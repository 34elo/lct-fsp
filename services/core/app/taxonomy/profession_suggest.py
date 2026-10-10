"""Система предлагает новые профессии (E41-17, skills.md §5.1).

Раз в неделю (`taxonomy.professions.suggest`, core.jobs) кластеризуем устойчивые наборы навыков
в опубликованных вакансиях и запросах работодателей (`needs`):

1. корзина — набор slug'ов навыков вакансии или запроса;
2. сильные пары: поддержка ≥ `PAIR_SUPPORT`, NPMI ≥ `NPMI_MIN` (формула `growth.npmi`);
3. кластер — связная компонента сильных пар из ≥ `MIN_SIZE` навыков, ядро — до `MAX_CORE`
   самых частых;
4. поддержка кластера — корзины, где есть ≥ max(2, ⌈0.6·|ядро|⌉) навыков ядра; нужно
   ≥ `MIN_SUPPORT`;
5. отличие от ближайшей профессии: доля ядра в навыках любой профессии ≤ `MAX_OVERLAP`.

Предложение сохраняется в `profession_suggestions`; отклонённое или принятое запоминается — похожий
кластер (Жаккар ядер ≥ `SAME_JACCARD`) больше не предлагается. «Создать» строит профиль: навыки
ядра (вес 0.5 + 0.5·доля корзин) и, для каждого типа навыка без семейств в банке, навыки этого
типа ближайшей профессии — так тест сразу строится из существующих семейств.

ПДн нет: только slug'и навыков, названия и id вакансий.
"""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from itertools import combinations

import structlog
from fsp_contracts import Envelope
from fsp_contracts.assessment import ProfessionInfo, SkillType
from fsp_platform.app import ProblemError
from fsp_platform.messaging import Consumer, idempotent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.identity.models import utcnow
from app.taxonomy import admin
from app.taxonomy.growth import npmi
from app.taxonomy.models import ProfessionSuggestion, Role, RoleSkill, Skill

log = structlog.get_logger()

PAIR_SUPPORT = 3
NPMI_MIN = 0.3
MIN_SIZE = 3
MAX_CORE = 8
CORE_SHARE = 0.6
MIN_SUPPORT = 3
MAX_OVERLAP = 0.5
SAME_JACCARD = 0.6
MAX_EXAMPLES = 3
_LIVE = ("active", "provisional")


# --- чистая часть: кластеризация ---------------------------------------------------------------


@dataclass(frozen=True)
class Basket:
    """Вакансия (`vacancy_id`, `title`) или запрос работодателя (оба `None`)."""

    skills: frozenset[str]
    vacancy_id: uuid.UUID | None = None
    title: str | None = None


@dataclass
class Cluster:
    skills: list[str]  # ядро по убыванию частоты
    shares: dict[str, float]  # доля корзин кластера с навыком
    support_vacancies: int
    support_needs: int
    nearest: str | None
    overlap: float
    title: str | None
    examples: list[dict] = field(default_factory=list)

    @property
    def support(self) -> int:
        return self.support_vacancies + self.support_needs

    @property
    def key(self) -> str:
        return ",".join(sorted(self.skills))


def strong_pairs(baskets: list[Basket]) -> dict[tuple[str, str], float]:
    n = len(baskets)
    singles: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    for b in baskets:
        singles.update(b.skills)
        pairs.update(combinations(sorted(b.skills), 2))
    out = {}
    for (a, b), n_ab in pairs.items():
        if n_ab >= PAIR_SUPPORT and (v := npmi(n_ab, singles[a], singles[b], n)) >= NPMI_MIN:
            out[(a, b)] = v
    return out


def components(pairs: Iterable[tuple[str, str]]) -> list[set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for a, b in pairs:
        adj[a].add(b)
        adj[b].add(a)
    seen: set[str] = set()
    out = []
    for start in sorted(adj):
        if start in seen:
            continue
        comp, stack = set(), [start]
        while stack:
            x = stack.pop()
            if x not in comp:
                comp.add(x)
                stack.extend(adj[x] - comp)
        seen |= comp
        if len(comp) >= MIN_SIZE:
            out.append(comp)
    return out


def nearest_profession(
    core: set[str], professions: dict[str, set[str]]
) -> tuple[str | None, float]:
    """Профессия с наибольшей долей ядра в своих навыках и эта доля."""
    best: tuple[str | None, float] = (None, 0.0)
    for slug in sorted(professions):
        share = len(core & professions[slug]) / len(core) if core else 0.0
        if share > best[1]:
            best = (slug, share)
    return best


_GRADE_WORDS = re.compile(
    r"\b(junior|middle|senior|lead|team ?lead|principal|стажер|стажёр|младший|старший|ведущий|"
    r"главный|джун|джуниор|мидл|сеньор|синьор)\b\+?",
    re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """«Senior программист 1С (ERP)» → «Программист 1С»."""
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", title)
    t = _GRADE_WORDS.sub(" ", t)
    t = re.sub(r"[\s/|,;:–—-]+$", "", " ".join(t.split()).strip(" -–—/|,;:"))
    return t[:1].upper() + t[1:] if t else ""


def candidate_title(inside: list[Basket]) -> str | None:
    """Самое частое очищенное название вакансий кластера (при равенстве — по алфавиту)."""
    names = Counter(t for b in inside if b.title and (t := clean_title(b.title)))
    if not names:
        return None
    return min(names.items(), key=lambda kv: (-kv[1], kv[0]))[0][:80]


def mine(baskets: list[Basket], professions: dict[str, set[str]]) -> list[Cluster]:
    """Кластеры навыков, которых нет среди профессий; детерминированно по входу."""
    freq: Counter[str] = Counter()
    for b in baskets:
        freq.update(b.skills)
    out = []
    for comp in components(strong_pairs(baskets)):
        core = sorted(comp, key=lambda s: (-freq[s], s))[:MAX_CORE]
        core_set = set(core)
        need = max(2, math.ceil(CORE_SHARE * len(core)))
        inside = [b for b in baskets if len(b.skills & core_set) >= need]
        if len(inside) < MIN_SUPPORT:
            continue
        nearest, overlap = nearest_profession(core_set, professions)
        if overlap > MAX_OVERLAP:
            continue
        in_freq: Counter[str] = Counter()
        for b in inside:
            in_freq.update(b.skills & core_set)
        core = sorted(core, key=lambda s: (-in_freq[s], s))
        vacs = sorted(
            (b for b in inside if b.vacancy_id is not None),
            key=lambda b: (b.title or "", str(b.vacancy_id)),
        )
        examples, titles = [], set()
        for b in vacs:
            if b.title not in titles and len(examples) < MAX_EXAMPLES:
                titles.add(b.title)
                examples.append({"vacancy_id": str(b.vacancy_id), "title": b.title})
        out.append(
            Cluster(
                skills=core,
                shares={s: round(in_freq[s] / len(inside), 3) for s in core},
                support_vacancies=len(vacs),
                support_needs=len(inside) - len(vacs),
                nearest=nearest,
                overlap=round(overlap, 3),
                title=candidate_title(vacs),
                examples=examples,
            )
        )
    out.sort(key=lambda c: (-c.support, c.key))
    return out


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


def core_weight(share: float) -> float:
    """Вес навыка ядра в профиле новой профессии: 0.5 + 0.5·доля, в (0.5, 1]."""
    return round(min(1.0, 0.5 + 0.5 * share), 2)


# --- данные ------------------------------------------------------------------------------------


async def gather(session: AsyncSession) -> list[Basket]:
    """Корзины: опубликованные вакансии (через `vacancies.service`) и запросы работодателей."""
    from app.matching import needs_service
    from app.vacancies import service as vacancies

    live = set(await session.scalars(select(Skill.slug).where(Skill.status.in_(_LIVE))))
    out: list[Basket] = []
    vacs = await vacancies.list_published(session)
    by_vac = await vacancies.skills_of(session, [v.id for v in vacs])
    for v in vacs:
        skills = frozenset(slug for _, slug in by_vac[v.id] if slug in live)
        if skills:
            out.append(Basket(skills, v.id, v.title))
    for skills in await needs_service.skill_sets(session):
        if s := frozenset(skills & live):
            out.append(Basket(s))
    return out


async def profession_skills(session: AsyncSession) -> dict[str, set[str]]:
    prof = set(await session.scalars(select(Role.slug).where(Role.is_profession)))
    rows = await session.execute(
        select(RoleSkill.role, Skill.slug).join(Skill, Skill.id == RoleSkill.skill_id)
    )
    out: dict[str, set[str]] = {p: set() for p in prof}
    for role, slug in rows.all():
        if role in out:
            out[role].add(slug)
    return out


def _fallback_title(skills: list[str], names: dict[str, str]) -> str:
    return f"Специалист: {', '.join(names.get(s, s) for s in skills[:2])}"[:80]


async def refresh(session: AsyncSession) -> dict[str, int]:
    """Одна итерация; идемпотентна. Похожий на открытое предложение кластер обновляет его,
    на отклонённое или принятое — пропускается; открытые предложения майнинга без кластера
    удаляются (сидовые остаются)."""
    clusters = mine(await gather(session), await profession_skills(session))
    names = dict((await session.execute(select(Skill.slug, Skill.name))).all())
    existing = list(await session.scalars(select(ProfessionSuggestion)))
    kept: set[uuid.UUID] = set()
    added = updated = skipped = 0
    for c in clusters:
        same = max(existing, key=lambda r: jaccard(r.skills, c.skills), default=None)
        if same is not None and jaccard(same.skills, c.skills) >= SAME_JACCARD:
            if same.status != "open":
                skipped += 1
                continue
            if same.id in kept:
                continue
            kept.add(same.id)
            row = same
            updated += 1
        else:
            row = ProfessionSuggestion(key=c.key, title="", skills=[], weights={}, examples=[])
            session.add(row)
            existing.append(row)
            added += 1
        row.key, row.skills, row.weights = c.key, c.skills, c.shares
        row.title = c.title or _fallback_title(c.skills, names)
        row.support_vacancies, row.support_needs = c.support_vacancies, c.support_needs
        row.nearest_profession, row.nearest_overlap = c.nearest, c.overlap
        row.examples, row.source = c.examples, "mining"
        await session.flush()
        kept.add(row.id)
    removed = 0
    for r in existing:
        if r.status == "open" and r.source == "mining" and r.id not in kept:
            await session.delete(r)
            removed += 1
    await session.flush()
    return {"added": added, "updated": updated, "skipped": skipped, "removed": removed}


async def seed(
    session: AsyncSession,
    *,
    title: str,
    skills: list[str],
    examples: list[dict],
    support_vacancies: int,
    support_needs: int,
) -> ProfessionSuggestion:
    """Демо-предложение (`source=seed`); идемпотентно по ядру. Ближайшая профессия — по БД."""
    key = ",".join(sorted(skills))
    row = await session.scalar(select(ProfessionSuggestion).where(ProfessionSuggestion.key == key))
    if row is not None:
        return row
    nearest, overlap = nearest_profession(set(skills), await profession_skills(session))
    row = ProfessionSuggestion(
        key=key, title=title, skills=skills, source="seed", examples=examples,
        weights={s: round(max(0.5, 1 - i * 0.1), 3) for i, s in enumerate(skills)},
        support_vacancies=support_vacancies, support_needs=support_needs,
        nearest_profession=nearest, nearest_overlap=round(overlap, 3),
    )  # fmt: skip
    session.add(row)
    await session.flush()
    return row


# --- админка -----------------------------------------------------------------------------------


async def list_open(session: AsyncSession) -> list[ProfessionSuggestion]:
    rows = await session.scalars(
        select(ProfessionSuggestion).where(ProfessionSuggestion.status == "open")
    )
    return sorted(rows, key=lambda r: (-(r.support_vacancies + r.support_needs), r.key))


async def _open(session: AsyncSession, suggestion_id: uuid.UUID) -> ProfessionSuggestion:
    row = await session.get(ProfessionSuggestion, suggestion_id)
    if row is None:
        raise ProblemError(404, "not_found", "Предложение не найдено")
    if row.status != "open":
        raise ProblemError(409, "suggestion_decided", "По предложению уже принято решение")
    return row


def _slug_base(skills: list[str]) -> str:
    parts = [re.sub(r"[^a-z0-9]", "", s.lower()) for s in skills[:2]]
    base = "_".join(p for p in parts if p) or "profession"
    return (base if base[0].isalpha() else f"p_{base}")[:28]


async def free_slug(session: AsyncSession, skills: list[str]) -> str:
    base, n = _slug_base(skills), 1
    slug = base
    while await session.get(Role, slug) is not None:
        n += 1
        slug = f"{base}_{n}"
    return slug


async def build_weights(session: AsyncSession, row: ProfessionSuggestion) -> dict[str, float]:
    """Профиль: ядро + навыки ближайшей профессии для типов, по которым у ядра нет семейств."""
    from app.assessment import service as assessment

    tested = await assessment.tested_skill_ids(session)
    live = {s.slug: s for s in await session.scalars(select(Skill).where(Skill.status.in_(_LIVE)))}
    weights = {s: core_weight(float(row.weights.get(s, 0.0))) for s in row.skills if s in live}
    covered = {live[s].skill_type for s in weights if live[s].id in tested and live[s].skill_type}
    donor = row.nearest_profession
    if donor is None or await session.get(Role, donor) is None:
        counts = Counter(await session.scalars(select(RoleSkill.role)))
        prof = set(await session.scalars(select(Role.slug).where(Role.is_profession)))
        donor = max(sorted(prof), key=lambda p: counts[p], default=None)
    if donor is not None:
        rows = await session.execute(
            select(Skill.slug, Skill.skill_type, RoleSkill.weight)
            .join(Skill, Skill.id == RoleSkill.skill_id)
            .where(RoleSkill.role == donor, Skill.status.in_(_LIVE))
        )
        for slug, stype, w in rows.all():
            if stype in {t.value for t in SkillType} and stype not in covered:
                weights.setdefault(slug, round(float(w), 2))
    return weights


async def accept(
    session: AsyncSession,
    suggestion_id: uuid.UUID,
    actor: uuid.UUID | None,
    *,
    slug: str | None = None,
    title: str | None = None,
) -> tuple[ProfessionSuggestion, ProfessionInfo, int]:
    """«Создать» одной кнопкой: профессия с готовым профилем навыков."""
    row = await _open(session, suggestion_id)
    slug = slug or await free_slug(session, row.skills)
    info, version = await admin.create_profession(
        session, slug, (title or row.title)[:80], await build_weights(session, row)
    )
    row.status, row.profession = "created", info.slug
    row.decided_by, row.decided_at = actor, utcnow()
    await session.flush()
    return row, info, version


async def reject(
    session: AsyncSession, suggestion_id: uuid.UUID, actor: uuid.UUID | None
) -> ProfessionSuggestion:
    row = await _open(session, suggestion_id)
    row.status, row.decided_by, row.decided_at = "rejected", actor, utcnow()
    await session.flush()
    return row


def register(
    consumers: Mapping[str, Consumer], session_factory: async_sessionmaker[AsyncSession]
) -> None:
    @consumers["core.jobs"].on("taxonomy.professions.suggest")
    @idempotent(session_factory, "taxonomy.professions_suggest")
    async def on_suggest(_envelope: Envelope, session: AsyncSession) -> None:
        log.info("profession_suggestions_refreshed", **await refresh(session))
