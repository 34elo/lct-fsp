"""Реестр ФСП (E39-28, ADR-052): мероприятия, участники, результаты и заявки на привязку.

Админ ведёт реестр руками или CSV. Кандидат жмёт «Привязать ФСП»: core присылает email и телефон
его аккаунта, мы ищем участника по нормализованным контактам — совпал ровно один → привязка сразу
(`fsp_links.method = registry`, `verified = true`), иначе кандидат подаёт заявку, админ принимает
(выбирает участника) или отклоняет с причиной.

Реестр — ещё и источник данных: `RegistryAdapter` отдаёт мероприятия и результаты реестра через
обычный `FspPort`, поэтому синхронизация (`SyncService`) и события `fsp.*` для core не меняются.
ID участников `r-…` живут только в реестре; иные ID (например, `p-anya` из источника ФСП)
— «надстройка»: контакты из реестра, результаты из реестра плюс из источника.

ПДн (ФИО, email, телефон) не логируются и не попадают в события.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import structlog
from fsp_contracts.fsp import (
    FspCompetition,
    FspOAuthIdentity,
    FspParticipant,
    FspParticipantBrief,
    FspRank,
    FspResult,
    FspStandingRow,
    FspTeam,
    FspTeamMember,
    MaskedContact,
)
from fsp_platform.app import ProblemError
from fsp_platform.db import session_scope
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fsp_connector.errors import FspError, FspNotFound
from fsp_connector.linking import LinkService
from fsp_connector.models import (
    FspLink,
    LinkRequest,
    RegistryEvent,
    RegistryParticipant,
    RegistryResult,
)
from fsp_connector.port import FspPort

log = structlog.get_logger()

NATIVE_PREFIX = "r-"  # участник только из реестра: в источник ФСП за ним не ходим
TEAM_PREFIX = "rt:"  # ID команды реестра: rt:{event_id}:{название}
MAX_CSV_ROWS = 5000

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ нормализация контактов
def normalize_email(raw: str | None) -> str | None:
    """`  Anya@Example.TEST ` → `anya@example.test`; пусто или не email → None."""
    if raw is None:
        return None
    s = raw.strip().lower()
    if s.startswith("mailto:"):
        s = s[len("mailto:") :]
    return s if _EMAIL.match(s) else None


def normalize_phone(raw: str | None) -> str | None:
    """Российский номер в E.164: `8 (900) 123-45-67`, `9001234567` → `+79001234567`.

    Иные страны — `+` и цифры (11–15 цифр). Меньше 10 цифр → None.
    """
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits
    elif len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    if len(digits) < 11 or len(digits) > 15:
        return None
    return "+" + digits


def mask_email(email: str | None) -> str | None:
    if not email:
        return None
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return f"{phone[:2]}*******{phone[-2:]}"


def split_name(full_name: str) -> tuple[str, str, str | None]:
    parts = full_name.split()
    if not parts:
        return "", "", None
    if len(parts) == 1:
        return parts[0], "", None
    return parts[0], parts[1], " ".join(parts[2:]) or None


def team_id(event_id: str, team: str) -> str:
    return f"{TEAM_PREFIX}{event_id}:{team}"


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}{secrets.token_hex(5)}"


# ------------------------------------------------------------------ CSV участников
@dataclass
class CsvRow:
    line: int
    full_name: str
    email: str | None
    phone: str | None


@dataclass
class CsvParsed:
    rows: list[CsvRow] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


_HEADERS = {
    "full_name": {"фио", "full_name", "name", "имя", "участник"},
    "email": {"email", "e-mail", "почта", "эл. почта", "электронная почта"},
    "phone": {"телефон", "phone", "тел", "тел."},
}


def parse_participants_csv(text: str) -> CsvParsed:
    """CSV «ФИО, email, телефон» (`,` или `;`, заголовок необязателен). Ошибки — по строкам."""
    out = CsvParsed()
    text = text.lstrip("﻿")
    sample = text[:2048]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    cols = {"full_name": 0, "email": 1, "phone": 2}
    for n, raw in enumerate(reader, start=1):
        cells = [c.strip() for c in raw]
        if not any(cells):
            continue
        if n == 1:
            lowered = [c.lower() for c in cells]
            found = {
                key: i
                for key, names in _HEADERS.items()
                for i, c in enumerate(lowered)
                if c in names
            }
            if "full_name" in found:
                cols = {k: found.get(k, -1) for k in cols}
                continue
        if len(out.rows) + len(out.errors) >= MAX_CSV_ROWS:
            out.errors.append({"line": n, "reason": "too_many_rows"})
            break

        def cell(key: str, cells: list[str] = cells, cols: dict[str, int] = cols) -> str:
            i = cols[key]
            return cells[i] if 0 <= i < len(cells) else ""

        name, email_raw, phone_raw = cell("full_name"), cell("email"), cell("phone")
        if not name:
            out.errors.append({"line": n, "reason": "no_name"})
            continue
        email = normalize_email(email_raw)
        if email_raw and email is None:
            out.errors.append({"line": n, "reason": "bad_email"})
            continue
        phone = normalize_phone(phone_raw)
        if phone_raw and phone is None:
            out.errors.append({"line": n, "reason": "bad_phone"})
            continue
        out.rows.append(CsvRow(n, " ".join(name.split()), email, phone))
    return out


# ------------------------------------------------------------------ сервис реестра
@dataclass
class MatchResult:
    linked: bool
    participant_id: str | None = None
    matched_by: str | None = None  # email | phone


class RegistryService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        links: LinkService,
        resync: Any | None = None,  # SyncService: пересылка результатов привязанным кандидатам
    ):
        self.sessions, self.links, self.resync = sessions, links, resync

    # ---------------------------------------------------------------- мероприятия
    async def list_events(self) -> list[dict[str, Any]]:
        async with self.sessions() as s:
            counts = dict(
                (
                    await s.execute(
                        select(RegistryResult.event_id, func.count()).group_by(
                            RegistryResult.event_id
                        )
                    )
                ).all()
            )
            rows = await s.scalars(
                select(RegistryEvent).order_by(RegistryEvent.date.desc(), RegistryEvent.id)
            )
            return [_event_out(e, counts.get(e.id, 0)) for e in rows]

    async def create_event(self, data: dict[str, Any]) -> dict[str, Any]:
        async with session_scope(self.sessions) as s:
            e = RegistryEvent(id=_new_id("e-"), **data)
            s.add(e)
            await s.flush()
            return _event_out(e, 0)

    async def update_event(self, event_id: str, data: dict[str, Any]) -> dict[str, Any]:
        async with session_scope(self.sessions) as s:
            e = await s.get(RegistryEvent, event_id)
            if e is None:
                raise ProblemError(404, "not_found", "Мероприятие не найдено")
            for k, v in data.items():
                setattr(e, k, v)
            e.updated_at = _now()
            n = await s.scalar(select(func.count()).where(RegistryResult.event_id == event_id))
            pids = list(
                await s.scalars(
                    select(RegistryResult.participant_id).where(RegistryResult.event_id == event_id)
                )
            )
            out = _event_out(e, n or 0)
        await self._resync(pids)
        return out

    # ---------------------------------------------------------------- участники
    async def list_participants(self, q: str | None, limit: int = 50) -> list[dict[str, Any]]:
        async with self.sessions() as s:
            stmt = select(RegistryParticipant).order_by(RegistryParticipant.full_name)
            if q and q.strip():
                q = q.strip()
                like = f"%{q.lower()}%"
                conds = [
                    RegistryParticipant.full_name.ilike(f"%{q}%"),
                    RegistryParticipant.full_name.like(f"%{q[:1].upper()}{q[1:].lower()}%"),
                    RegistryParticipant.full_name.like(f"%{q.lower()}%"),
                    RegistryParticipant.email_norm.like(like),
                    func.lower(RegistryParticipant.id).like(like),
                ]
                phone = normalize_phone(q)
                if phone:
                    conds.append(RegistryParticipant.phone_norm == phone)
                stmt = stmt.where(or_(*conds))
            parts = list(await s.scalars(stmt.limit(limit)))
            linked = await _linked_of(s, [p.id for p in parts])
            return [_participant_out(p, linked.get(p.id)) for p in parts]

    async def create_participant(
        self, full_name: str, email: str | None, phone: str | None
    ) -> dict[str, Any]:
        email_n, phone_n = normalize_email(email), normalize_phone(phone)
        if email and email_n is None:
            raise ProblemError(422, "bad_email", "Неверный email")
        if phone and phone_n is None:
            raise ProblemError(422, "bad_phone", "Неверный телефон")
        async with session_scope(self.sessions) as s:
            if await _find_by_contacts(s, email_n, phone_n):
                raise ProblemError(
                    409, "participant_exists", "Участник с таким email или телефоном уже есть"
                )
            p = RegistryParticipant(
                id=_new_id(NATIVE_PREFIX),
                full_name=" ".join(full_name.split()),
                email=email_n,
                phone=phone_n,
                email_norm=email_n,
                phone_norm=phone_n,
            )
            s.add(p)
            await s.flush()
            return _participant_out(p, None)

    async def import_csv(self, text: str) -> dict[str, Any]:
        parsed = parse_participants_csv(text)
        created = updated = 0
        async with session_scope(self.sessions) as s:
            for row in parsed.rows:
                existing = await _find_by_contacts(s, row.email, row.phone)
                if len(existing) > 1:
                    parsed.errors.append({"line": row.line, "reason": "ambiguous"})
                    continue
                if existing:
                    p = existing[0]
                    p.full_name = row.full_name
                    if row.email:
                        p.email = p.email_norm = row.email
                    if row.phone:
                        p.phone = p.phone_norm = row.phone
                    updated += 1
                else:
                    s.add(
                        RegistryParticipant(
                            id=_new_id(NATIVE_PREFIX),
                            full_name=row.full_name,
                            email=row.email,
                            phone=row.phone,
                            email_norm=row.email,
                            phone_norm=row.phone,
                        )
                    )
                    created += 1
                await s.flush()
        errors = sorted(parsed.errors, key=lambda e: e["line"])
        log.info("fsp_registry_import", created=created, updated=updated, errors=len(errors))
        return {"created": created, "updated": updated, "errors": errors}

    # ---------------------------------------------------------------- результаты
    async def list_results(
        self, event_id: str | None, participant_id: str | None
    ) -> list[dict[str, Any]]:
        async with self.sessions() as s:
            stmt = (
                select(RegistryResult, RegistryParticipant.full_name, RegistryEvent.title)
                .join(RegistryParticipant, RegistryParticipant.id == RegistryResult.participant_id)
                .join(RegistryEvent, RegistryEvent.id == RegistryResult.event_id)
                .order_by(
                    RegistryEvent.date.desc(),
                    RegistryResult.place.is_(None),
                    RegistryResult.place,
                    RegistryParticipant.full_name,
                )  # fmt: skip
            )
            if event_id:
                stmt = stmt.where(RegistryResult.event_id == event_id)
            if participant_id:
                stmt = stmt.where(RegistryResult.participant_id == participant_id)
            return [
                {
                    "id": r.id,
                    "participant_id": r.participant_id,
                    "participant_name": name,
                    "event_id": r.event_id,
                    "event_title": title,
                    "place": r.place,
                    "team": r.team,
                }
                for r, name, title in (await s.execute(stmt.limit(500))).all()
            ]

    async def upsert_result(
        self, participant_id: str, event_id: str, place: int | None, team: str | None
    ) -> int:
        team = " ".join(team.split()) if team and team.strip() else None
        async with session_scope(self.sessions) as s:
            if await s.get(RegistryParticipant, participant_id) is None:
                raise ProblemError(404, "not_found", "Участник не найден")
            if await s.get(RegistryEvent, event_id) is None:
                raise ProblemError(404, "not_found", "Мероприятие не найдено")
            row = await s.scalar(
                select(RegistryResult).where(
                    RegistryResult.participant_id == participant_id,
                    RegistryResult.event_id == event_id,
                )
            )
            if row is None:
                row = RegistryResult(participant_id=participant_id, event_id=event_id)
                s.add(row)
            row.place, row.team, row.updated_at = place, team, _now()
            await s.flush()
            rid = row.id
        await self._resync([participant_id])
        return rid

    async def delete_result(self, result_id: int) -> None:
        async with session_scope(self.sessions) as s:
            row = await s.get(RegistryResult, result_id)
            if row is None:
                raise ProblemError(404, "not_found", "Результат не найден")
            pid = row.participant_id
            await s.delete(row)
        await self._resync([pid])

    async def _resync(self, participant_ids: Iterable[str]) -> None:
        """Изменили результаты — привязанным кандидатам сразу уходит полная выгрузка."""
        if self.resync is None:
            return
        pids = sorted(set(participant_ids))
        if not pids:
            return
        async with self.sessions() as s:
            cids = list(
                await s.scalars(
                    select(FspLink.candidate_id).where(FspLink.participant_id.in_(pids))
                )
            )
        for cid in cids:
            try:
                async with session_scope(self.sessions) as s:
                    await self.resync.sync_candidate(s, cid, reason="manual")
            except FspError as exc:  # источник недоступен — догонит часовой sync_all
                log.warning("fsp_registry_resync_failed", candidate_id=str(cid), code=exc.code)

    # ---------------------------------------------------------------- привязка кандидата
    async def match(
        self, candidate_id: uuid.UUID, emails: Sequence[str], phones: Sequence[str]
    ) -> MatchResult:
        """Поиск по контактам аккаунта кандидата. Ровно одно совпадение — привязка сразу."""
        async with self.sessions() as s:
            mine = await s.get(FspLink, candidate_id)
            if mine is not None:
                return MatchResult(True, mine.participant_id, None)
            e_norm = sorted({e for e in (normalize_email(x) for x in emails) if e})
            p_norm = sorted({p for p in (normalize_phone(x) for x in phones) if p})
            by_email = (
                list(
                    await s.scalars(
                        select(RegistryParticipant.id).where(
                            RegistryParticipant.email_norm.in_(e_norm)
                        )
                    )
                )
                if e_norm
                else []
            )
            by_phone = (
                list(
                    await s.scalars(
                        select(RegistryParticipant.id).where(
                            RegistryParticipant.phone_norm.in_(p_norm)
                        )
                    )
                )
                if p_norm
                else []
            )
        if len(set(by_email)) == 1:
            pid, how = by_email[0], "email"
        elif not by_email and len(set(by_phone)) == 1:
            pid, how = by_phone[0], "phone"
        else:  # нет совпадений или неоднозначно — только через заявку
            return MatchResult(False)
        await self.links.bind_registry(candidate_id, pid)
        log.info("fsp_registry_matched", candidate_id=str(candidate_id), matched_by=how)
        return MatchResult(True, pid, how)

    async def create_request(
        self,
        candidate_id: uuid.UUID,
        full_name: str,
        email: str | None,
        phone: str | None,
        event: str | None,
    ) -> dict[str, Any]:
        email_n = normalize_email(email)
        phone_n = normalize_phone(phone)
        if email and email.strip() and email_n is None:
            raise ProblemError(422, "bad_email", "Неверный email")
        if phone and phone.strip() and phone_n is None:
            raise ProblemError(422, "bad_phone", "Неверный телефон")
        if not (email_n or phone_n):
            raise ProblemError(422, "validation_error", "Укажите email или телефон в ФСП")
        async with session_scope(self.sessions) as s:
            if await s.get(FspLink, candidate_id) is not None:
                raise ProblemError(409, "candidate_already_linked", "ФСП уже привязана")
            req = await s.scalar(
                select(LinkRequest).where(
                    LinkRequest.candidate_id == candidate_id, LinkRequest.status == "pending"
                )
            )
            if req is None:  # одна открытая заявка на кандидата: повтор правит её
                req = LinkRequest(id=uuid.uuid4(), candidate_id=candidate_id, status="pending")
                s.add(req)
            req.full_name = " ".join(full_name.split())
            req.email, req.phone = email_n, phone_n
            req.event = event.strip() if event and event.strip() else None
            req.created_at = _now()
            await s.flush()
            return _request_out(req)

    async def candidate_request(self, candidate_id: uuid.UUID) -> dict[str, Any] | None:
        async with self.sessions() as s:
            req = await s.scalar(
                select(LinkRequest)
                .where(LinkRequest.candidate_id == candidate_id)
                .order_by(LinkRequest.created_at.desc())
                .limit(1)
            )
            return _request_out(req) if req else None

    async def list_requests(self, status: str | None) -> list[dict[str, Any]]:
        async with self.sessions() as s:
            stmt = select(LinkRequest).order_by(LinkRequest.created_at.desc())
            if status:
                stmt = stmt.where(LinkRequest.status == status)
            reqs = list(await s.scalars(stmt.limit(200)))
            out = []
            for r in reqs:
                item = _request_out(r)
                item["candidates"] = [  # подсказка админу: кто в реестре похож по контактам
                    _participant_out(p, None) for p in await _find_by_contacts(s, r.email, r.phone)
                ]
                out.append(item)
            return out

    async def accept_request(self, request_id: uuid.UUID, participant_id: str) -> dict[str, Any]:
        async with self.sessions() as s:
            req = await s.get(LinkRequest, request_id)
            if req is None:
                raise ProblemError(404, "not_found", "Заявка не найдена")
            if req.status != "pending":
                raise ProblemError(409, "request_decided", "Заявка уже рассмотрена")
            if await s.get(RegistryParticipant, participant_id) is None:
                raise ProblemError(404, "not_found", "Участник не найден")
            candidate_id = req.candidate_id
        await self.links.bind_registry(candidate_id, participant_id)
        async with session_scope(self.sessions) as s:
            req = await s.get(LinkRequest, request_id)
            assert req is not None
            req.status, req.participant_id, req.decided_at = "accepted", participant_id, _now()
            return _request_out(req)

    async def reject_request(self, request_id: uuid.UUID, reason: str) -> dict[str, Any]:
        async with session_scope(self.sessions) as s:
            req = await s.get(LinkRequest, request_id)
            if req is None:
                raise ProblemError(404, "not_found", "Заявка не найдена")
            if req.status != "pending":
                raise ProblemError(409, "request_decided", "Заявка уже рассмотрена")
            req.status, req.reason, req.decided_at = "rejected", reason.strip(), _now()
            return _request_out(req)


# ------------------------------------------------------------------ демо-наполнение (seed)
async def upsert_demo(
    sessions: async_sessionmaker[AsyncSession],
    *,
    events: Sequence[dict[str, Any]],
    participants: Sequence[dict[str, Any]],
    results: Sequence[dict[str, Any]],
) -> dict[str, int]:
    """Идемпотентно (по ID) кладёт демо-реестр: герои и жюри с email их аккаунтов."""
    async with session_scope(sessions) as s:
        for e in events:
            row = await s.get(RegistryEvent, e["id"]) or RegistryEvent(id=e["id"])
            row.title, row.discipline, row.level = e["title"], e["discipline"], e["level"]
            row.date = e["date"] if isinstance(e["date"], date) else date.fromisoformat(e["date"])
            row.updated_at = _now()
            s.add(row)
        for p in participants:
            row = await s.get(RegistryParticipant, p["id"]) or RegistryParticipant(id=p["id"])
            email, phone = normalize_email(p.get("email")), normalize_phone(p.get("phone"))
            row.full_name = p["full_name"]
            row.email = row.email_norm = email
            row.phone = row.phone_norm = phone
            s.add(row)
        await s.flush()
        for r in results:
            row = await s.scalar(
                select(RegistryResult).where(
                    RegistryResult.participant_id == r["participant_id"],
                    RegistryResult.event_id == r["event_id"],
                )
            )
            if row is None:
                row = RegistryResult(participant_id=r["participant_id"], event_id=r["event_id"])
                s.add(row)
            row.place, row.team = r.get("place"), r.get("team")
    return {"events": len(events), "participants": len(participants), "results": len(results)}


# ------------------------------------------------------------------ адаптер-источник
class RegistryAdapter:
    """`FspPort` поверх реестра; чего нет в реестре — у внутреннего адаптера (источник ФСП)."""

    def __init__(self, inner: FspPort, sessions: async_sessionmaker[AsyncSession]):
        self.inner, self.sessions = inner, sessions

    async def aclose(self) -> None:
        inner = getattr(self.inner, "inner", self.inner)
        close = getattr(inner, "aclose", None)
        if close is not None:
            await close()

    async def invalidate(self, participant_id: str) -> None:
        inv = getattr(self.inner, "invalidate", None)
        if inv is not None:
            await inv(participant_id)

    @staticmethod
    def _native(pid: str) -> bool:
        return pid.startswith(NATIVE_PREFIX)

    async def get_participant(self, participant_id: str) -> FspParticipant:
        async with self.sessions() as s:
            p = await s.get(RegistryParticipant, participant_id)
        if p is None:
            if self._native(participant_id):
                raise FspNotFound(participant_id)
            return await self.inner.get_participant(participant_id)
        last, first, middle = split_name(p.full_name)
        ranks = await self.get_ranks(participant_id)
        return FspParticipant(
            id=p.id,
            last_name=last,
            first_name=first,
            middle_name=middle,
            email_masked=mask_email(p.email),
            phone_masked=mask_phone(p.phone),
            ranks=ranks,
        )

    async def find_participant(
        self,
        *,
        email: str | None = None,
        last_name: str | None = None,
        birth_date: date | None = None,
    ) -> list[FspParticipantBrief]:
        e = normalize_email(email)
        if e:
            async with self.sessions() as s:
                found = list(
                    await s.scalars(
                        select(RegistryParticipant).where(RegistryParticipant.email_norm == e)
                    )
                )
            if found:
                return [_brief(p) for p in found]
        return await self.inner.find_participant(
            email=email, last_name=last_name, birth_date=birth_date
        )

    async def _registry_results(self, participant_id: str, since: date | None) -> list[FspResult]:
        async with self.sessions() as s:
            rows = (
                await s.execute(
                    select(RegistryResult, RegistryEvent)
                    .join(RegistryEvent, RegistryEvent.id == RegistryResult.event_id)
                    .where(RegistryResult.participant_id == participant_id)
                    .order_by(RegistryEvent.date)
                )
            ).all()
            event_ids = [e.id for _, e in rows]
            totals: dict[str, int] = {}
            if event_ids:  # в зачёте: max(число результатов, худшее место)
                for eid, n, worst in (
                    await s.execute(
                        select(
                            RegistryResult.event_id, func.count(), func.max(RegistryResult.place)
                        )
                        .where(RegistryResult.event_id.in_(event_ids))
                        .group_by(RegistryResult.event_id)
                    )
                ).all():
                    totals[eid] = max(n, worst or 0)
        out = []
        for r, e in rows:
            if since is not None and e.date < since:
                continue
            out.append(
                FspResult(
                    competition_id=e.id,
                    discipline=e.discipline,
                    stage="final",
                    team_id=team_id(e.id, r.team) if r.team else None,
                    team_role="member" if r.team else "individual",
                    place=r.place,
                    participants_total=max(totals.get(e.id, 1), r.place or 1),
                    date=e.date,
                )
            )
        return out

    async def get_results(self, participant_id: str, since: date | None = None) -> list[FspResult]:
        own = await self._registry_results(participant_id, since)
        if self._native(participant_id):
            return own
        try:
            return own + await self.inner.get_results(participant_id, since)
        except FspNotFound:
            return own

    async def get_ranks(self, participant_id: str) -> list[FspRank]:
        if self._native(participant_id):
            return []
        try:
            return await self.inner.get_ranks(participant_id)
        except FspNotFound:
            return []

    async def get_competitions(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        discipline: str | None = None,
    ) -> list[FspCompetition]:
        async with self.sessions() as s:
            events = list(await s.scalars(select(RegistryEvent).order_by(RegistryEvent.date)))
        today = datetime.now(UTC).date()
        own = [
            FspCompetition(
                id=e.id,
                title=e.title,
                discipline=e.discipline,
                level=e.level,
                format="offline",
                start_date=e.date,
                status="finished" if e.date <= today else "announced",
            )
            for e in events
            if (date_from is None or e.date >= date_from)
            and (date_to is None or e.date <= date_to)
            and (discipline is None or e.discipline == discipline)
        ]
        try:
            rest = await self.inner.get_competitions(
                date_from=date_from, date_to=date_to, discipline=discipline
            )
        except FspError as exc:  # источник недоступен — реестр всё равно отдаём
            log.warning("fsp_registry_inner_competitions_failed", code=exc.code)
            rest = []
        return own + rest

    async def get_standings(self, competition_id: str) -> list[FspStandingRow]:
        async with self.sessions() as s:
            if await s.get(RegistryEvent, competition_id) is None:
                return await self.inner.get_standings(competition_id)
            rows = list(
                await s.scalars(
                    select(RegistryResult)
                    .where(RegistryResult.event_id == competition_id)
                    .where(RegistryResult.place.is_not(None))
                    .order_by(RegistryResult.place)
                )
            )
        return [
            FspStandingRow(
                place=r.place or 1,
                team_id=team_id(competition_id, r.team) if r.team else None,
                participant_ids=[r.participant_id],
            )
            for r in rows
        ]

    async def get_team(self, team_id_: str) -> FspTeam:
        if not team_id_.startswith(TEAM_PREFIX):
            return await self.inner.get_team(team_id_)
        event_id, _, name = team_id_[len(TEAM_PREFIX) :].partition(":")
        async with self.sessions() as s:
            rows = list(
                await s.scalars(
                    select(RegistryResult).where(
                        RegistryResult.event_id == event_id, RegistryResult.team == name
                    )
                )
            )
        if not rows:
            raise FspNotFound(team_id_)
        return FspTeam(
            id=team_id_,
            name=name,
            competition_id=event_id,
            members=[FspTeamMember(participant_id=r.participant_id, role="member") for r in rows],
        )

    # верификация и OAuth — у источника (бэкенд OAuth сохраняем, ADR-052)
    async def send_verification_code(self, participant_id: str) -> MaskedContact:
        return await self.inner.send_verification_code(participant_id)

    async def check_verification_code(self, participant_id: str, code: str) -> bool:
        return await self.inner.check_verification_code(participant_id, code)

    def authorize_url(self, state: str, code_challenge: str) -> str:
        return self.inner.authorize_url(state, code_challenge)

    async def exchange_code(self, code: str, code_verifier: str) -> FspOAuthIdentity:
        return await self.inner.exchange_code(code, code_verifier)


# ------------------------------------------------------------------ helpers
async def _find_by_contacts(
    s: AsyncSession, email: str | None, phone: str | None
) -> list[RegistryParticipant]:
    conds = []
    if email:
        conds.append(RegistryParticipant.email_norm == email)
    if phone:
        conds.append(RegistryParticipant.phone_norm == phone)
    if not conds:
        return []
    return list(await s.scalars(select(RegistryParticipant).where(or_(*conds))))


async def _linked_of(s: AsyncSession, pids: list[str]) -> dict[str, str]:
    if not pids:
        return {}
    rows = await s.execute(
        select(FspLink.participant_id, FspLink.candidate_id).where(FspLink.participant_id.in_(pids))
    )
    return {pid: str(cid) for pid, cid in rows.all()}


def _event_out(e: RegistryEvent, results: int) -> dict[str, Any]:
    return {
        "id": e.id,
        "title": e.title,
        "discipline": e.discipline,
        "level": e.level,
        "date": e.date,
        "results": results,
    }


def _participant_out(p: RegistryParticipant, linked_candidate: str | None) -> dict[str, Any]:
    return {
        "id": p.id,
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "linked": linked_candidate is not None,
    }


def _request_out(r: LinkRequest) -> dict[str, Any]:
    return {
        "id": r.id,
        "candidate_id": r.candidate_id,
        "full_name": r.full_name,
        "email": r.email,
        "phone": r.phone,
        "event": r.event,
        "status": r.status,
        "reason": r.reason,
        "participant_id": r.participant_id,
        "created_at": r.created_at,
        "decided_at": r.decided_at,
    }


def _brief(p: RegistryParticipant) -> FspParticipantBrief:
    last, first, _ = split_name(p.full_name)
    return FspParticipantBrief(id=p.id, full_name_masked=f"{last[:1]}*** {first[:1]}.".strip())
