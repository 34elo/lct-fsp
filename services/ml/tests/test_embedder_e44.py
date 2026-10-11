"""Источник модели, префиксы e5, fallback и /healthz (без загрузки настоящей модели)."""

import threading

from fastapi.testclient import TestClient
from fsp_contracts.ml import EmbeddingsRequest
from fsp_ml import embedder as emb
from fsp_ml.config import Settings
from fsp_ml.main import build_app
from fsp_ml.taxonomy import TaxonomyProvider


def test_prefix_only_for_e5():
    assert emb.with_prefix(["a"], "query", "multilingual-e5-small") == ["query: a"]
    assert emb.with_prefix(["a"], "passage", "multilingual-e5-small") == ["passage: a"]
    assert emb.with_prefix(["a"], "query", "bge-m3") == ["a"]


def test_resolve_source(tmp_path):
    assert emb.resolve_source(str(tmp_path), "bge-m3") == str(tmp_path)
    assert emb.resolve_source("", "multilingual-e5-small", autoload=True) == (
        "intfloat/multilingual-e5-small"
    )
    assert emb.resolve_source("", "multilingual-e5-small", "org/x", autoload=True) == "org/x"
    assert emb.resolve_source("", "multilingual-e5-small", autoload=False) == ""
    assert emb.resolve_source("", "bge-m3", autoload=True) == ""  # неизвестное имя — не качаем


def test_load_embedder_without_library_or_source_is_none(monkeypatch):
    assert emb.load_embedder("", "bge-m3") is None

    def boom(*a, **k):
        raise ImportError("sentence_transformers")

    monkeypatch.setattr(emb, "StEmbedder", boom)
    assert emb.load_embedder("", "multilingual-e5-small", autoload=True) is None


class _Real:
    model = "multilingual-e5-small"

    def __init__(self):
        self.kinds = []

    def encode(self, texts, kind="passage"):
        self.kinds.append(kind)
        return [[0.6, 0.8] for _ in texts]


def test_embed_passes_kind_and_falls_back_on_error():
    real = _Real()
    r = emb.embed(EmbeddingsRequest(texts=["x"], kind="query"), real, 4)
    assert real.kinds == ["query"] and r.model == real.model

    class _Bad(_Real):
        def encode(self, texts, kind="passage"):
            raise RuntimeError("oom")

    r = emb.embed(EmbeddingsRequest(texts=["x"], kind="query"), _Bad(), 4)
    assert r.dim == 4  # запасные векторы


def test_lazy_embedder_fallback_then_up():
    gate = threading.Event()
    real = _Real()

    def loader():
        gate.wait(5)
        return real

    lazy = emb.LazyEmbedder("multilingual-e5-small", loader)
    assert not emb.is_ready(lazy)
    assert emb.embed(EmbeddingsRequest(texts=["x"], kind="passage"), lazy, 4).dim == 4
    gate.set()
    assert lazy.wait(5) and emb.is_ready(lazy)
    assert emb.embed(EmbeddingsRequest(texts=["x"], kind="passage"), lazy, 4).dim == 2


def test_lazy_embedder_failed_load_stays_fallback():
    lazy = emb.LazyEmbedder("multilingual-e5-small", lambda: None)
    assert lazy.wait(5) is False and not emb.is_ready(lazy)


def _health(lazy) -> dict:
    app = build_app(Settings(ml_fake=False), embedder=lazy, taxonomy=TaxonomyProvider("", ""))
    return TestClient(app).get("/healthz").json()


def test_healthz_reflects_model_state():
    ok = emb.LazyEmbedder("multilingual-e5-small", lambda: _Real())
    ok.wait(5)
    assert _health(ok)["embedder"] == "up" and _health(ok)["model"] == "multilingual-e5-small"
    bad = emb.LazyEmbedder("multilingual-e5-small", lambda: None)
    bad.wait(5)
    assert _health(bad)["embedder"] == "fallback"


def test_build_app_autoloads_from_model_name(monkeypatch):
    calls = []
    monkeypatch.setattr(emb, "load_embedder", lambda *a, **k: calls.append(a) or None)
    import fsp_ml.main as m

    monkeypatch.setattr(m, "load_embedder", emb.load_embedder)
    s = Settings(ml_fake=False, embedding_model="multilingual-e5-small", embedding_dim=1024)
    app = build_app(s, taxonomy=TaxonomyProvider("", ""))
    assert TestClient(app).get("/healthz").json()["embedder"] == "fallback"
    for _ in range(50):
        if calls:
            break
        threading.Event().wait(0.05)
    assert calls and calls[0][1] == "multilingual-e5-small"
