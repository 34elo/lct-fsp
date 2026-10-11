"""Банк майнинга → таблица `families` (`source = mutation`).

Идемпотентно: семейство с тем же slug не меняется (выданные варианты пересобираются с тем же
ключом), новое создаётся в `draft` и проходит автопроверку `families-check`. С `to_pilot`
прошедшие автопроверку идут в `pilot`; в `active` — только решением админа по статистике
пилота.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import lifecycle
from app.assessment.config import AssessmentConfig
from app.assessment.families.check import check_family, seeds
from app.assessment.mining.bank import SCHEMA
from app.assessment.mining.family import MinedFamily
from app.assessment.models import FamilyRow
from app.taxonomy import service as taxonomy

NAMESPACE = uuid.UUID("5b0f6a3e-30e3-4c1d-9a51-6d7574617465")
CHECK_SEEDS = 50


def digest(entry: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def family_of(entry: dict[str, Any], bank: dict[str, Any], *, skill_type: str) -> MinedFamily:
    return MinedFamily(
        entry, bank["project"], slug=entry["slug"], skill=bank["skill"], skill_type=skill_type
    )


async def import_bank(
    session: AsyncSession, bank: dict[str, Any], cfg: AssessmentConfig, *, to_pilot: bool = False
) -> Counter:
    """Счётчики: `created`, `unchanged`, `kept` (slug есть, содержимое другое), `failed_check`."""
    if bank.get("schema") != SCHEMA:
        raise ValueError(f"схема банка {bank.get('schema')} ≠ {SCHEMA}")
    skill = bank["skill"]
    types = await taxonomy.skill_types_of(session, [skill])
    if skill not in types:
        raise ValueError(f"навыка {skill} нет в справочнике")
    skill_type = types[skill].value
    slugs = [e["slug"] for e in bank["families"]]
    existing = {
        r.slug: r for r in await session.scalars(select(FamilyRow).where(FamilyRow.slug.in_(slugs)))
    }
    out: Counter = Counter()
    for entry in bank["families"]:
        d = digest(entry)
        row = existing.get(entry["slug"])
        if row is not None:
            same = row.source == "mutation" and (row.spec or {}).get("digest") == d
            out["unchanged" if same else "kept"] += 1
            continue
        fam = family_of(entry, bank, skill_type=skill_type)
        errs = check_family(fam, seeds(CHECK_SEEDS))
        if errs:
            out["failed_check"] += 1
            continue
        row = FamilyRow(
            id=uuid.uuid5(NAMESPACE, entry["slug"]),
            slug=entry["slug"],
            kind=fam.kind.value,
            source="mutation",
            skill_id=taxonomy.skill_id(skill),
            skill_type=skill_type,
            level=fam.level,
            b=cfg.prior_b(fam.level),
            status="draft",
            spec={"mined": entry, "project": bank["project"], "skill": skill, "digest": d},
            key_status="approved",
            stats={},
        )
        session.add(row)
        await session.flush()
        if to_pilot:
            await lifecycle.to_pilot(session, row, cfg)
        out["created"] += 1
    await session.flush()
    return out
