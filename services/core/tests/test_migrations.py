import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

CORE = Path(__file__).resolve().parents[1]


def _alembic(url: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", *args],
        cwd=CORE,
        check=True,
        capture_output=True,
    )


def test_upgrade_and_downgrade(tmp_path):
    db = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{db}"
    _alembic(url, "upgrade", "head")
    tables = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert {"outbox", "inbox", "alembic_version"} <= tables
    _alembic(url, "downgrade", "base")
    assert "outbox" not in set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())


def test_stage0_migrations_chain(tmp_path):
    """s0_01 → s0_02 → b2_01 (контакты компании): upgrade и пошаговый downgrade."""
    db = tmp_path / "s0.db"
    url = f"sqlite+aiosqlite:///{db}"
    sync = f"sqlite:///{db}"
    heads = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "heads"],
        cwd=CORE,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert heads.count("(head)") == 1 and ("s0_02" in heads or "b2_01" in heads)
    _alembic(url, "upgrade", "head")
    insp = inspect(create_engine(sync))
    assert "grades" in insp.get_table_names()
    assert "email_verified_at" in {c["name"] for c in insp.get_columns("users")}
    # Check that b2_01 migration adds contacts and direction columns to companies
    assert "contacts" in {c["name"] for c in insp.get_columns("companies")}
    assert "direction" in {c["name"] for c in insp.get_columns("companies")}
    _alembic(url, "downgrade", "s0_02")
    insp = inspect(create_engine(sync))
    assert "contacts" not in {c["name"] for c in insp.get_columns("companies")}
    _alembic(url, "downgrade", "s0_01")
    insp = inspect(create_engine(sync))
    assert "email_verified_at" not in {c["name"] for c in insp.get_columns("users")}
    _alembic(url, "downgrade", "0024")
    assert "grades" not in inspect(create_engine(sync)).get_table_names()
