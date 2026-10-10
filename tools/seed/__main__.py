"""`python -m tools.seed <команда>` (make seed): демо-витрина по SEED.

plan      — построить план и напечатать сводку (без записи куда-либо)
fsp-mock  — записать JSON с данными fsp-mock (FSP_MOCK_DATA=<файл> для сервиса)
core      — наполнить БД core через его сервисные слои (DATABASE_URL, справочник навыков загружен)
all       — fsp-mock + core
demo2     — демо-данные v2 (E34-1, demo_v2.py): герои, компании, офферы, задания; после grades
families  — демо-очередь допуска заданий (E39-31): профессия × грейд, и предложение новой
            профессии «Разработчик 1С» (E41-17); идемпотентно
grades    — seed-грейды (таблица grades, блок 1); после core, идемпотентно
fsp-registry — демо-реестр ФСП в БД fsp-connector (FSP_CONNECTOR_DATABASE_URL; E39-28)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from .plan import ROOT, build_plan, load_config

DEFAULT_MOCK = ROOT / "reports" / "seed" / "fsp-mock.json"


def summary(plan: dict) -> dict:
    cands = plan["candidates"]
    return {
        "seed": plan["seed"],
        "anchor": plan["anchor"],
        "hash": plan["hash"],
        "candidates": len(cands),
        "candidates_with_fsp": sum(1 for c in cands if c["fsp"]),
        "candidates_with_github": sum(
            1 for c in cands if any(e["source"] == "github" for e in c["evidence"])
        ),
        "candidates_with_tests": sum(
            1 for c in cands if any(e["source"] == "test" for e in c["evidence"])
        ),
        "companies": len(plan["companies"]),
        "vacancies": len(plan["vacancies"]),
        "offers_planned": len(plan["offers"]),
        "fsp": {k: len(v) for k, v in plan["fsp"].items()},
    }


def write_mock(plan: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(plan["fsp"], ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
    )
    return out


async def seed_core(plan: dict) -> dict:
    from app.config import Settings
    from fsp_platform.db import make_engine, make_session_factory

    from .jury import seed_jury
    from .loader import Seeder

    cfg = load_config()
    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        seeder = Seeder(
            plan,
            make_session_factory(engine),
            password=cfg["demo"]["password"],
            pseudo_secret=settings.pseudo_id_secret,
            analytics_salt=settings.analytics_salt,
        )
        stats = await seeder.run()
        stats.update(
            await seed_jury(
                make_session_factory(engine),
                password=cfg["demo"]["password"],
                pseudo_secret=settings.pseudo_id_secret,
            )
        )
        return stats
    finally:
        await engine.dispose()


async def seed_grades_cmd(plan: dict) -> dict:
    from app.config import Settings
    from app.identity import service as identity
    from app.identity.models import User
    from fsp_platform.db import make_engine, make_session_factory, session_scope
    from sqlalchemy import select

    from .grades import seed_grades

    engine = make_engine(Settings().database_url)
    try:
        factory = make_session_factory(engine)
        async with session_scope(factory) as s:
            rows = await s.execute(select(User.email, User.id))
            by_email = {e: i for e, i in rows}
        user_ids = {
            c["key"]: by_email[identity.normalize_email(c["email"])]
            for c in plan["candidates"]
            if identity.normalize_email(c["email"]) in by_email
        }
        return await seed_grades(factory, plan, user_ids)
    finally:
        await engine.dispose()


async def seed_families_cmd() -> dict:
    from app.config import Settings
    from fsp_platform.db import make_engine, make_session_factory

    from .families import seed_families
    from .professions import seed_profession_suggestion

    engine = make_engine(Settings().database_url)
    try:
        factory = make_session_factory(engine)
        return await seed_families(factory) | await seed_profession_suggestion(factory)
    finally:
        await engine.dispose()


async def seed_demo2_cmd(plan: dict) -> dict:
    from app.config import Settings
    from fsp_platform.db import make_engine, make_session_factory

    from .demo_v2 import seed_demo_v2
    from .loader import Seeder

    settings = Settings()
    engine = make_engine(settings.database_url)
    try:
        seeder = Seeder(
            plan,
            make_session_factory(engine),
            password=load_config()["demo"]["password"],
            pseudo_secret=settings.pseudo_id_secret,
            analytics_salt=settings.analytics_salt,
        )
        return await seed_demo_v2(seeder)
    finally:
        await engine.dispose()


def load_env_file(path: Path, db_host_port: str = "28432") -> None:
    """Подгрузить секреты стека из env-файла (.env / .env.demo) в окружение процесса и собрать
    DATABASE_URL на проброшенный порт Postgres. Значения не печатаются; уже заданные env важнее."""
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip("\"'")
    for key in ("PSEUDO_ID_SECRET", "ANALYTICS_SALT", "PII_KEY", "JWT_SECRET"):
        if env.get(key):
            os.environ.setdefault(key, env[key])
    host_port = env.get("POSTGRES_HOST_PORT") or db_host_port
    if env.get("FSPC_DB_PASSWORD"):
        os.environ.setdefault(
            "FSP_CONNECTOR_DATABASE_URL",
            f"postgresql+asyncpg://fspc:{env['FSPC_DB_PASSWORD']}@127.0.0.1:{host_port}"
            "/fsp_connector",
        )
    if env.get("CORE_DB_PASSWORD"):
        os.environ.setdefault(
            "DATABASE_URL",
            f"postgresql+asyncpg://core:{env['CORE_DB_PASSWORD']}@127.0.0.1:{host_port}/core",
        )


def print_accounts(plan: dict) -> None:
    """Демо-аккаунты для README/показа (пароль — тестовый, из tools/seed/config.yaml)."""
    cfg = load_config()
    pwd = cfg["demo"]["password"]
    heroes = [c["email"] for c in plan["candidates"] if c["hero"]]
    owners = [co["email"] for co in plan["companies"][:3]]
    print(f"\nДемо-аккаунты (пароль у всех: {pwd}):")
    print("  кандидаты-герои:", ", ".join(heroes))
    print(
        "  кандидаты:", plan["candidates"][-1]["email"], "и др. (шаблон cand{NNNN}@demo.fsp.test)"
    )
    print("  работодатели:", ", ".join(owners), "и др. (hr{NN}@demo.fsp.test)")
    print("  админ:", cfg["demo"]["admin_email"])
    print("  жюри:", cfg["demo"]["jury_candidate_email"], cfg["demo"]["jury_employer_email"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.seed", description=__doc__)
    p.add_argument(
        "command",
        choices=["plan", "fsp-mock", "core", "all", "grades", "families", "demo2", "fsp-registry"],
    )
    p.add_argument(
        "--seed", type=int, default=int(os.environ["SEED"]) if os.environ.get("SEED") else None
    )
    p.add_argument(
        "--anchor", type=date.fromisoformat, default=None, help="«сегодня» витрины (YYYY-MM-DD)"
    )
    p.add_argument("--out", type=Path, default=DEFAULT_MOCK, help="файл для данных fsp-mock")
    p.add_argument(
        "--env-file", type=Path, default=None, help="env стека: секреты и DATABASE_URL (.env.demo)"
    )
    args = p.parse_args(argv)
    if args.env_file:
        load_env_file(args.env_file)

    plan = build_plan(seed=args.seed, anchor=args.anchor)
    print(json.dumps(summary(plan), ensure_ascii=False, indent=1))
    if args.command in ("fsp-mock", "all"):
        print(f"fsp-mock: {write_mock(plan, args.out)}")
    if args.command in ("core", "all"):
        try:
            stats = asyncio.run(seed_core(plan))
        except Exception as exc:  # noqa: BLE001 — понятное сообщение вместо трассировки
            print(f"Ошибка наполнения core: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
        print_accounts(plan)
    if args.command == "grades":
        try:
            stats = asyncio.run(seed_grades_cmd(plan))
        except Exception as exc:  # noqa: BLE001
            print(f"Ошибка seed-грейдов: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
    if args.command == "families":
        try:
            stats = asyncio.run(seed_families_cmd())
        except Exception as exc:  # noqa: BLE001
            print(f"Ошибка демо-заданий допуска: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
    if args.command == "demo2":
        try:
            stats = asyncio.run(seed_demo2_cmd(plan))
        except Exception as exc:  # noqa: BLE001
            print(f"Ошибка демо-данных v2: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
    if args.command == "fsp-registry":
        from .fsp_registry import seed_registry

        url = os.environ.get("FSP_CONNECTOR_DATABASE_URL")
        if not url:
            print("Нужен FSP_CONNECTOR_DATABASE_URL или --env-file", file=sys.stderr)
            return 1
        try:
            stats = asyncio.run(seed_registry(url, plan))
        except Exception as exc:  # noqa: BLE001
            print(f"Ошибка демо-реестра ФСП: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
