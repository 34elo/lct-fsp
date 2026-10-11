"""`POST /v1/families/key-draft` — черновик ключа задания (ML_FAKE, LLM_ENABLED, LLM)."""

from fastapi.testclient import TestClient
from fsp_contracts.ml import FamilyKeyDraftRequest
from fsp_ml import family_key
from fsp_ml.config import Settings
from fsp_ml.llm import LlmError
from fsp_ml.main import build_app
from fsp_platform.app import create_app

CHOICE = {"kind": "choice", "stem": "Чему равно 7 // 2?", "options": ["3", "3.5", "4"]}
SJT = {"kind": "sjt", "stem": "PR на 3000 строк", "actions": ["Разбить", "Одобрить", "Обсудить"]}


def _client(settings: Settings, llm=None) -> TestClient:
    if llm is None:
        return TestClient(build_app(settings))
    app = create_app("ml")  # тот же роутер, но с подставным LLM-клиентом
    app.include_router(family_key.build_router(settings, llm))
    return TestClient(app)


def test_fake_draft_is_deterministic_and_fits():
    c = _client(Settings(ml_fake=True))
    a = c.post("/v1/families/key-draft", json=CHOICE).json()
    assert a == c.post("/v1/families/key-draft", json=CHOICE).json()
    assert 0 <= a["correct"] < 3 and a["model"] == family_key.FAKE_MODEL
    s = c.post("/v1/families/key-draft", json=SJT).json()
    assert len(s["scores"]) == 3 and len(set(s["scores"])) == 3
    o = c.post("/v1/families/key-draft", json={"kind": "open", "stem": "Опишите план"}).json()
    assert o["rubric"]


def test_llm_disabled_returns_503():
    r = _client(Settings(ml_fake=False, llm_enabled=False)).post(
        "/v1/families/key-draft", json=CHOICE
    )
    assert r.status_code == 503 and r.json()["code"] == "llm_disabled"


class _Llm:
    def __init__(self, data):
        self.data, self.calls = data, []

    async def complete_json(self, messages, schema, *, schema_name, temperature=0.0):
        self.calls.append((messages, schema_name))
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def test_real_path_validates_answer():
    s = Settings(ml_fake=False, llm_enabled=True, llm_base_url="http://llm", llm_model="qwen")
    llm = _Llm({"correct": 0, "rationale": "целочисленное деление"})
    r = _client(s, llm).post("/v1/families/key-draft", json=CHOICE)
    assert r.status_code == 200 and r.json()["correct"] == 0 and r.json()["model"] == "qwen"
    msgs, name = llm.calls[0]
    assert name == "family_key" and "1. 3.5" in msgs[1]["content"]

    oob = _client(s, _Llm({"correct": 7})).post("/v1/families/key-draft", json=CHOICE)
    assert oob.status_code == 503 and oob.json()["code"] == "llm_invalid"
    down = _client(s, _Llm(LlmError("llm_timeout"))).post("/v1/families/key-draft", json=CHOICE)
    assert down.status_code == 503 and down.json()["code"] == "llm_timeout"


def test_fits_by_kind():
    req = FamilyKeyDraftRequest(kind="find_bug", stem="x", lines=["a", "b"])
    assert family_key.fits(req, family_key.LlmKeyDraft(bug_lines=[2]))
    assert not family_key.fits(req, family_key.LlmKeyDraft(bug_lines=[3]))
