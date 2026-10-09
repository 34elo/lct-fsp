"""E42-3: сид на чистом Postgres проходит с первого раза и повторяется без ошибок.

Нужен пустой Postgres с pgvector: `SEED_PG_URL=postgresql+asyncpg://user:pw@host:port/db`
(например, docker run с образом pgvector/pgvector:pg16, POSTGRES_DB=core, порт 29432).
Без переменной тест пропускается.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
URL = os.environ.get("SEED_PG_URL")

pytestmark = pytest.mark.skipif(not URL, reason="нужен SEED_PG_URL (пустой Postgres с pgvector)")


def _run(args: list[str], cwd: Path) -> None:
    env = {**os.environ, "DATABASE_URL": URL or "", "SEED": "20261003"}
    r = subprocess.run(
        [sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=900
    )
    assert r.returncode == 0, f"{args}: {(r.stdout + r.stderr)[-1500:]}"


def test_seed_chain_on_clean_postgres_twice():
    core = ROOT / "services" / "core"
    _run(["-m", "alembic", "upgrade", "head"], core)
    _run(["-m", "app.taxonomy"], core)
    (ROOT / "reports" / "seed").mkdir(parents=True, exist_ok=True)
    for _ in range(2):  # второй проход — идемпотентность (prod-init повторяем)
        for step in ("all", "grades", "families", "demo2"):
            _run(["-m", "tools.seed", step], ROOT)
