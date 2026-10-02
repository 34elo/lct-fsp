import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("new_service", ROOT / "tools/new_service.py")
ns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ns)


def test_create_from_template(tmp_path):
    target = ns.create("demo", tmp_path)
    assert (target / "pyproject.toml").read_text().count('name = "fsp-demo"') == 1
    assert (target / "AGENTS.md").exists() and not list(target.rglob("*.tmpl"))
    assert len((target / "AGENTS.md").read_text().splitlines()) <= 40
    assert "__NAME__" not in "".join(p.read_text() for p in target.rglob("*") if p.is_file())
    # сервис из шаблона поднимается и отвечает на /healthz
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(target),
            "-c",
            "/dev/null",
            str(target / "tests"),
        ],
        cwd=target,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(target)},
    )
    assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]


def test_rejects_bad_name_and_duplicate(tmp_path):
    with pytest.raises(ValueError):
        ns.create("Bad_Name", tmp_path)
    ns.create("ok", tmp_path)
    with pytest.raises(FileExistsError):
        ns.create("ok", tmp_path)
