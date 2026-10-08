"""Admin справочника (E13-1a): профессии, веса навыков, карточки навыков.

Каждая правка поднимает версию справочника и пишет `taxonomy.updated` (как `decisions.py`).
Правки профессий через `publish_change` (меняют снимок → меняется хеш). Карточки в снимок не
входят, поэтому версия поднимается принудительно. Карточка админа хранится в `scoring_config`
под ключом `skill_card:<slug>` (JSON формы `SkillCard`, своя версия) и перекрывает файл
`data/skills/cards/<slug>.yaml`; для навыка без файла и правки — черновик ml (`skill_card_drafts`).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fsp_contracts.assessment import ProfessionInfo, SkillType
from fsp_contracts.envelope import new_envelope
from fsp_contracts.events import TaxonomyUpdated
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.taxonomy import service
from app.taxonomy.cards import CARDS_DIR, SkillCard, parse_card
from app.taxonomy.decisions import publish_change
from app.taxonomy.loader import TaxonomyError
from app.taxonomy.models import (
    Role,
    RoleSkill,
    ScoringConfig,
    Skill,
    SkillCardDraftRow,
)

_LIVE = ("active", "provisional")
_PROFESSION_SLUG = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
CARD_PREFIX = "skill_card:"


# --- профессии и веса --------------------------------------------------------------------------


async def _profession(session: AsyncSession, slug: str) -> Role:
    role = await session.get(Role, slug)
    if role is None or not role.is_profession:
        raise ProblemError(404, "not_found", "Профессия не найдена")
    return role


async def _validated_weights(
    session: AsyncSession, weights: dict[str, float]
) -> dict[uuid.UUID, tuple[float, str]]:
    """slug → (id, вес); все навыки живые, веса в (0, 1], покрыты все шесть типов."""
    for slug, w in weights.items():
        if not 0 < w <= 1:
            raise ProblemError(422, "invalid_weight", f"Вес {slug!r} должен быть в (0, 1]")
    skills = {
        s.slug: s
        for s in await session.scalars(
            select(Skill).where(Skill.slug.in_(list(weights)), Skill.status.in_(_LIVE))
        )
    }
    if unknown := sorted(set(weights) - set(skills)):
        raise ProblemError(422, "unknown_skill", f"Нет навыков в справочнике: {unknown}")
    have = {s.skill_type for s in skills.values()}
    if missing := [t.value for t in SkillType if t.value not in have]:
        raise ProblemError(
            422, "missing_skill_types", f"Профессия должна покрывать все типы навыков: {missing}"
        )
    return {skills[slug].id: (w, slug) for slug, w in weights.items()}


async def _info(session: AsyncSession, slug: str) -> ProfessionInfo:
    for p in await service.list_professions(session, include_hidden=True):
        if p.slug == slug:
            return p
    raise ProblemError(404, "not_found", "Профессия не найдена")


async def list_professions(session: AsyncSession) -> list[ProfessionInfo]:
    return await service.list_professions(session, include_hidden=True)  # админ видит и скрытые


async def get_profession(session: AsyncSession, slug: str) -> ProfessionInfo:
    await _profession(session, slug)
    return await _info(session, slug)


async def _write_weights(
    session: AsyncSession, slug: str, ids: dict[uuid.UUID, tuple[float, str]]
) -> list[uuid.UUID]:
    """Заменяет веса роли целиком; правленые и добавленные строки получают `source=admin`."""
    have = {
        x.skill_id: x
        for x in await session.scalars(select(RoleSkill).where(RoleSkill.role == slug))
    }
    changed: list[uuid.UUID] = []
    for sid, row in have.items():
        if sid not in ids:
            await session.delete(row)
            changed.append(sid)
    for sid, (w, _) in ids.items():
        row = have.get(sid)
        if row is None:
            session.add(RoleSkill(role=slug, skill_id=sid, weight=w, source="admin"))
            changed.append(sid)
        elif row.weight != w:
            row.weight, row.source = w, "admin"
            changed.append(sid)
    await session.flush()
    return changed


async def create_profession(
    session: AsyncSession, slug: str, title: str, weights: dict[str, float]
) -> tuple[ProfessionInfo, int]:
    if not _PROFESSION_SLUG.match(slug):
        raise ProblemError(422, "invalid_slug", "Слаг: строчные латинские буквы, цифры, «_»")
    if await session.get(Role, slug) is not None:
        raise ProblemError(409, "profession_exists", "Роль с таким слагом уже есть")
    ids = await _validated_weights(session, weights)
    session.add(Role(slug=slug, name=title, is_profession=True))
    await session.flush()
    changed = await _write_weights(session, slug, ids)
    version = await _bump(session, changed)
    return await _info(session, slug), version


async def update_profession(
    session: AsyncSession,
    slug: str,
    title: str | None,
    weights: dict[str, float] | None,
) -> tuple[ProfessionInfo, int]:
    role = await _profession(session, slug)
    changed: list[uuid.UUID] = []
    if weights is not None:
        changed = await _write_weights(session, slug, await _validated_weights(session, weights))
    if title is not None and title != role.name:
        role.name = title
        await session.flush()
    version = await publish_change(session, changed) or await service.get_version(session)
    return await _info(session, slug), version


async def retire_profession(session: AsyncSession, slug: str) -> int:
    """Снимает признак профессии: роль и веса остаются, новые попытки по ней недоступны."""
    role = await _profession(session, slug)
    role.is_profession = False
    await session.flush()
    return await publish_change(session, []) or await service.get_version(session)


async def _bump(session: AsyncSession, skill_ids: list[uuid.UUID]) -> int:
    """`publish_change`, а если снимок не изменился (карточка) — версия растёт принудительно."""
    if (version := await publish_change(session, skill_ids)) is not None:
        return version
    cfg = await session.get(ScoringConfig, service.KEY)
    version = (cfg.version if cfg else 0) + 1
    if cfg is None:
        session.add(
            ScoringConfig(
                key=service.KEY,
                value={"hash": service.snapshot_hash(await service.build_snapshot(session))},
                version=version,
            )
        )
    else:
        cfg.version = version
    ids = list(dict.fromkeys(skill_ids))
    await add_to_outbox(
        session,
        new_envelope(
            "taxonomy.updated", "core", TaxonomyUpdated(version=version, changed_skill_ids=ids)
        ),
    )
    await session.flush()
    return version


# --- карточки навыков --------------------------------------------------------------------------


@dataclass
class CardView:
    slug: str
    source: str  # admin | file | draft
    version: int
    card: SkillCard


async def _skill(session: AsyncSession, slug: str) -> Skill:
    sk = await session.scalar(select(Skill).where(Skill.slug == slug, Skill.status.in_(_LIVE)))
    if sk is None:
        raise ProblemError(404, "not_found", "Навык не найден")
    return sk


def _file_card(slug: str, directory: Path) -> SkillCard | None:
    path = directory / f"{slug}.yaml"
    if not path.is_file():
        return None
    try:
        return parse_card(path)
    except TaxonomyError:
        return None


async def get_card(session: AsyncSession, slug: str, directory: Path = CARDS_DIR) -> CardView:
    sk = await _skill(session, slug)
    if (row := await session.get(ScoringConfig, CARD_PREFIX + slug)) is not None:
        return CardView(slug, "admin", row.version, SkillCard.model_validate(row.value))
    if (card := _file_card(slug, directory)) is not None:
        return CardView(slug, "file", 0, card)
    if (draft := await session.get(SkillCardDraftRow, sk.id)) is not None:
        return CardView(slug, "draft", 0, SkillCard.model_validate(draft.card))
    raise ProblemError(404, "not_found", "Карточки нет")


def _card_slugs(directory: Path) -> set[str]:
    return {p.stem for p in directory.glob("*.yaml")} if directory.is_dir() else set()


async def list_cards(session: AsyncSession, directory: Path = CARDS_DIR) -> list[CardView]:
    slugs = _card_slugs(directory)
    over = {
        r.key.removeprefix(CARD_PREFIX): r
        for r in await session.scalars(
            select(ScoringConfig).where(ScoringConfig.key.like(CARD_PREFIX + "%"))
        )
    }
    live = {s.slug: s for s in await session.scalars(select(Skill).where(Skill.status.in_(_LIVE)))}
    by_id = {s.id: s.slug for s in live.values()}
    drafts = {
        by_id[d.skill_id]: d
        for d in await session.scalars(select(SkillCardDraftRow))
        if d.skill_id in by_id
    }
    out: list[CardView] = []
    for slug in sorted((slugs | set(over) | set(drafts)) & set(live)):
        if slug in over:
            out.append(
                CardView(
                    slug, "admin", over[slug].version, SkillCard.model_validate(over[slug].value)
                )
            )
        elif (card := _file_card(slug, directory)) is not None:
            out.append(CardView(slug, "file", 0, card))
        elif slug in drafts:
            out.append(CardView(slug, "draft", 0, SkillCard.model_validate(drafts[slug].card)))
    return out


async def put_card(session: AsyncSession, slug: str, card: SkillCard) -> tuple[CardView, int]:
    sk = await _skill(session, slug)
    if card.skill != slug:
        raise ProblemError(422, "card_skill_mismatch", "Поле skill не совпадает с путём")
    if sk.skill_type != card.type.value:
        raise ProblemError(
            422, "card_type_mismatch", f"Тип карточки {card.type.value}, у навыка {sk.skill_type}"
        )
    key, value = CARD_PREFIX + slug, card.model_dump(mode="json")
    row = await session.get(ScoringConfig, key)
    if row is None:
        row = ScoringConfig(key=key, value=value, version=1)
        session.add(row)
    elif row.value != value:
        row.value, row.version = value, row.version + 1
    else:  # без изменений версия справочника не растёт
        return CardView(slug, "admin", row.version, card), await service.get_version(session)
    await session.flush()
    version = await _bump(session, [sk.id])
    return CardView(slug, "admin", row.version, card), version
