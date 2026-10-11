import math
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from fsp_ml.config import Settings
from fsp_ml.main import build_app
from fsp_ml.normalize import normalize
from fsp_ml.taxonomy import TaxonomyProvider

TAX = Path(__file__).resolve().parents[3] / "data" / "taxonomy"


def _snapshot(version: int = 3) -> dict:
    skills = yaml.safe_load((TAX / "skills.yaml").read_text())["skills"]
    return {"version": version, "skills": skills}


def _client(fake_mode: bool = True, embedder=None) -> TestClient:
    prov = TaxonomyProvider("", "")
    prov.set_snapshot(_snapshot())
    app = build_app(Settings(ml_fake=fake_mode), embedder=embedder, taxonomy=prov)
    return TestClient(app)


def _resolve(c: TestClient, *raws: str) -> list[dict]:
    r = c.post(
        "/v1/skills/resolve",
        json={"mentions": [{"raw": x} for x in raws], "taxonomy_version": 3},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_normalize_examples():
    assert normalize("Python 3.11") == "python"
    assert normalize("  C++17 ") == "c++"
    assert normalize("Постгрес 15") == "постгрес"
    assert normalize("Ёлка") == "елка"
    assert normalize("1С") == "1с"


def test_exact_synonyms_and_versions():
    out = {
        i["raw"]: i for i in _resolve(_client(), "Python 3.11", "питон", "Джава", "C++17", "golang")
    }
    assert out["Python 3.11"]["skill_slug"] == "python"
    assert out["Python 3.11"]["decision"] == "alias"
    assert out["питон"]["skill_slug"] == "python"
    assert out["Джава"]["skill_slug"] == "java"
    assert out["C++17"]["skill_slug"] == "cpp"
    assert out["golang"]["skill_slug"] == "go"


def test_trap_pairs_not_merged():
    out = _resolve(_client(), "Java", "JavaScript", "C", "C#", "C++")
    assert [i["skill_slug"] for i in out] == ["java", "javascript", "c", "csharp", "cpp"]


def test_fuzzy_typo():
    out = _resolve(_client(), "pythn", "typescipt", "postgresq")[0:3]
    assert [i["decision"] for i in out] == ["fuzzy"] * 3
    assert [i["skill_slug"] for i in out] == ["python", "typescript", "postgresql"]


def test_short_strings_not_fuzzy():
    out = _resolve(_client(), "gi")[0]
    assert out["decision"] != "fuzzy"


def test_unknown_goes_to_stub_pipeline():
    out = _resolve(_client(), "квантовая алхимия")[0]
    assert out["decision"] == "new"


def test_embeddings_fake_shape_and_determinism():
    c = _client()
    body = {"texts": ["a", "b"], "kind": "query"}
    r1 = c.post("/v1/embeddings", json=body).json()
    r2 = c.post("/v1/embeddings", json=body).json()
    assert r1 == r2 and r1["dim"] == 1024 and len(r1["vectors"]) == 2
    assert math.isclose(sum(x * x for x in r1["vectors"][0]), 1.0, abs_tol=1e-3)


def test_embeddings_limit_and_fallback():
    c = _client()
    r = c.post("/v1/embeddings", json={"texts": ["x"] * 129, "kind": "passage"})
    assert r.status_code == 422
    r = _client(fake_mode=False).post("/v1/embeddings", json={"texts": ["x"], "kind": "query"})
    assert r.status_code == 200  # запасные векторы вместо 503 (E42-2)


class _Stub:
    model = "bge-m3"

    def encode(self, texts, kind="passage"):
        return [[1.0, 0.0, 0.0] for _ in texts]


def test_real_embedder_used_when_present():
    c = _client(fake_mode=False, embedder=_Stub())
    r = c.post("/v1/embeddings", json={"texts": ["x"], "kind": "query"}).json()
    assert r["model"] == "bge-m3" and r["dim"] == 3
    assert c.get("/healthz").json()["embedder"] == "up"


def test_resolve_works_without_fake_when_taxonomy_loaded():
    out = _resolve(_client(fake_mode=False), "питон")[0]
    assert out["skill_slug"] == "python"
