"""/v1/query/parse не отвечает 503 ни в одном профиле."""

from fastapi.testclient import TestClient
from fsp_ml.config import Settings
from fsp_ml.llm import LlmError
from fsp_ml.main import build_app

BODY = {"text": "Senior бэкенд на Python удалённо до 300 тыс", "taxonomy_version": 1}


class _Llm:
    def __init__(self, answer=None, error=None):
        self.answer, self.error = answer, error

    async def complete_json(self, messages, schema, *, schema_name, temperature=0.0):
        if self.error:
            raise self.error
        return self.answer


def _post(settings, llm=None, body=BODY):
    c = TestClient(build_app(settings, llm=llm))
    r = c.post("/v1/query/parse", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _check_rules(out):
    f = out["filters"]
    assert f["roles"] == ["backend"] and f["grade_min"] == "senior"
    assert f["formats"] == ["remote"] and f["salary_max"] == 300000
    assert f["skills_must"][0]["slug"] == "python"


def test_fake_mode():
    _check_rules(_post(Settings(ml_fake=True)))


def test_real_mode_without_llm():
    out = _post(Settings(ml_fake=False, llm_enabled=False, llm_base_url=""))
    _check_rules(out)
    assert {c["source"] for c in out["chips"]} == {"rule"}


def test_real_mode_llm_enabled_but_unreachable_gives_rules():
    llm = _Llm(error=LlmError("llm_unavailable"))
    out = _post(Settings(ml_fake=False, llm_enabled=True, llm_base_url="http://x"), llm)
    _check_rules(out)


def test_real_mode_llm_fills_gaps_only():
    llm = _Llm(answer={"roles": ["devops"], "grade": "lead", "formats": ["office"]})
    body = {"text": "нужен специалист в офис", "taxonomy_version": 1}
    out = _post(Settings(ml_fake=False, llm_enabled=True, llm_base_url="http://x"), llm, body)
    assert out["filters"]["roles"] == ["devops"] and out["filters"]["grade_min"] == "lead"
    assert out["filters"]["formats"] == ["office"]  # правила нашли «офис» раньше LLM
    llm2 = _Llm(answer={"roles": ["devops"]})
    out2 = _post(Settings(ml_fake=False, llm_enabled=True, llm_base_url="http://x"), llm2)
    assert out2["filters"]["roles"] == ["backend"]  # правила не перезаписываются


def test_real_mode_llm_invalid_answer_gives_rules():
    llm = _Llm(answer={"roles": ["wizard"]})
    out = _post(Settings(ml_fake=False, llm_enabled=True, llm_base_url="http://x"), llm)
    _check_rules(out)
