"""Эмбеддер: bge-m3 на CPU, если установлен; иначе фейк при ML_FAKE=true (ml.md §3)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import structlog
from fsp_contracts.ml import EmbeddingsRequest, EmbeddingsResponse

from fsp_ml import fake

log = structlog.get_logger()

MODEL_NAME = "bge-m3"


class Embedder(Protocol):
    model: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class BgeM3Embedder:
    """sentence-transformers, CPU, нормированные векторы. У bge-m3 префиксов query/passage нет."""

    model = MODEL_NAME

    def __init__(self, model_path: str) -> None:
        from sentence_transformers import SentenceTransformer  # необязательная зависимость

        self._st = SentenceTransformer(model_path, device="cpu")

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._st.encode(texts, normalize_embeddings=True, batch_size=16)
        return [[round(float(x), 6) for x in v] for v in vecs]


def load_embedder(model_path: str) -> Embedder | None:
    """Настоящий bge-m3, только если путь задан, существует и библиотека установлена."""
    if not model_path or not Path(model_path).exists():
        return None
    try:
        return BgeM3Embedder(model_path)
    except ImportError:
        log.warning("embedder_lib_missing", lib="sentence_transformers")
    except Exception:  # noqa: BLE001 - битая модель не должна ронять сервис
        log.exception("embedder_load_failed")
    return None


def embed(req: EmbeddingsRequest, real: Embedder | None, dim: int) -> EmbeddingsResponse:
    if real is not None:
        vectors = real.encode(req.texts)
        return EmbeddingsResponse(model=real.model, dim=len(vectors[0]), vectors=vectors)
    return fake.embeddings(req, dim)
