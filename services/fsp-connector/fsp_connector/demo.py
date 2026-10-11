"""Снапшот и сброс демо-привязок ФСП: `python -m fsp_connector.demo snapshot|reset`.

id демо-кандидатов приходят на stdin строками `DEMO_ID <uuid>` (их печатает `python -m app.demo`
в core: в БД core коннектор не ходит). Демо-строки — привязки, конфликты и заявки этих
кандидатов; при сбросе ещё удаляются участники реестра песочниц жюри
(`jury-<pair>-c@demo.fsp.test`, их создаёт core при входе жюри). Реестр и привязки реальных
кандидатов не трогаются. Снапшот — таблицы `demo_snap__<таблица>` той же БД.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Iterable
from uuid import UUID

import sqlalchemy as sa
from fsp_platform.db import make_engine, make_session_factory, session_scope
from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fsp_connector.models import (
    FspLink,
    FspLinkConflict,
    LinkRequest,
    RegistryParticipant,
    RegistryResult,
)

SNAP = "demo_snap__"
TABLES = (FspLink, FspLinkConflict, LinkRequest)
SANDBOX_EMAIL_RE = re.compile(r"^jury-[0-9a-f]{12}-c@demo\.fsp\.test$")


class SnapshotMissing(RuntimeError):
    """Нет снапшота: сначала `make demo-snapshot`."""


def parse_ids(lines: Iterable[str]) -> list[UUID]:
    """`DEMO_ID <uuid>` → UUID; прочие строки (логи) пропускаются."""
    out: list[UUID] = []
    for line in lines:
        head, _, value = line.strip().partition(" ")
        if head == "DEMO_ID":
            try:
                out.append(UUID(value.strip()))
            except ValueError:
                continue
    return out


def _ids_param() -> sa.BindParameter:
    return bindparam("ids", expanding=True, type_=sa.Uuid())


async def _tables(session: AsyncSession) -> set[str]:
    conn = await session.connection()
    return await conn.run_sync(lambda c: set(sa.inspect(c).get_table_names()))


async def snapshot(session: AsyncSession, ids: list[UUID]) -> dict[str, int]:
    existing = await _tables(session)
    out: dict[str, int] = {}
    for model in TABLES:
        t = model.__tablename__
        if f"{SNAP}{t}" in existing:
            await session.execute(text(f"DROP TABLE {SNAP}{t}"))
        await session.execute(text(f"CREATE TABLE {SNAP}{t} AS SELECT * FROM {t} WHERE 1 = 0"))
        if ids:
            res = await session.execute(
                text(
                    f"INSERT INTO {SNAP}{t} SELECT * FROM {t} WHERE candidate_id IN :ids"  # noqa: S608
                ).bindparams(_ids_param()),
                {"ids": ids},
            )
            out[t] = res.rowcount or 0
        else:
            out[t] = 0
    return out


async def reset(session: AsyncSession, ids: list[UUID]) -> dict[str, dict[str, int]]:
    existing = await _tables(session)
    if any(f"{SNAP}{m.__tablename__}" not in existing for m in TABLES):
        raise SnapshotMissing("нет снапшота демо в fsp_connector: сначала make demo-snapshot")
    deleted: dict[str, int] = {}
    for model in TABLES:
        if ids:
            res = await session.execute(delete(model).where(model.candidate_id.in_(ids)))
            deleted[model.__tablename__] = res.rowcount or 0
    rows = await session.execute(
        select(RegistryParticipant.id, RegistryParticipant.email_norm).where(
            RegistryParticipant.email_norm.like("jury-%@demo.fsp.test")
        )
    )
    sandbox = [pid for pid, email in rows if email and SANDBOX_EMAIL_RE.fullmatch(email)]
    if sandbox:
        await session.execute(
            delete(RegistryResult).where(RegistryResult.participant_id.in_(sandbox))
        )
        await session.execute(delete(FspLink).where(FspLink.participant_id.in_(sandbox)))
        await session.execute(
            delete(RegistryParticipant).where(RegistryParticipant.id.in_(sandbox))
        )
    deleted["fsp_reg_participants"] = len(sandbox)
    restored: dict[str, int] = {}
    for model in TABLES:
        t = model.__tablename__
        res = await session.execute(text(f"INSERT INTO {t} SELECT * FROM {SNAP}{t}"))  # noqa: S608
        restored[t] = res.rowcount or 0
    return {"deleted": deleted, "restored": restored}


async def run(command: str, ids: list[UUID], database_url: str) -> dict:
    engine = make_engine(database_url)
    try:
        async with session_scope(make_session_factory(engine)) as s:
            if command == "snapshot":
                return {"snapshot": await snapshot(s, ids)}
            return await reset(s, ids)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    from fsp_connector.config import Settings

    p = argparse.ArgumentParser(prog="fsp_connector.demo", description=__doc__)
    p.add_argument("command", choices=["snapshot", "reset"])
    args = p.parse_args(argv)
    ids = parse_ids(sys.stdin)
    try:
        out = asyncio.run(run(args.command, ids, Settings().database_url))
    except SnapshotMissing as exc:
        print(str(exc), file=sys.stderr)
        return 1
    out["demo_ids"] = len(ids)
    print(json.dumps(out, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
