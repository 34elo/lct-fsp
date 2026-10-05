"""Анкета кандидата: ленивое создание, псевдоним, pseudo_id, предпочтения, видимость, стоп-лист."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import statistics
import uuid
from datetime import UTC, timedelta

import sqlalchemy as sa
from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import DEFAULT_VISIBILITY, Candidate, CategoryDispute
from app.identity.models import utcnow

ACTIVE_DAYS = 7
STOPLIST_MAX = 200


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


def _attr_filters(
    stmt: sa.Select, *, salary_cap: float, formats: list[str], company_id: uuid.UUID, pg: bool
) -> sa.Select:
    """Жёсткие фильтры по анкете (ml.md §6.1); массивы — только в PostgreSQL (в SQLite JSON)."""
    stmt = stmt.where(
        Candidate.deleted_at.is_(None),
        Candidate.search_status != "dnd",
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
