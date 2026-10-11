"""`POST /v1/assessment/explain` — текст объяснения ошибки (ML_FAKE, LLM_ENABLED, LLM)."""

from fastapi.testclient import TestClient
from fsp_ml import answer_explain
from fsp_ml.config import Settings
from fsp_ml.llm import LlmError
from fsp_ml.main import build_app
from fsp_platform.app import create_app

REQ = {
    "kind": "choice",
    "skill": "python",
    "stem": "Чему равно 7 // 2?",
    "reason_code": "misconception",
    "reason_label": "Ложное представление",
    "misconception": "// возвращает дробь",
    "truth": "// — целочисленное деление",
}


def _client(settings: Settings, llm=None) -> TestClient:
    if llm is None:
        return TestClient(build_app(settings))
    app = create_app("ml")
    app.include_router(answer_explain.build_router(settings, llm))
    return TestClient(app)


class _Llm:
    def __init__(self, data):
        self.data, self.calls = data, []

    async def complete_json(self, messages, schema, *, schema_name, temperature=0.0):
        self.calls.append((messages, schema_name))
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def test_fake_is_deterministic():
    c = _client(Settings(ml_fake=True))
    a = c.post("/v1/assessment/explain", json=REQ).json()
    assert a == c.post("/v1/assessment/explain", json=REQ).json()
    assert a["model"] == answer_explain.FAKE_MODEL and "целочисленное" in a["text"]


def test_llm_disabled_returns_503():
    r = _client(Settings(ml_fake=False, llm_enabled=False)).post("/v1/assessment/explain", json=REQ)
    assert r.status_code == 503 and r.json()["code"] == "llm_disabled"


def test_real_path_validates_schema_and_hides_nothing_extra():
    s = Settings(ml_fake=False, llm_enabled=True, llm_base_url="http://llm", llm_model="qwen")
    llm = _Llm({"text": "Вы, вероятно, считали // обычным делением."})
    r = _client(s, llm).post("/v1/assessment/explain", json=REQ)
    assert r.status_code == 200 and r.json()["model"] == "qwen"
    msgs, name = llm.calls[0]
    assert name == "answer_explain" and "Ложное представление" in msgs[1]["content"]
    bad = _client(s, _Llm({"text": "коротко"})).post("/v1/assessment/explain", json=REQ)
    assert bad.status_code == 503 and bad.json()["code"] == "llm_invalid"
    down = _client(s, _Llm(LlmError("llm_timeout"))).post("/v1/assessment/explain", json=REQ)
    assert down.status_code == 503 and down.json()["code"] == "llm_timeout"
