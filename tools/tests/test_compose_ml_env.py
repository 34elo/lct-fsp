"""ml-сервисы получают настройки MinIO (иначе resume_file_unavailable)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ML_SERVICES = ("ml-api", "ml-worker-llm", "ml-worker-code")
S3_VARS = ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET")

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="нужен docker")


def _compose_config() -> dict:
    env = {
        **os.environ,
        # обязательные переменные compose (`${VAR:?...}`): тестовые значения
        **dict.fromkeys(
            re.findall(r"\$\{(\w+):\?", (ROOT / "docker-compose.yml").read_text(encoding="utf-8")),
            "test-value",
        ),
    }
    for k in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_BUCKET"):
        env.pop(k, None)
    out = subprocess.run(
        ["docker", "compose", "--profile", "*", "config", "--format", "json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        pytest.skip(f"docker compose config недоступен: {out.stderr[-300:]}")
    return json.loads(out.stdout)


def test_ml_services_have_s3_env() -> None:
    services = _compose_config()["services"]
    for name in ML_SERVICES:
        env = services[name]["environment"]
        for var in S3_VARS:
            assert env.get(var), f"{name}: нет {var}"
        assert env["S3_ENDPOINT"] == "http://minio:9000"
        assert env["S3_BUCKET"] == "fsp"
