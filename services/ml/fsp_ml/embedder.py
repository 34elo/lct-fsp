"""Эмбеддер: sentence-transformers на CPU (e5-small / bge-m3), иначе запасные векторы (ml.md §3).

Модель берётся из локального каталога (`EMBEDDING_MODEL_PATH`) или скачивается с HF в кеш тома
при первом старте (`EMBEDDING_HF_ID`, E44-1). Загрузка идёт в фоне: сервис отвечает сразу, пока
модель не готова — `/healthz`: `fallback`, `/v1/embeddings` отдаёт детерминированные векторы.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Protocol

import structlog
from fsp_contracts.ml import EmbeddingsRequest, EmbeddingsResponse

from fsp_ml import fake

log = structlog.get_logger()

MODEL_NAME = "bge-m3"
# короткое имя модели → репозиторий на HF
HF_IDS = {"multilingual-e5-small": "intfloat/multilingual-e5-small"}
# e5 обучена с префиксами: запрос — "query: ", документ — "passage: "
E5_PREFIX = {"query": "query: ", "passage": "passage: "}


class Embedder(Protocol):
    model: str

    def encode(self, texts: list[str], kind: str = "passage") -> list[list[float]]: ...


def is_e5(name: str) -> bool:
    return "e5" in name.lower()


def with_prefix(texts: list[str], kind: str, name: str) -> list[str]:
    """Для e5 добавляет "query: "/"passage: ", у остальных моделей (bge-m3) текст как есть."""
    if not is_e5(name):
        return texts
    prefix = E5_PREFIX.get(kind, E5_PREFIX["passage"])
    return [prefix + t for t in texts]


class StEmbedder:
    """sentence-transformers, CPU, нормированные векторы, добивка нулями до колонки БД."""

    def __init__(
        self, source: str, name: str = MODEL_NAME, pad_to: int = 0, cache_dir: str = ""
    ) -> None:
        self.model = name
        self._pad_to = pad_to
        from sentence_transformers import SentenceTransformer  # необязательная зависимость

        self._st = SentenceTransformer(source, device="cpu", cache_folder=cache_dir or None)

    def encode(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        vecs = self._st.encode(
            with_prefix(texts, kind, self.model), normalize_embeddings=True, batch_size=16
        )
        out = [[round(float(x), 6) for x in v] for v in vecs]
        return pad_vectors(out, self._pad_to)


BgeM3Embedder = StEmbedder  # прежнее имя


def resolve_source(model_path: str, name: str, hf_id: str = "", autoload: bool = False) -> str:
    """Где брать модель: существующий локальный каталог, иначе HF-репозиторий, иначе пусто."""
    if model_path and Path(model_path).exists():
        return model_path
    if autoload:
        return hf_id or HF_IDS.get(name, name if "/" in name else "")
    return ""


def load_embedder(
    model_path: str,
    name: str = MODEL_NAME,
    pad_to: int = 0,
    hf_id: str = "",
    autoload: bool = False,
    cache_dir: str = "",
) -> Embedder | None:
    """Настоящая модель, только если источник найден и библиотека установлена; иначе None."""
    source = resolve_source(model_path, name, hf_id, autoload)
    if not source:
        return None
    try:
        emb = StEmbedder(source, name, pad_to, cache_dir)
        emb.encode(["прогрев"], "query")  # проверка, что модель реально работает
        log.info("embedder_loaded", model=name, source=source, dim=pad_to)
        return emb
    except ImportError:
        log.warning("embedder_lib_missing", lib="sentence_transformers", model=name)
    except Exception:  # noqa: BLE001 - нет сети/кеша или битая модель не роняют сервис
        log.exception("embedder_load_failed", model=name, source=source)
    return None


class LazyEmbedder:
    """Загружает модель в фоновом потоке; до готовности `ready` ложно, `encode` недоступен."""

    def __init__(self, name: str, loader) -> None:  # noqa: ANN001
        self.model = name
        self._real: Embedder | None = None
        self._done = threading.Event()
        t = threading.Thread(target=self._run, args=(loader,), name="embedder-load", daemon=True)
        t.start()

    def _run(self, loader) -> None:  # noqa: ANN001
        log.info("embedder_loading", model=self.model, hint="первый старт скачивает модель в кеш")
        try:
            self._real = loader()
        finally:
            if self._real is None:
                log.warning("embedder_fallback", model=self.model, reason="модель не загрузилась")
            self._done.set()

    @property
    def ready(self) -> bool:
        return self._real is not None

    def wait(self, timeout: float | None = None) -> bool:
        self._done.wait(timeout)
        return self.ready

    def encode(self, texts: list[str], kind: str = "passage") -> list[list[float]]:
        if self._real is None:
            raise RuntimeError("embedder not ready")
        return self._real.encode(texts, kind)


def pad_vectors(vectors: list[list[float]], dim: int) -> list[list[float]]:
    """Малая модель (lite) даёт вектор короче колонки БД: добиваем нулями (косинус не меняется)."""
    return [v + [0.0] * (dim - len(v)) if 0 < len(v) < dim else v for v in vectors]


def is_ready(real: Embedder | None) -> bool:
    return real is not None and getattr(real, "ready", True)


def configure_hf_cache(cache_dir: str) -> None:
    if cache_dir:
        os.environ.setdefault("HF_HOME", cache_dir)


def embed(req: EmbeddingsRequest, real: Embedder | None, dim: int) -> EmbeddingsResponse:
    if is_ready(real):
        try:
            vectors = real.encode(req.texts, req.kind)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - сбой модели → запасные векторы, не 500
            log.exception("embedder_encode_failed")
        else:
            return EmbeddingsResponse(model=real.model, dim=len(vectors[0]), vectors=vectors)  # type: ignore[union-attr]
    return fake.embeddings(req, dim)
