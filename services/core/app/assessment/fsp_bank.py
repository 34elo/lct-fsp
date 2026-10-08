"""Задачи соревнований ФСП в банке заданий (E32-6, ADR-025, assessment.md §4).

Платформа не только для олимпиадников: задачи прошлых соревнований ФСП — дополнительный источник
банка (`families.source = fsp`), но участник соревнования не получает преимущества. Защита:

1. **Не показываем участнику.** Семейство несёт `competition_id`; кандидату, у которого в графе есть
   результат или команда этого соревнования (`graph.service.fsp_competitions_of`), оно не выдаётся
   (`engine.eligible`).
2. **Нет бонуса за ФСП в θ.** Участие считается только в слагаемом F силы профиля
   (`graph/fsp_strength.py`), θ и грейд от него не зависят.
3. **Сложность не из «решаемости среди своих».** Старт — априорная `b` по уровню; Rasch-калибровка
   (`psychometrics_db`) не учитывает ответы кандидатов с доказательствами ФСП, шкалу задаёт
   остальная аудитория.
4. **DIF «с ФСП / без ФСП» обязателен.** Допуск `pilot → active` без измеренного DIF невозможен
   (`dif_unmeasured`), порог — `admit_max_dif`; утечка и апелляции работают как у всех семейств.
5. **Происхождение.** Каждая запись банка — соревнование, лицензия и (для `fsp-permission`) ссылка
   на разрешение организаторов; без них банк не принимается.

Банк — YAML `data/questions/fsp/<имя>.yaml`: `schema`, `competition {id, title, year, url, license,
permission?}`, `tasks[{slug?, form}]`, где `form` — форма конструктора (`FamilySpec`) с готовым
ключом. Условие — параметризованное (`params`, `derived`), а не копия текста оригинала: это и
лицензия, и уникальность вариантов. Импорт идемпотентен по slug; новое семейство — `draft` (или
`pilot` с `--pilot`), в `active` — только админ по статистике пилота.

`python -m app.assessment.fsp_bank check|import [файлы]`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import constructor, lifecycle
from app.assessment.config import AssessmentConfig
from app.assessment.families.base import Kind
from app.assessment.families.spec import FamilySpec, SpecFamily
from app.assessment.models import FamilyRow
from app.taxonomy import service as taxonomy

ROOT = Path(__file__).resolve().parents[4]
BANK_DIR = ROOT / "data" / "questions" / "fsp"
SCHEMA = 1
SOURCE = "fsp"
NAMESPACE = uuid.UUID("3f1c8d52-7a4e-4f0b-8c36-66737062616e")
# CC0 и CC-BY — условия открытой публикации; fsp-permission — письменное разрешение организаторов
# (поле `permission`); author — задача написана нами по мотивам, текст оригинала не копировался.
LICENSES = ("CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "fsp-permission", "author")
NOT_IN_TEST = (Kind.open, Kind.chain)


class BankError(ValueError):
    """Банк задач ФСП не принимается."""


def load(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise BankError(f"{path.name}: ожидался YAML-словарь")
    return raw


def slug_of(competition_id: str, form: dict[str, Any]) -> str:
    h = hashlib.sha256(json.dumps(form, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f"fsp-{competition_id}-{h[:8]}".lower()


def digest(competition: dict[str, Any], form: dict[str, Any]) -> str:
    blob = json.dumps({"c": competition, "f": form}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def check_header(bank: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if bank.get("schema") != SCHEMA:
        errs.append(f"schema {bank.get('schema')} ≠ {SCHEMA}")
    comp = bank.get("competition")
    if not isinstance(comp, dict):
        return [*errs, "нет секции competition"]
    for k in ("id", "title", "year", "url"):
        if not comp.get(k):
            errs.append(f"competition.{k} обязателен")
    lic = comp.get("license")
    if lic not in LICENSES:
        errs.append(f"competition.license {lic!r} не из {LICENSES}")
    if lic == "fsp-permission" and not comp.get("permission"):
        errs.append("fsp-permission: укажите competition.permission (ссылка или дата письма ФСП)")
    if not isinstance(bank.get("tasks"), list) or not bank["tasks"]:
        errs.append("нет задач (tasks)")
    return errs


def check_task(form: dict[str, Any], *, taxonomy_skills: set[str] | None = None) -> list[str]:
    """Форма — `FamilySpec` с готовым ключом, не `open`/`chain`, автопроверка на 200 сидах."""
    try:
        spec = FamilySpec.model_validate(form)
    except (ValidationError, ValueError) as e:
        msg = e.errors()[0]["msg"] if isinstance(e, ValidationError) else str(e)
        return [f"форма: {msg}"]
    if spec.kind in NOT_IN_TEST:
        return [f"kind={spec.kind.value} не идёт в тест"]
    if spec.missing_key():
        return [f"нет ключа: {', '.join(spec.missing_key())} (черновик LLM для задач ФСП не берём)"]
    if taxonomy_skills is not None and spec.skill not in taxonomy_skills:
        return [f"навыка {spec.skill} нет в справочнике"]
    return constructor.autocheck(SpecFamily(spec, slug="fsp-check", skill_type="hard"))


def check_bank(bank: dict[str, Any], *, taxonomy_skills: set[str] | None = None) -> list[str]:
    errs = check_header(bank)
    if not isinstance(bank.get("tasks"), list):
        return errs
    slugs: set[str] = set()
    cid = str((bank.get("competition") or {}).get("id", ""))
    for i, t in enumerate(bank["tasks"], start=1):
        form = (t or {}).get("form")
        if not isinstance(form, dict):
            errs.append(f"задача {i}: нет form")
            continue
        slug = t.get("slug") or slug_of(cid, form)
        if slug in slugs:
            errs.append(f"задача {i}: повтор slug {slug}")
        slugs.add(slug)
        errs += [
            f"задача {i} ({slug}): {e}" for e in check_task(form, taxonomy_skills=taxonomy_skills)
        ]
    return errs


async def import_bank(
    session: AsyncSession, bank: dict[str, Any], cfg: AssessmentConfig, *, to_pilot: bool = False
) -> Counter:
    """Счётчики: `created`, `unchanged`, `kept` (slug есть, содержимое другое), `failed_check`."""
    errs = check_header(bank)
    if errs:
        raise BankError("; ".join(errs))
    comp = bank["competition"]
    cid = str(comp["id"])
    out: Counter = Counter()
    for t in bank["tasks"]:
        form = t["form"]
        slug = t.get("slug") or slug_of(cid, form)
        d = digest(comp, form)
        row = await session.scalar(select(FamilyRow).where(FamilyRow.slug == slug))
        if row is not None:
            same = row.source == SOURCE and (row.spec or {}).get("fsp", {}).get("digest") == d
            out["unchanged" if same else "kept"] += 1
            continue
        types = await taxonomy.skill_types_of(session, [str(form.get("skill", ""))])
        if check_task(form, taxonomy_skills=set(types)):
            out["failed_check"] += 1
            continue
        spec = FamilySpec.model_validate(form)
        row = FamilyRow(
            id=uuid.uuid5(NAMESPACE, slug),
            slug=slug,
            kind=spec.kind.value,
            source=SOURCE,
            skill_id=taxonomy.skill_id(spec.skill),
            skill_type=types[spec.skill].value,
            level=spec.level,
            b=cfg.prior_b(spec.level),
            status="draft",
            spec={
                "form": spec.model_dump(mode="json"),
                "author": spec.model_dump(mode="json"),
                "autocheck": {"ok": True, "seeds": constructor.CHECK_SEEDS},
                "fsp": {
                    "competition": {k: comp.get(k) for k in ("id", "title", "year", "url")},
                    "license": comp["license"],
                    "permission": comp.get("permission"),
                    "digest": d,
                },
            },
            key_status="approved",
            competition_id=cid,
            stats={},
        )
        session.add(row)
        await session.flush()
        if to_pilot:
            await lifecycle.to_pilot(session, row, cfg)
        out["created"] += 1
    await session.flush()
    return out


# --- CLI --------------------------------------------------------------------------------------


def bank_files(base: Path = BANK_DIR) -> list[Path]:
    return sorted(base.glob("*.yaml")) if base.is_dir() else []


def check_files(paths: list[Path], taxonomy_skills: set[str] | None = None) -> list[str]:
    errs: list[str] = []
    for p in paths:
        try:
            errs += [f"{p.name}: {e}" for e in check_bank(load(p), taxonomy_skills=taxonomy_skills)]
        except (BankError, yaml.YAMLError) as e:
            errs.append(f"{p.name}: {e}")
    return errs


async def _import(paths: list[Path], to_pilot: bool) -> int:
    from fsp_platform.db import make_engine, make_session_factory, session_scope

    from app.assessment.config import load_config
    from app.config import Settings

    settings = Settings()
    cfg = load_config(settings.scoring_config_path or None)
    engine = make_engine(settings.database_url)
    try:
        async with session_scope(make_session_factory(engine)) as session:
            for p in paths:
                res = await import_bank(session, load(p), cfg, to_pilot=to_pilot)
                print(f"{p.name}: {dict(res)}")
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Банк задач ФСП (E32-6)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "import"):
        sp = sub.add_parser(name)
        sp.add_argument("files", nargs="*", type=Path)
        if name == "import":
            sp.add_argument("--pilot", action="store_true")
    args = p.parse_args(argv)
    paths = args.files or bank_files()
    if args.cmd == "check":
        errs = check_files(paths)
        for e in errs:
            print(f"FAIL {e}", file=sys.stderr)
        print(f"fsp-bank: банков {len(paths)} — {'OK' if not errs else f'ошибок: {len(errs)}'}")
        return 1 if errs else 0
    return asyncio.run(_import(paths, args.pilot))


if __name__ == "__main__":
    raise SystemExit(main())
