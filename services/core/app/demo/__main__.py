"""`python -m app.demo snapshot|reset` — снапшот и сброс только демо-данных (E40-1).

Вызывается из `infra/scripts/demo.sh` внутри контейнера core-api (`DATABASE_URL`, соль из env).
В stdout — только строки `DEMO_ID <uuid>`: id демо-кандидатов для сброса в fsp-connector
(`python -m fsp_connector.demo`). Сводка — в stderr.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from fsp_platform.db import make_engine, make_session_factory, session_scope

from app.config import Settings
from app.demo import snapshot as snap

CACHE_KEYS = ("c:public:stats",)  # кеши с цифрами, где демо исключено


async def _flush_cache(url: str) -> None:
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(url)
        try:
            await redis.delete(*CACHE_KEYS)
        finally:
            await redis.aclose()
    except Exception as exc:  # noqa: BLE001 — кеш живёт 5 минут и сам истечёт
        print(f"redis: {type(exc).__name__}", file=sys.stderr)


async def run(command: str, settings: Settings) -> int:
    engine = make_engine(settings.database_url)
    started = time.monotonic()
    try:
        factory = make_session_factory(engine)
        async with session_scope(factory) as s:
            if command == "snapshot":
                stats = await snap.snapshot(s, settings.analytics_salt)
                ids = await snap.snapshot_user_ids(s)
                summary = {"snapshot": stats}
            else:
                try:
                    res = await snap.reset(s, settings.analytics_salt)
                except snap.SnapshotMissing as exc:
                    print(str(exc), file=sys.stderr)
                    return 1
                ids = res.demo_user_ids
                summary = {"deleted": res.deleted, "restored": res.restored}
    finally:
        await engine.dispose()
    if command == "reset":
        await _flush_cache(settings.redis_url)
    for i in ids:
        print(f"DEMO_ID {i}")
    summary["seconds"] = round(time.monotonic() - started, 1)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.demo", description=__doc__)
    p.add_argument("command", choices=["snapshot", "reset"])
    args = p.parse_args(argv)
    return asyncio.run(run(args.command, Settings()))


if __name__ == "__main__":
    sys.exit(main())
