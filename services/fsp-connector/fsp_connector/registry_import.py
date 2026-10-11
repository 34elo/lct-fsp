"""Добавление результатов в реестр ФСП списком: CSV/вставка из таблицы, превью и импорт.

Колонки: `участник` (ФИО, email, телефон или ID), `мероприятие`, `дата`, `результат`
(место числом; «участие»/пусто — участие без места), необязательные `дисциплина`, `уровень`.
Разбор и проверка строк — чистые функции; запись в БД — `plan_and_apply` (одна транзакция).
Идемпотентность: ключ «участник + мероприятие»; такая же запись повторно — `unchanged`.
ПДн (ФИО, email, телефон) не логируются.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from fsp_contracts.enums import FspDiscipline, FspLevel
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fsp_connector.models import RegistryEvent, RegistryParticipant, RegistryResult

MAX_IMPORT_ROWS = 1000

_HEADERS = {
    "participant": {"участник", "фио", "participant", "name", "email", "e-mail", "ник"},
    "event": {"мероприятие", "событие", "соревнование", "event"},
    "date": {"дата", "date"},
    "result": {"результат", "место", "result", "place"},
    "discipline": {"дисциплина", "discipline"},
    "level": {"уровень", "level"},
}
_ORDER = ["participant", "event", "date", "result", "discipline", "level"]
_PARTICIPATION = {"", "-", "—", "участие", "участник", "участвовал", "участвовала"}
_PLACE = re.compile(r"^(\d{1,6})(?:\s*(?:-?е)?\s*(?:место|м\.?))?$")
_DISCIPLINES = {
    "алгоритмическое": "algorithmic",
    "алгоритмическое программирование": "algorithmic",
    "продуктовое": "product",
    "продуктовое программирование": "product",
    "безопасность": "security",
    "информационная безопасность": "security",
    "бпла": "uav",
    "робототехника": "robotics",
}
_LEVELS = {
    "региональный": "regional",
    "межрегиональный": "interregional",
    "всероссийский": "national",
    "федеральный": "national",
    "международный": "international",
}


@dataclass
class ImportLine:
    line: int
    participant: str
    event: str
    date_raw: str
    result: str
    discipline: str = ""
    level: str = ""


@dataclass
class _Planned:
    line: ImportLine
    status: str = "ok"  # ok | error
    action: str | None = None  # create | update | unchanged
    error: str | None = None
    participant_id: str | None = None
    participant_name: str | None = None
    event_id: str | None = None  # существующее мероприятие
    new_event_key: str | None = None
    event_date: date | None = None
    place: int | None = None


@dataclass
class ImportOutcome:
    lines: list[dict[str, Any]] = field(default_factory=list)
    new_events: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    affected: list[str] = field(default_factory=list)


def parse_date(raw: str) -> date | None:
    s = raw.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})$", s)
        if not m:
            return None
        d, mo, y = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_place(raw: str) -> tuple[bool, int | None]:
    """(ok, место): «3», «3 место» → 3; «участие»/пусто → None; прочее — ошибка."""
    s = raw.strip().casefold()
    if s in _PARTICIPATION:
        return True, None
    m = _PLACE.match(s)
    if m and 1 <= int(m.group(1)) <= 100000:
        return True, int(m.group(1))
    return False, None


def parse_import_text(text: str) -> list[ImportLine]:
    """Разбор CSV (`;`, `,` или TAB из таблицы); заголовок необязателен."""
    text = text.lstrip("﻿")
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    delim = max((";", "\t", ","), key=first.count) if any(c in first for c in ";\t,") else ","
    cols = dict(zip(_ORDER, range(len(_ORDER)), strict=True))
    out: list[ImportLine] = []
    header_checked = False
    for n, raw in enumerate(csv.reader(io.StringIO(text), delimiter=delim), start=1):
        cells = [c.strip() for c in raw]
        if not any(cells):
            continue
        if not header_checked:
            header_checked = True
            lowered = [c.casefold() for c in cells]
            found = {
                k: i for k, names in _HEADERS.items() for i, c in enumerate(lowered) if c in names
            }
            if "participant" in found and "event" in found:
                cols = {k: found.get(k, -1) for k in _ORDER}
                continue
        if len(out) >= MAX_IMPORT_ROWS:
            raise ProblemError(
                422, "too_many_rows", f"В файле больше {MAX_IMPORT_ROWS} строк — разбейте на части"
            )

        def cell(key: str, cells: list[str] = cells, cols: dict[str, int] = cols) -> str:
            i = cols[key]
            return cells[i] if 0 <= i < len(cells) else ""

        out.append(
            ImportLine(
                n,
                " ".join(cell("participant").split()),
                " ".join(cell("event").split()),
                cell("date"),
                cell("result"),
                cell("discipline").casefold(),
                cell("level").casefold(),
            )
        )
    return out


def _norm_name(s: str) -> str:
    return " ".join(s.split()).casefold().replace("ё", "е")


def _pick(raw: str, ru: dict[str, str], valid: set[str], default: str) -> str | None:
    if not raw:
        return default
    return raw if raw in valid else ru.get(raw)


async def plan_and_apply(
    s: AsyncSession,
    lines: list[ImportLine],
    *,
    commit: bool,
    skip_errors: bool,
    create_events: set[str],
    default_discipline: str,
    default_level: str,
) -> ImportOutcome:
    """Проверяет строки и (commit) записывает. Вызывать внутри одной транзакции."""
    parts = list(await s.scalars(select(RegistryParticipant)))
    idx = _Index(parts, list(await s.scalars(select(RegistryEvent))))
    existing = {(r.participant_id, r.event_id): r for r in await s.scalars(select(RegistryResult))}

    planned: list[_Planned] = []
    seen: set[tuple[str, str]] = set()
    new_events: dict[str, dict[str, Any]] = {}
    for ln in lines:
        pl = _Planned(ln)
        planned.append(pl)
        pl.error = _check(pl, idx, new_events, default_discipline, default_level)
        if pl.error is None:
            key = (pl.participant_id or "", pl.event_id or pl.new_event_key or "")
            if key in seen:
                pl.error = "duplicate"
            seen.add(key)
        if pl.error is None and commit and pl.new_event_key not in (None, *create_events):
            pl.error = "event_not_confirmed"
        if pl.error is None:
            cur = existing.get((pl.participant_id or "", pl.event_id or ""))
            if cur is None:
                pl.action = "create"
            else:
                pl.action = "unchanged" if cur.place == pl.place else "update"
        else:
            pl.status = "error"
    for ev in new_events.values():
        ev["rows"] = sum(1 for p in planned if p.new_event_key == ev["key"] and p.status == "ok")
        ev["confirmed"] = ev["key"] in create_events

    errors = sum(1 for p in planned if p.status == "error")
    out = ImportOutcome(
        lines=[_line_out(p) for p in planned],
        new_events=[e for e in new_events.values() if e["rows"] > 0],
    )
    summary = {"total": len(planned), "errors": errors, "created": 0, "updated": 0, "unchanged": 0}
    if commit and errors and not skip_errors:
        raise ProblemError(
            422, "has_errors", "В файле есть ошибочные строки — исправьте или пропустите их"
        )
    created_events: dict[str, str] = {}
    affected: set[str] = set()
    now = datetime.now(UTC)
    for p in planned:
        if p.status != "ok" or p.action is None:
            continue
        counter = {"create": "created", "update": "updated"}.get(p.action, "unchanged")
        summary[counter] += 1
        if not commit or p.action == "unchanged":
            continue
        eid = p.event_id
        if eid is None:
            key = p.new_event_key or ""
            if key not in created_events:
                meta = new_events[key]
                created_events[key] = "e-" + secrets.token_hex(5)
                s.add(
                    RegistryEvent(
                        id=created_events[key],
                        title=meta["title"],
                        discipline=meta["discipline"],
                        level=meta["level"],
                        date=meta["date"],
                    )
                )
                await s.flush()
            eid = created_events[key]
        pid = p.participant_id or ""
        row = existing.get((pid, eid))
        if row is None:
            s.add(RegistryResult(participant_id=pid, event_id=eid, place=p.place, updated_at=now))
        else:
            row.place, row.updated_at = p.place, now
        affected.add(pid)
    if commit:
        await s.flush()
        out.affected = sorted(affected)
    out.summary = summary
    return out


class _Index:
    def __init__(self, parts: list[RegistryParticipant], events: list[RegistryEvent]):
        self.by_email = {p.email_norm: p for p in parts if p.email_norm}
        self.by_phone = {p.phone_norm: p for p in parts if p.phone_norm}
        self.by_id = {p.id.casefold(): p for p in parts}
        self.by_name: dict[str, list[RegistryParticipant]] = {}
        for p in parts:
            self.by_name.setdefault(_norm_name(p.full_name), []).append(p)
        self.ev_by_title: dict[str, list[RegistryEvent]] = {}
        for e in events:
            self.ev_by_title.setdefault(_norm_name(e.title), []).append(e)


def _find_participant(ln: ImportLine, idx: _Index) -> list[RegistryParticipant]:
    from fsp_connector.registry import normalize_email, normalize_phone

    if (em := normalize_email(ln.participant)) is not None:
        return [idx.by_email[em]] if em in idx.by_email else []
    if re.fullmatch(r"[+\d\s()\-]{10,}", ln.participant):
        ph = normalize_phone(ln.participant)
        return [idx.by_phone[ph]] if ph in idx.by_phone else []
    if ln.participant.casefold() in idx.by_id:
        return [idx.by_id[ln.participant.casefold()]]
    return idx.by_name.get(_norm_name(ln.participant), [])


def _check(
    pl: _Planned,
    idx: _Index,
    new_events: dict[str, dict[str, Any]],
    default_discipline: str,
    default_level: str,
) -> str | None:
    ln = pl.line
    if not ln.participant:
        return "no_participant"
    found = _find_participant(ln, idx)
    if not found:
        return "participant_not_found"
    if len(found) > 1:
        return "participant_ambiguous"
    pl.participant_id, pl.participant_name = found[0].id, found[0].full_name

    ok, pl.place = parse_place(ln.result)
    if not ok:
        return "bad_result"
    if not ln.event:
        return "no_event"
    if len(ln.event) < 2 or len(ln.event) > 200:
        return "bad_event"
    d: date | None = None
    if ln.date_raw:
        d = parse_date(ln.date_raw)
        if d is None:
            return "bad_date"
    matches = idx.ev_by_title.get(_norm_name(ln.event), [])
    if d is not None:
        matches = [e for e in matches if e.date == d]
    if len(matches) == 1:
        pl.event_id = matches[0].id
        return None
    if len(matches) > 1:
        return "event_ambiguous"
    if d is None:
        return "no_date"
    disc = _pick(ln.discipline, _DISCIPLINES, {x.value for x in FspDiscipline}, default_discipline)
    lvl = _pick(ln.level, _LEVELS, {x.value for x in FspLevel}, default_level)
    if disc is None:
        return "bad_discipline"
    if lvl is None:
        return "bad_level"
    key = f"{_norm_name(ln.event)}|{d.isoformat()}"
    pl.new_event_key, pl.event_date = key, d
    new_events.setdefault(
        key, {"key": key, "title": ln.event, "date": d, "discipline": disc, "level": lvl}
    )
    return None


def _line_out(p: _Planned) -> dict[str, Any]:
    ln = p.line
    return {
        "line": ln.line,
        "participant": ln.participant,
        "participant_id": p.participant_id,
        "participant_name": p.participant_name,
        "event": ln.event,
        "date": ln.date_raw or None,
        "result": ln.result or None,
        "status": p.status,
        "action": p.action,
        "error": p.error,
        "new_event_key": p.new_event_key,
    }
