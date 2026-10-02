import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]


def _alembic(url: str, *args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def test_upgrade_and_downgrade(tmp_path):
    db = tmp_path / "m.db"
    url = f"sqlite+aiosqlite:///{db}"
    _alembic(url, "upgrade", "head")
    tables = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert {
        "outbox",
        "inbox",
        "fsp_links",
        "raw_responses",
        "webhook_log",
        "fsp_link_conflicts",
    } <= tables
    _alembic(url, "downgrade", "base")
    assert "fsp_links" not in set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
