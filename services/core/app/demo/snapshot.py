"""Снапшот и сброс только демо-данных.

Демо — пользователи, компании, вакансии и приглашения с `is_demo` и всё, что на них ссылается
(попытки, грейды, интересы, ФСП-данные в core, события аналитики по псевдониму). Реальные
регистрации и их данные не трогаются.

- `snapshot`: копия «чистых» демо-строк (все ссылки строки — демо или пусто) в таблицы
  `demo_snap__<таблица>` той же БД. Делается на чистой витрине сразу после `make seed`.
- `reset`: в одной транзакции удаляет строки, которые касаются демо (хотя бы одна ссылка — демо:
  в том числе песочницы жюри и приглашения реальных кандидатов от демо-компаний), и возвращает
  строки из снапшота. Секунды, без остановки сервисов.

Работает в PostgreSQL и SQLite (тесты): только `CREATE TABLE AS`, `INSERT … SELECT`, `DELETE`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.service import pseudonym

SNAP = "demo_snap__"
FLAG = "is_demo"

# Множества id: в живых таблицах (что касается демо) и в снапшоте (что вернуть).
_LIVE = {
    "U": "SELECT id FROM users WHERE is_demo",
    "C": "SELECT id FROM companies WHERE is_demo",
    "V": "SELECT id FROM vacancies WHERE is_demo OR company_id IN ({C})",
    "O": "SELECT id FROM offers WHERE is_demo OR company_id IN ({C}) OR candidate_id IN ({U})",
    "A": "SELECT id FROM attempts WHERE candidate_id IN ({U})",
    "T": "SELECT id FROM regular_tasks WHERE company_id IN ({C})",
    "S": "SELECT id FROM category_subscriptions WHERE company_id IN ({C})",
}
_SNAP_OF = {
    "U": "users",
    "C": "companies",
    "V": "vacancies",
    "O": "offers",
    "A": "attempts",
    "T": "regular_tasks",
    "S": "category_subscriptions",
}

# Порядок «родитель раньше ребёнка»: снапшот и вставка — по порядку, удаление — в обратном.
# Таблица → [(колонка, множество)]; множество FLAG — сама строка помечена `is_demo`.
OWNED: list[tuple[str, list[tuple[str, str]]]] = [
    ("users", [(FLAG, FLAG)]),
    ("companies", [(FLAG, FLAG)]),
    ("user_profiles", [("user_id", "U")]),
    ("consents", [("user_id", "U")]),
    ("email_verifications", [("user_id", "U")]),
    ("refresh_tokens", [("user_id", "U")]),
    ("telegram_accounts", [("user_id", "U")]),
    ("notifications", [("user_id", "U")]),
    ("candidates", [("user_id", "U")]),
    ("company_members", [("company_id", "C"), ("user_id", "U")]),
    ("company_invites", [("company_id", "C")]),
    ("needs", [("company_id", "C")]),
    ("category_subscriptions", [("company_id", "C")]),
    ("regular_tasks", [("company_id", "C")]),
    ("vacancies", [(FLAG, FLAG), ("company_id", "C"), ("created_by", "U")]),
    ("vacancy_skills", [("vacancy_id", "V")]),
    ("attempts", [("candidate_id", "U")]),
    ("responses", [("attempt_id", "A")]),
    ("grades", [("candidate_id", "U")]),
    ("surveys", [("candidate_id", "U")]),
    ("candidate_skills", [("candidate_id", "U")]),
    ("evidence", [("candidate_id", "U")]),
    ("resumes", [("candidate_id", "U")]),
    ("education", [("candidate_id", "U")]),
    ("experience", [("candidate_id", "U")]),
    ("category_disputes", [("candidate_id", "U")]),
    ("issued_credentials", [("candidate_id", "U")]),
    ("fsp_participants", [("candidate_id", "U")]),
    ("fsp_ranks", [("candidate_id", "U")]),
    ("fsp_results", [("candidate_id", "U")]),
    ("fsp_team_members", [("candidate_id", "U")]),
    ("candidate_links", [("candidate_a", "U"), ("candidate_b", "U")]),
    ("candidate_interests", [("candidate_id", "U"), ("company_id", "C")]),
    ("category_subscription_hits", [("candidate_id", "U"), ("subscription_id", "S")]),
    ("matches", [("candidate_id", "U"), ("vacancy_id", "V")]),
    ("task_submissions", [("candidate_id", "U"), ("task_id", "T")]),
    (
        "profile_views",
        [("candidate_id", "U"), ("company_id", "C"), ("viewer_user_id", "U"), ("vacancy_id", "V")],
    ),
    ("impressions", [("company_id", "C"), ("user_id", "U"), ("candidate_id", "U")]),
    ("rec_feedback", [("company_id", "C"), ("user_id", "U"), ("candidate_id", "U")]),
    (
        "offers",
        [
            (FLAG, FLAG),
            ("company_id", "C"),
            ("candidate_id", "U"),
            ("vacancy_id", "V"),
            ("created_by", "U"),
        ],
    ),
    ("offer_events", [("offer_id", "O")]),
    ("offer_messages", [("offer_id", "O")]),
    ("offer_tasks", [("offer_id", "O"), ("company_id", "C")]),
    ("complaints", [("offer_id", "O")]),
    ("contact_reveals", [("offer_id", "O")]),
]
EVENTS = "analytics_events"  # по псевдониму `actor` (HMAC id пользователя или компании)

# Песочницы жюри (`jury-<pair>-c|e@`, app.demo.service) в снапшот не входят: сброс их удаляет.
SANDBOX_LIKE = "jury-____________-_@demo.fsp.test"
SNAP_EXTRA = {
    "users": f"email NOT LIKE '{SANDBOX_LIKE}'",
    "companies": (
        "id NOT IN (SELECT m.company_id FROM company_members m JOIN users u ON u.id = m.user_id"
        f" WHERE u.email LIKE '{SANDBOX_LIKE}')"
    ),
}


class SnapshotMissing(RuntimeError):
    """Нет снапшота демо: сначала `make demo-snapshot` на чистой витрине."""


@dataclass
class ResetStats:
    deleted: dict[str, int]
    restored: dict[str, int]
    demo_user_ids: list[uuid.UUID]


def _live(key: str) -> str:
    sql = _LIVE[key]
    return sql.format(U=_LIVE["U"], C=_LIVE["C"]) if "{" in sql else sql


def _snap_set(key: str) -> str:
    return f"SELECT id FROM {SNAP}{_SNAP_OF[key]}"


def delete_where(conds: list[tuple[str, str]]) -> str:
    """Строка касается демо: хотя бы одна ссылка — демо."""
    return " OR ".join(FLAG if s == FLAG else f"{c} IN ({_live(s)})" for c, s in conds)


def snapshot_where(conds: list[tuple[str, str]], extra: str | None = None) -> str:
    """«Чистая» демо-строка: все ссылки — на демо из снапшота (или пусто); без песочниц жюри."""
    parts = [FLAG if s == FLAG else f"({c} IS NULL OR {c} IN ({_snap_set(s)}))" for c, s in conds]
    return " AND ".join([*parts, *([extra] if extra else [])])


async def _tables(session: AsyncSession) -> set[str]:
    def names(sync_conn) -> set[str]:
        from sqlalchemy import inspect

        return set(inspect(sync_conn).get_table_names())

    conn = await session.connection()
    return await conn.run_sync(names)


async def _columns(session: AsyncSession, table: str) -> list[str]:
    res = await session.execute(text(f"SELECT * FROM {table} WHERE 1 = 0"))  # noqa: S608
    return list(res.keys())


async def _actors(session: AsyncSession, salt: str, users: str, companies: str) -> list[str]:
    ids = [*await session.scalars(text(users)), *await session.scalars(text(companies))]
    return sorted({pseudonym(salt, _uuid(i)) for i in ids})


def _uuid(v: object) -> uuid.UUID:
    return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))


async def has_snapshot(session: AsyncSession) -> bool:
    return f"{SNAP}users" in await _tables(session)


async def snapshot(session: AsyncSession, salt: str) -> dict[str, int]:
    """Снять снапшот демо-строк. Старый снапшот заменяется. Возвращает число строк по таблицам."""
    existing = await _tables(session)
    for t in [EVENTS, *(t for t, _ in reversed(OWNED))]:
        if f"{SNAP}{t}" in existing:
            await session.execute(text(f"DROP TABLE {SNAP}{t}"))
    out: dict[str, int] = {}
    for table, conds in OWNED:
        if table not in existing:
            continue
        await session.execute(
            text(
                f"CREATE TABLE {SNAP}{table} AS SELECT * FROM {table} "  # noqa: S608
                f"WHERE {snapshot_where(conds, SNAP_EXTRA.get(table))}"
            )
        )
        out[table] = int(await session.scalar(text(f"SELECT count(*) FROM {SNAP}{table}")) or 0)
    actors = await _actors(session, salt, _snap_set("U"), _snap_set("C"))
    await session.execute(
        text(f"CREATE TABLE {SNAP}{EVENTS} AS SELECT * FROM {EVENTS} WHERE 1 = 0")  # noqa: S608
    )
    if actors:
        res = await session.execute(
            text(
                f"INSERT INTO {SNAP}{EVENTS} SELECT * FROM {EVENTS} WHERE actor IN :a"  # noqa: S608
            ).bindparams(bindparam("a", expanding=True)),
            {"a": actors},
        )
        out[EVENTS] = res.rowcount or 0
    return out


async def snapshot_user_ids(session: AsyncSession) -> list[uuid.UUID]:
    return [_uuid(i) for i in await session.scalars(text(_snap_set("U")))]


async def live_demo_user_ids(session: AsyncSession) -> list[uuid.UUID]:
    return [_uuid(i) for i in await session.scalars(text(_LIVE["U"]))]


async def reset(session: AsyncSession, salt: str) -> ResetStats:
    """Удалить всё, что касается демо, и вернуть демо-строки из снапшота (одна транзакция)."""
    if not await has_snapshot(session):
        raise SnapshotMissing("нет снапшота демо: сначала make demo-snapshot")
    existing = await _tables(session)
    ids = sorted({*await live_demo_user_ids(session), *await snapshot_user_ids(session)}, key=str)
    actors = await _actors(session, salt, _LIVE["U"], _LIVE["C"])
    deleted: dict[str, int] = {}
    if actors:
        res = await session.execute(
            text(f"DELETE FROM {EVENTS} WHERE actor IN :a").bindparams(  # noqa: S608
                bindparam("a", expanding=True)
            ),
            {"a": actors},
        )
        deleted[EVENTS] = res.rowcount or 0
    for table, conds in reversed(OWNED):
        if table not in existing:
            continue
        res = await session.execute(
            text(f"DELETE FROM {table} WHERE {delete_where(conds)}")  # noqa: S608
        )
        deleted[table] = res.rowcount or 0
    restored: dict[str, int] = {}
    for table in [*(t for t, _ in OWNED), EVENTS]:
        if table not in existing or f"{SNAP}{table}" not in existing:
            continue
        live_cols = set(await _columns(session, table))
        cols = ", ".join(c for c in await _columns(session, f"{SNAP}{table}") if c in live_cols)
        res = await session.execute(
            text(
                f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {SNAP}{table}"  # noqa: S608
            )
        )
        restored[table] = res.rowcount or 0
    return ResetStats(deleted=deleted, restored=restored, demo_user_ids=ids)
