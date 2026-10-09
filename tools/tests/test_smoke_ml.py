"""Смоук ML после деплоя (E42-6): smoke-ml.sh с подменой docker через PATH-заглушку."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infra" / "scripts" / "smoke-ml.sh"
SH = shutil.which("sh")
pytestmark = pytest.mark.skipif(SH is None, reason="нужен POSIX sh")

# ruff: noqa: E501
# Заглушка docker: поведение задают переменные FAKE_*, вид вызова определяет, что отвечать
DOCKER_STUB = r"""#!/bin/sh
case "$*" in
  *"exec -T ml-api python -c"*)
    case "$*" in
      *"/healthz"*) [ "${FAKE_HEALTH:-up}" = fail ] && { echo "connection refused"; exit 1; }
                    echo "{\"llm\":\"up\",\"embedder\":\"${FAKE_EMBEDDER:-up}\",\"model\":\"m\",\"queue_depth\":0}" ;;
      *"/v1/embeddings"*) [ "${FAKE_EMB:-ok}" = fail ] && { echo "HTTP Error 503: Service Unavailable"; exit 1; }; echo ok ;;
      *"/chat/completions"*) [ "${FAKE_LLM:-ok}" = fail ] && { echo "HTTP Error 502: Bad Gateway"; exit 1; }; echo ok ;;
    esac ;;
  *"ps -q bot"*) [ "${FAKE_BOT:-run}" = none ] || echo cid123 ;;
  inspect*) [ "${FAKE_BOT:-run}" = crash ] && echo "false true" || echo "true false" ;;
esac
"""


def run(tmp_path: Path, env_lines: str, **fake: str) -> subprocess.CompletedProcess[str]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "docker"
    stub.write_text(DOCKER_STUB, encoding="utf-8", newline="\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    envf = tmp_path / "env"
    envf.write_text(env_lines, encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "ENV_FILE": str(envf),
        "SMOKE_TRIES": "1",
        "SMOKE_SLEEP": "0",
        **fake,
    }
    return subprocess.run(
        [SH, str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=tmp_path,
        timeout=60,
    )


FULL = "LLM_ENABLED=true\nTG_BOT_TOKEN=123:abc\n"


def test_all_green(tmp_path: Path) -> None:
    r = run(tmp_path, FULL)
    assert r.returncode == 0, r.stderr
    assert "ok bot запущен" in r.stdout and "ok LLM отвечает" in r.stdout


def test_embedder_fallback_is_ok(tmp_path: Path) -> None:
    assert run(tmp_path, FULL, FAKE_EMBEDDER="fallback").returncode == 0


def test_embedder_down_fails(tmp_path: Path) -> None:
    r = run(tmp_path, FULL, FAKE_EMBEDDER="down")
    assert r.returncode == 1 and "FAIL ml-api /healthz: embedder=down" in r.stderr


def test_ml_api_unreachable(tmp_path: Path) -> None:
    r = run(tmp_path, FULL, FAKE_HEALTH="fail")
    assert r.returncode == 1 and "FAIL ml-api /healthz" in r.stderr


def test_embeddings_503(tmp_path: Path) -> None:
    r = run(tmp_path, FULL, FAKE_EMB="fail")
    assert r.returncode == 1 and "FAIL /v1/embeddings: HTTP Error 503" in r.stderr


def test_llm_down_gives_reason(tmp_path: Path) -> None:
    r = run(tmp_path, FULL, FAKE_LLM="fail")
    assert r.returncode == 1
    assert "FAIL LLM: не ответил на короткий запрос (HTTP Error 502" in r.stderr


def test_llm_skipped_when_disabled(tmp_path: Path) -> None:
    r = run(tmp_path, "LLM_ENABLED=false\n", FAKE_LLM="fail")
    assert r.returncode == 0 and "skip LLM" in r.stdout and "skip bot" in r.stdout


def test_bot_crashing_fails(tmp_path: Path) -> None:
    r = run(tmp_path, FULL, FAKE_BOT="crash")
    assert r.returncode == 1 and "FAIL bot" in r.stderr


def test_bot_missing_fails_only_with_token(tmp_path: Path) -> None:
    assert run(tmp_path, FULL, FAKE_BOT="none").returncode == 1
    assert run(tmp_path, "LLM_ENABLED=true\n", FAKE_BOT="none").returncode == 0


def test_deploy_script_syntax() -> None:
    for name in ("deploy.sh", "smoke-ml.sh"):
        subprocess.run([SH, "-n", str(ROOT / "infra" / "scripts" / name)], check=True)
