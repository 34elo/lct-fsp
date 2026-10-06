"""Профиль lite (E20-8): LLM_ENABLED=false — резюме разбирается правилами, воркер не требует LLM."""

import pytest
from fsp_ml import resume_parser
from fsp_ml.config import Settings
from fsp_ml.embedder import pad_vectors
from fsp_ml.worker import MlWorker
from tests.test_resume_parser import INDEX, TEXT, TODAY


def test_rules_parse_keeps_only_quoted_skills():
    out = resume_parser.extract_rules(TEXT, INDEX)
    assert out.skills
    parsed = resume_parser.assemble(
        TEXT, out, INDEX, version=resume_parser.RULES_VERSION, today=TODAY
    )
    assert parsed.skills and all(s.quote and s.slug for s in parsed.skills)
    assert all(s.raw.lower() in s.quote.lower() for s in parsed.skills)
    assert parsed.parser_version == "resume-rules-v2"


async def test_parse_resume_without_llm(monkeypatch):
    monkeypatch.setattr(resume_parser, "extract_text", lambda data: TEXT)
    parsed = await resume_parser.parse_resume(b"x", llm=None, index=INDEX, model="-", today=TODAY)
    assert "rules_mode" in parsed.warnings and parsed.skills


def test_worker_starts_without_llm_url_when_disabled():
    w = MlWorker("llm", Settings(ml_fake=False, llm_enabled=False, llm_base_url=""))
    assert w.llm is None
    with pytest.raises(RuntimeError):
        MlWorker("llm", Settings(ml_fake=False, llm_enabled=True, llm_base_url=""))


def test_small_embeddings_padded_to_column_dim():
    assert pad_vectors([[0.6, 0.8]], 4) == [[0.6, 0.8, 0.0, 0.0]]
    assert pad_vectors([[1.0] * 4], 4) == [[1.0] * 4]
    assert pad_vectors([[1.0, 2.0]], 0) == [[1.0, 2.0]]
