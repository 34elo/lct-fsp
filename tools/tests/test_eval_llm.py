"""E32-3: скрипт замера LLM на фейковом OpenAI-совместимом сервере (без GPU и моделей)."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.eval_llm import cases  # noqa: E402
from tools.eval_llm.__main__ import main, schema_errors, skill_verified  # noqa: E402


def _answer(system: str, user: str) -> dict:
    if "извлекаешь факты" in system:
        case = next(r for r in cases.RESUMES if r["text"][:30] in user)
        skills = [{"name": g, "quote": g} for g in case["gold"] if g in case["text"]]
        skills.append({"name": case["trap"][0], "quote": "придумано, в тексте нет"})
        return {"skills": skills, "experience": []}
    if "черновик правильного ответа" in system:
        if "find_bug" in user:
            return {"correct": None, "bug_lines": [3], "rationale": "граница"}
        return {"correct": 1, "bug_lines": None, "rationale": "x"}
    return {"text": "Скорее всего, ошибка в границе. Проверьте, как работает диапазон."}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.path == "/v1/chat/completions"
        msgs = body["messages"]
        out = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            _answer(msgs[0]["content"], msgs[1]["content"]), ensure_ascii=False
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # тишина
        pass


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_report_on_fake_server(server, tmp_path):
    argv = ["--base-url", server, "--model", "fake/model", "--out", str(tmp_path), "--repeats", "2"]
    assert main(argv, environ={}) == 0
    rep = json.loads((tmp_path / "fake_model.json").read_text(encoding="utf-8"))
    s = rep["summary"]
    assert s["resume"]["json_valid"] == 1.0 and s["resume"]["schema_ok"] == 1.0
    assert s["resume"]["skills_recall"] == 1.0
    assert s["resume"]["skills_precision"] == 1.0  # придуманные навыки в TP/FP не попадают
    assert 0 < s["resume"]["hallucinated_share"] < 0.2
    assert s["resume"]["trap_hits"] == len(cases.RESUMES) * 2
    assert s["key"]["key_accuracy"] == pytest.approx(2 / 3, abs=0.001)  # второй choice неверен
    assert s["explain"]["no_leak"] == 1.0 and s["explain"]["length_ok"] == 1.0
    assert s["resume"]["tokens_per_s"] > 0
    assert "p95" in (tmp_path / "fake_model.md").read_text(encoding="utf-8")


def test_unreachable_server(tmp_path, capsys):
    rc = main(
        [
            "--base-url",
            "http://127.0.0.1:1/v1",
            "--model",
            "m",
            "--out",
            str(tmp_path),
            "--timeout",
            "2",
        ],
        environ={},
    )
    assert rc == 2
    assert "недоступна" in capsys.readouterr().err


def test_ml_fake_is_refused(tmp_path, capsys):
    rc = main(["--out", str(tmp_path)], environ={"ML_FAKE": "true", "LLM_BASE_URL": "http://x/v1"})
    assert rc == 2
    assert "ML_FAKE" in capsys.readouterr().err
    assert not list(tmp_path.iterdir())


def test_missing_config(capsys):
    assert main([], environ={}) == 2
    assert "LLM_BASE_URL" in capsys.readouterr().err


def test_env_file_reads_only_llm_keys(server, tmp_path):
    env = tmp_path / "env"
    env.write_text(f"JWT_SECRET=секрет\nLLM_BASE_URL={server}\nLLM_MODEL=from-file\n")
    assert (
        main(
            [
                "--env-file",
                str(env),
                "--out",
                str(tmp_path),
                "--repeats",
                "1",
                "--tasks",
                "explain",
            ],
            environ={},
        )
        == 0
    )
    assert (tmp_path / "from-file.json").exists()
    assert "секрет" not in (tmp_path / "from-file.json").read_text(encoding="utf-8")


def test_skill_verified_rejects_java_in_javascript():
    text = "Немного писал на JavaScript для админок"
    assert skill_verified({"name": "JavaScript", "quote": "писал на JavaScript для"}, text)
    assert not skill_verified({"name": "Java", "quote": "писал на JavaScript для"}, text)
    assert not skill_verified({"name": "Go", "quote": "нет такого в тексте"}, text)


def test_schema_errors():
    assert schema_errors({"skills": [], "experience": []}, cases.RESUME_SCHEMA) == []
    assert schema_errors({"skills": [{"name": "x"}], "experience": []}, cases.RESUME_SCHEMA)
    assert schema_errors({"correct": True, "bug_lines": None, "rationale": ""}, cases.KEY_SCHEMA)
