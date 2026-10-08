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

    def __init__(self, model_path: str, name: str = MODEL_NAME, pad_to: int = 0) -> None:
        self.model = name
        self._pad_to = pad_to
        from sentence_transformers import SentenceTransformer  # необязательная зависимость

        self._st = SentenceTransformer(model_path, device="cpu")

    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._st.encode(texts, normalize_embeddings=True, batch_size=16)
        out = [[round(float(x), 6) for x in v] for v in vecs]
        return pad_vectors(out, self._pad_to)


def load_embedder(model_path: str, name: str = MODEL_NAME, pad_to: int = 0) -> Embedder | None:
    """Настоящий bge-m3, только если путь задан, существует и библиотека установлена."""
    if not model_path or not Path(model_path).exists():
        return None
    try:
        return BgeM3Embedder(model_path, name, pad_to)
    except ImportError:
        log.warning("embedder_lib_missing", lib="sentence_transformers")
    except Exception:  # noqa: BLE001 - битая модель не должна ронять сервис
        log.exception("embedder_load_failed")
    return None


def pad_vectors(vectors: list[list[float]], dim: int) -> list[list[float]]:
    """Малая модель (lite) даёт вектор короче колонки БД: добиваем нулями (косинус не меняется)."""
    return [v + [0.0] * (dim - len(v)) if 0 < len(v) < dim else v for v in vectors]


def embed(req: EmbeddingsRequest, real: Embedder | None, dim: int) -> EmbeddingsResponse:
    if real is not None:
        vectors = real.encode(req.texts)
        return EmbeddingsResponse(model=real.model, dim=len(vectors[0]), vectors=vectors)
    return fake.embeddings(req, dim)
