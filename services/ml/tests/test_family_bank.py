"""`POST /v1/families/generate` и `/solve` — генератор и решатель (ML_FAKE, LLM)."""

from fastapi.testclient import TestClient
from fsp_ml import family_bank
from fsp_ml.config import Settings
from fsp_ml.llm import LlmError
from fsp_ml.main import build_app
from fsp_platform.app import create_app

KINDS = ["exact", "estimate", "choice", "find_bug", "order", "sjt", "open"]
LLM = Settings(ml_fake=False, llm_enabled=True, llm_base_url="http://llm", llm_model="qwen")


class _Llm:
    def __init__(self, data):
        self.data, self.calls = data, []

    async def complete_json(self, messages, schema, *, schema_name, temperature=0.0):
        self.calls.append((messages, schema_name, temperature))
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def _client(settings: Settings, llm=None) -> TestClient:
    if llm is None:
        return TestClient(build_app(settings))
    app = create_app("ml")
    app.include_router(family_bank.build_router(settings, llm))
    return TestClient(app)


def test_fake_generate_is_deterministic_for_every_kind():
    c = _client(Settings(ml_fake=True))
    for kind in KINDS:
        body = {"skill": "python", "kind": kind, "level": 3, "n": 2}
        a = c.post("/v1/families/generate", json=body).json()
        assert a == c.post("/v1/families/generate", json=body).json()
        assert len(a["specs"]) == 2 and a["model"] == family_bank.FAKE_MODEL
        assert a["specs"][0] != a["specs"][1] or kind not in ("exact", "estimate")


def test_fake_solve_fits_variant():
    c = _client(Settings(ml_fake=True))
    cases = [
        {"kind": "choice", "stem": "?", "options": ["a", "b", "c"]},
        {"kind": "order", "stem": "?", "options": ["a", "b", "c"]},
        {"kind": "find_bug", "stem": "Найдите\n\n 1 | x = 1\n 2 | y = x\n 3 | z"},
        {"kind": "exact", "stem": "2 + 2"},
    ]
    for body in cases:
        r = c.post("/v1/families/solve", json=body).json()
        req = family_bank.FamilySolveRequest.model_validate(body)
        assert family_bank.answer_fits(req, r["answer"]), body
        if body["kind"] == "find_bug":
            assert 1 <= r["answer"][0] <= 3


def test_llm_disabled_returns_503():
    c = _client(Settings(ml_fake=False, llm_enabled=False))
    r = c.post("/v1/families/generate", json={"skill": "python", "kind": "choice", "level": 2})
    assert r.status_code == 503 and r.json()["code"] == "llm_disabled"
    r = c.post("/v1/families/solve", json={"kind": "choice", "stem": "?", "options": ["a", "b"]})
    assert r.status_code == 503 and r.json()["code"] == "llm_disabled"


def test_generate_llm_forces_target_fields():
    spec = {
        "title": "Деление",
        "stem": "Чему равно {{a}} // 2?",
        "options": ["1", "2"],
        "correct": 0,
        "params": {"a": {"values": [2, 3]}},
    }
    llm = _Llm({"specs": [spec, spec]})
    body = {"skill": "python", "kind": "choice", "level": 2, "n": 1}
    r = _client(LLM, llm).post("/v1/families/generate", json=body)
    assert r.status_code == 200
    out = r.json()
    assert len(out["specs"]) == 1 and out["model"] == "qwen"
    s = out["specs"][0]
    assert (s["kind"], s["skill"], s["level"]) == ("choice", "python", 2) and s["correct"] == 0
    msgs, name, temp = llm.calls[0]
    assert name == "family_gen" and temp > 0 and "Навык: python" in msgs[1]["content"]

    bad = _client(LLM, _Llm({"specs": "нет"})).post("/v1/families/generate", json=body)
    assert bad.status_code == 503 and bad.json()["code"] == "llm_invalid"


def test_solve_llm_validates_bounds():
    body = {"kind": "choice", "stem": "?", "options": ["a", "b"]}
    llm = _Llm({"answer": 1})
    r = _client(LLM, llm).post("/v1/families/solve", json=body)
    assert r.status_code == 200 and r.json() == {"answer": 1, "model": "qwen"}
    assert llm.calls[0][1] == "family_solve" and "1. b" in llm.calls[0][0][1]["content"]
    oob = _client(LLM, _Llm({"answer": 5})).post("/v1/families/solve", json=body)
    assert oob.status_code == 503 and oob.json()["code"] == "llm_invalid"
    order = {"kind": "order", "stem": "?", "options": ["a", "b", "c"]}
    assert (
        _client(LLM, _Llm({"answer": [0, 0, 1]})).post("/v1/families/solve", json=order).status_code
        == 503
    )
    down = _client(LLM, _Llm(LlmError("llm_timeout"))).post("/v1/families/solve", json=body)
    assert down.status_code == 503 and down.json()["code"] == "llm_timeout"
