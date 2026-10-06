"""Анкета кандидата: ленивое создание, псевдоним, pseudo_id, предпочтения, видимость, стоп-лист."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import statistics
import uuid
from datetime import UTC, date, timedelta

import sqlalchemy as sa
from fsp_contracts.enums import EvidenceSource
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import pii
from app.candidates.models import DEFAULT_VISIBILITY, Candidate, CategoryDispute
from app.graph import service as graph
from app.identity.models import utcnow
from app.taxonomy import service as taxonomy

ACTIVE_DAYS = 7
STOPLIST_MAX = 200
STRENGTH_SELF = 0.15  # навык из ручной формы: «заявлено», потолок provisional 0.25 (skills.md)
SELF_FACT = "self_profile"


def make_pseudo_id(secret: str, user_id: uuid.UUID) -> str:
    """HMAC(secret, user_id), 12 символов: по нему нельзя перебрать пользователей."""
    return hmac.new(secret.encode(), str(user_id).encode(), hashlib.sha256).hexdigest()[:12]


def make_pseudonym() -> str:
    """Не зависит от ПДн; роль на момент создания неизвестна, поэтому нейтральный префикс."""
    return f"Candidate #{secrets.randbelow(9000) + 1000}"


async def get_or_create(session: AsyncSession, user_id: uuid.UUID, secret: str) -> Candidate:
    cand = await session.get(Candidate, user_id)
    if cand is not None:
        return cand
    for _ in range(20):  # коллизии 4-значных псевдонимов решаем повтором в savepoint
        cand = Candidate(
            user_id=user_id,
            pseudonym=make_pseudonym(),
            pseudo_id=make_pseudo_id(secret, user_id),
            visibility=dict(DEFAULT_VISIBILITY),
            formats=[],
            employment_types=[],
            stoplist_company_ids=[],
        )
        try:
            async with session.begin_nested():
                session.add(cand)
                await session.flush()
            return cand
        except IntegrityError:
            if cand in session:  # откат savepoint уже мог убрать объект из сессии
                session.expunge(cand)
            existing = await session.get(Candidate, user_id)
            if existing is not None:  # параллельный запрос успел раньше
                return existing
    raise RuntimeError("pseudonym_exhausted")


async def get(session: AsyncSession, user_id: uuid.UUID) -> Candidate | None:
    """Анкета без проверок — для внутренних модулей (подбор)."""
    return await session.get(Candidate, user_id)


async def get_by_pseudo_id(session: AsyncSession, pseudo_id: str) -> Candidate | None:
    return await session.scalar(
        select(Candidate).where(Candidate.pseudo_id == pseudo_id, Candidate.deleted_at.is_(None))
    )


async def update_preferences(session: AsyncSession, cand: Candidate, changes: dict) -> Candidate:
    """Частичное обновление; `search_status=active` ставит active_until=+7д, иной — сбрасывает."""
    for key in ("salary_min", "city", "relocation", "formats", "employment_types"):
        if key in changes:
            value = changes[key]
            if key in ("formats", "employment_types"):
                value = sorted({str(v) for v in value or []})
            setattr(cand, key, value)
    if "search_status" in changes and changes["search_status"] is not None:
        status = str(changes["search_status"])
        cand.search_status = status
        cand.active_until = utcnow() + timedelta(days=ACTIVE_DAYS) if status == "active" else None
    await session.flush()
    return cand


def contacts_of(cand: Candidate, key: str) -> dict[str, str]:
    return pii.decrypt_contacts(key, cand.contacts_enc)


async def update_profile(
    session: AsyncSession, cand: Candidate, changes: dict, *, pii_key: str
) -> Candidate:
    """Ручная форма (E20-4): контакты, стек (`self`), стаж, роли, софт-навыки.

    Частичное обновление по ключам `changes`. Стек — полный список: убранные навыки
    деактивируются. Доказательства, стаж и софт-навыки запускают пересчёт, `profile_version` растёт
    там же, только если агрегат изменился.
    """
    recompute = False
    if "contacts" in changes:
        contacts = {k: v for k, v in (changes["contacts"] or {}).items() if v}
        cand.contacts_enc = pii.encrypt_contacts(pii_key, contacts) if contacts else None
    if "desired_roles" in changes:
        cand.desired_roles = list(dict.fromkeys(str(r) for r in changes["desired_roles"] or []))
    if "experience_months" in changes:
        recompute |= cand.experience_months != changes["experience_months"]
        cand.experience_months = changes["experience_months"]
    if "soft_skills" in changes:
        slugs = list(dict.fromkeys(changes["soft_skills"] or []))
        by_slug = await taxonomy.resolve_slugs(session, slugs)
        _require_known(slugs, by_slug, "soft_skills")
        kinds = await taxonomy.skill_kinds(session, list(by_slug.values()))
        names = await taxonomy.skill_names(session, list(by_slug.values()))
        bad = [s for s in slugs if kinds.get(by_slug[s]) != "soft"]
        if bad:
            raise _skill_error(bad, "soft_skills", "Это не софт-навык")
        soft = [names[by_slug[s]] for s in slugs]
        recompute |= (cand.claimed_soft or []) != soft
        cand.claimed_soft = soft
    if "age_group" in changes or "parent_consent" in changes:
        _set_age(cand, changes)
    if "stack" in changes:
        await _set_stack(session, cand, changes["stack"] or [])  # сам запрашивает пересчёт
    await session.flush()
    if recompute:
        await graph.request_recompute(session, cand.user_id)
    return cand


def _set_age(cand: Candidate, changes: dict) -> None:
    """Возрастная группа и согласие родителя (E32-5b). Дата рождения не хранится.

    Согласие осмысленно только для `minor`; смена группы на `adult` или отзыв сбрасывают отметку.
    """
    group = changes.get("age_group", cand.age_group)
    if group not in (None, "adult", "minor"):
        raise ProblemError(422, "validation_error", "Неизвестная возрастная группа")
    if "parent_consent" in changes and changes["parent_consent"] and group != "minor":
        raise ProblemError(
            422, "validation_error", "Согласие родителя нужно только кандидатам 15–17 лет"
        )
    cand.age_group = group
    if group != "minor" or changes.get("parent_consent") is False:
        cand.parent_consent_at = None
    elif changes.get("parent_consent") and cand.parent_consent_at is None:
        cand.parent_consent_at = utcnow()


def is_publishable(cand: Candidate) -> bool:
    """Профиль 15–17 лет не публикуется без согласия родителя (E32-5b)."""
    return cand.age_group != "minor" or cand.parent_consent_at is not None


def _skill_error(slugs: list[str], field: str, message: str) -> ProblemError:
    return ProblemError(
        422, "unknown_skill", "Неизвестный навык",
        errors=[{"field": field, "message": f"{s}: {message}"} for s in slugs],
    )  # fmt: skip


def _require_known(slugs: list[str], by_slug: dict, field: str) -> None:
    unknown = [s for s in slugs if s not in by_slug]
    if unknown:
        raise _skill_error(unknown, field, "нет в справочнике")


async def _set_stack(session: AsyncSession, cand: Candidate, stack: list[dict]) -> bool:
    items = {str(i["slug"]): i for i in stack}  # дубли: побеждает последний
    by_slug = await taxonomy.resolve_slugs(session, list(items))
    _require_known(list(items), by_slug, "stack")
    kinds = await taxonomy.skill_kinds(session, list(by_slug.values()))
    soft = [s for s in items if kinds.get(by_slug[s]) == "soft"]
    if soft:
        raise _skill_error(soft, "stack", "софт-навыки указываются отдельно")
    wanted = {by_slug[s]: items[s] for s in items}
    today = date.today()
    current = {
        e.skill_id
        for e in await graph.list_active(session, cand.user_id)
        if e.fact_type == SELF_FACT and e.fact_id == cand.user_id
    }
    removed = current - set(wanted)
    changed = False
    if removed:
        changed |= bool(
            await graph.deactivate(
                session, cand.user_id, fact_type=SELF_FACT, fact_id=cand.user_id, skill_ids=removed
            )
        )
    res = await graph.upsert_evidence(
        session,
        cand.user_id,
        [
            graph.EvidenceIn(
                skill_id=sid,
                source=EvidenceSource.self_,
                strength=STRENGTH_SELF,
                observed_at=today,
                fact_type=SELF_FACT,
                fact_id=cand.user_id,
                details={"years": i.get("years")},
                verified=False,
            )
            for sid, i in wanted.items()
        ],
    )
    return changed or res.changed


async def update_visibility(session: AsyncSession, cand: Candidate, changes: dict) -> Candidate:
    cand.visibility = {**DEFAULT_VISIBILITY, **cand.visibility, **changes}
    await session.flush()
    return cand


async def set_stoplist(
    session: AsyncSession, cand: Candidate, company_ids: list[uuid.UUID]
) -> Candidate:
    cand.stoplist_company_ids = sorted({str(c) for c in company_ids})
    await session.flush()
    return cand


def effective_status(cand: Candidate) -> str:
    """«Активно ищу» действует до active_until; потом считается как open."""
    if cand.search_status != "active":
        return cand.search_status
    until = cand.active_until
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return "active" if until is not None and until > utcnow() else "open"


# --- чтение для подбора (matching) -------------------------------------------------------


_PUBLISHABLE = sa.or_(
    Candidate.age_group.is_(None),
    Candidate.age_group != "minor",
    Candidate.parent_consent_at.is_not(None),
)


def _attr_filters(
    stmt: sa.Select, *, salary_cap: float, formats: list[str], company_id: uuid.UUID, pg: bool
) -> sa.Select:
    """Жёсткие фильтры по анкете (ml.md §6.1); массивы — только в PostgreSQL (в SQLite JSON)."""
    stmt = stmt.where(
        Candidate.deleted_at.is_(None),
        Candidate.search_status != "dnd",
        _PUBLISHABLE,
        sa.or_(Candidate.salary_min.is_(None), Candidate.salary_min <= salary_cap),
    )
    if pg:
        arr = postgresql.ARRAY(sa.Text)
        stmt = stmt.where(
            Candidate.formats.op("&&")(sa.cast(formats, arr)),
            sa.not_(
                sa.cast(str(company_id), sa.Text) == sa.func.any(Candidate.stoplist_company_ids)
            ),
        )
    return stmt


async def eligible(
    session: AsyncSession,
    candidate_ids: list[uuid.UUID],
    *,
    salary_cap: float,
    formats: list[str],
    company_id: uuid.UUID,
) -> list[Candidate]:
    """Анкеты из `candidate_ids`, прошедшие жёсткие фильтры по атрибутам."""
    if not candidate_ids:
        return []
    pg = session.bind.dialect.name == "postgresql"
    stmt = _attr_filters(
        select(Candidate).where(Candidate.user_id.in_(candidate_ids)),
        salary_cap=salary_cap, formats=formats, company_id=company_id, pg=pg,
    )  # fmt: skip
    return list(await session.scalars(stmt))


async def nearest_by_embedding(
    session: AsyncSession,
    vector: list[float],
    *,
    limit: int,
    salary_cap: float,
    formats: list[str],
    company_id: uuid.UUID,
) -> list[Candidate]:
    """Отбор по смыслу (matching.md §3, B): `embedding <=> :vec`; только PostgreSQL + pgvector."""
    if session.bind.dialect.name != "postgresql":
        return []
    dist = Candidate.embedding.op("<=>")(vector)
    stmt = _attr_filters(
        select(Candidate).where(Candidate.embedding.is_not(None)),
        salary_cap=salary_cap, formats=formats, company_id=company_id, pg=True,
    ).order_by(dist).limit(limit)  # fmt: skip
    return list(await session.scalars(stmt))


# --- каталог для поиска работодателя (E7-3) ----------------------------------------------

GRADE_ORDER = ("intern", "junior", "junior_plus", "middle", "middle_plus", "senior", "lead")


async def catalog_version(session: AsyncSession) -> str:
    """Версия каталога для ключа кеша выдачи: меняется при любой правке анкеты и пересчёте."""
    n, last = (
        await session.execute(
            select(sa.func.count(), sa.func.max(Candidate.updated_at)).where(
                Candidate.deleted_at.is_(None)
            )
        )
    ).one()
    return hashlib.sha1(f"{n}:{last}".encode()).hexdigest()[:10]


async def search_pool(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    roles: list[str] | None = None,
    grades: list[str] | None = None,
    salary_max: int | None = None,
    formats: list[str] | None = None,
    employment_types: list[str] | None = None,
    cities: list[str] | None = None,
    relocation_ok: bool | None = None,
    active_only: bool = False,
) -> list[Candidate]:
    """Каталог: видимые анкеты по фильтрам анкеты (скаляры — SQL, массивы — в памяти)."""
    stmt = select(Candidate).where(
        Candidate.deleted_at.is_(None),
        Candidate.search_status != "dnd",
        _PUBLISHABLE,
        Candidate.primary_role.is_not(None),
    )
    if roles:
        stmt = stmt.where(Candidate.primary_role.in_(roles))
    if grades is not None:
        stmt = stmt.where(Candidate.grade.in_(grades))
    if salary_max is not None:  # без указанной вилки кандидат подходит под любой бюджет
        stmt = stmt.where(
            sa.or_(Candidate.salary_min.is_(None), Candidate.salary_min <= salary_max)
        )
    if relocation_ok:
        stmt = stmt.where(Candidate.relocation.is_(True))
    lowered = {c.casefold() for c in cities or ()}
    me = str(company_id)
    out: list[Candidate] = []
    for c in await session.scalars(stmt.order_by(Candidate.user_id)):
        if me in (c.stoplist_company_ids or ()):
            continue
        if formats and not set(formats) & set(c.formats or ()):
            continue
        if employment_types and not set(employment_types) & set(c.employment_types or ()):
            continue
        if lowered and (c.city or "").casefold() not in lowered and not c.relocation:
            continue
        if active_only and effective_status(c) != "active":
            continue
        out.append(c)
    return out


MEDIAN_MIN_SAMPLE = 3


async def category_median(session: AsyncSession, role: str | None, grade: str | None) -> int | None:
    """Медиана `salary_min` по ячейке role×grade (ml.md §6.5); мало данных — None."""
    if not role or not grade:
        return None
    stmt = select(Candidate.salary_min).where(
        Candidate.deleted_at.is_(None), Candidate.primary_role == role,
        Candidate.grade == grade, Candidate.salary_min.is_not(None),
    )  # fmt: skip
    vals = list((await session.execute(stmt)).scalars())
    return int(statistics.median(vals)) if len(vals) >= MEDIAN_MIN_SAMPLE else None


async def open_dispute(session: AsyncSession, candidate_id: uuid.UUID) -> CategoryDispute | None:
    return await session.scalar(
        select(CategoryDispute)
        .where(CategoryDispute.candidate_id == candidate_id, CategoryDispute.resolved_at.is_(None))
        .order_by(CategoryDispute.created_at.desc())
        .limit(1)
    )


async def add_dispute(
    session: AsyncSession, cand: Candidate, *, role: str, grade: str, comment: str | None
) -> CategoryDispute:
    """Запись для модерации + событие `category.disputed` (комментарий в событие не идёт)."""
    from fsp_contracts.enums import Grade, RoleSlug
    from fsp_contracts.envelope import new_envelope
    from fsp_contracts.events import CategoryDisputed
    from fsp_platform.outbox import add_to_outbox

    if await open_dispute(session, cand.user_id) is not None:
        raise ProblemError(409, "dispute_exists", "Оспаривание уже на рассмотрении")
    row = CategoryDispute(
        id=uuid.uuid4(), candidate_id=cand.user_id, claimed_role=role, claimed_grade=grade,
        comment=(comment or "").strip() or None,
    )  # fmt: skip
    session.add(row)
    await session.flush()
    event = CategoryDisputed(
        dispute_id=row.id, candidate_id=cand.user_id,
        claimed_role=RoleSlug(role), claimed_grade=Grade(grade),
    )  # fmt: skip
    await add_to_outbox(session, new_envelope("category.disputed", "core", event), cand.user_id)
    return row


# --- удаление профиля (F13, 152-ФЗ) -------------------------------------------------------


async def erase(session: AsyncSession, storage, user) -> Candidate:
    """Необратимо удалить профиль: ПДн и доказательства стираются, анкета остаётся обезличенной.

    Строка `candidates` сохраняется как «надгробие» с псевдонимом: на неё ссылаются офферы и
    таблицы блока 2 (в офферах остаётся только псевдоним, flows.md F13). `deleted_at` скрывает
    кандидата из подбора. Чужие зоны (подбор, офферы, Telegram, ФСП, бейджи, просмотры, кеши)
    чистят свои данные по событию `candidate.deleted`. Повторный вызов — 404 (в роутере).
    """
    from fsp_contracts import new_envelope
    from fsp_contracts.enums import ConsentType
    from fsp_contracts.events import CandidateDeleted
    from fsp_platform.outbox import add_to_outbox

    from app.assessment import service as assessment
    from app.consents import service as consents
    from app.identity import service as identity
    from app.resumes import service as resumes

    cand = await session.get(Candidate, user.id, with_for_update=True)
    if cand is None or cand.deleted_at is not None:
        raise ProblemError(404, "candidate_not_found", "Профиль не найден")
    cid = cand.user_id
    await resumes.erase_candidate(session, storage, cid)
    await assessment.erase_candidate(session, cid)
    await graph.erase_candidate(session, cid)
    await session.execute(sa.delete(CategoryDispute).where(CategoryDispute.candidate_id == cid))
    active = await consents.active(session, cid)
    await consents.set_consents(session, cid, [(ConsentType(t), False, None) for t in active])
    for col in (
        "city", "salary_min", "active_until", "primary_role", "roles", "primary_stack", "grade",
        "grade_score", "grade_confidence", "grade_breakdown", "grade_next", "experience_months",
        "profile_text", "profile_text_sha", "embedding", "embedding_model", "team_signals",
        "claimed_soft", "contacts_enc", "desired_roles", "age_group", "parent_consent_at",
        "recompute_requested_at", "recomputed_at",
    ):  # fmt: skip
        setattr(cand, col, None)
    cand.formats, cand.employment_types, cand.stoplist_company_ids = [], [], []
    cand.relocation = False
    cand.search_status = "dnd"
    cand.visibility = {k: False for k in DEFAULT_VISIBILITY}
    cand.profile_version += 1
    cand.deleted_at = utcnow()
    await identity.erase_user(session, user)
    await add_to_outbox(
        session, new_envelope("candidate.deleted", "core", CandidateDeleted(candidate_id=cid)), cid
    )
    await session.flush()
    return cand
