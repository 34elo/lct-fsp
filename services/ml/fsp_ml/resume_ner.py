"""Natasha (локальный NER, E30-4): имя, город и организации в строках резюме без LLM.

Модели лежат в пакете (navec + slovnet, ≈ 30 МБ, ≈ 200 МБ RAM после загрузки), сети нет.
Без пакета или при ошибке загрузки всё возвращает пустое: правила работают сами по себе.
Тексты в логи не пишем.
"""

from __future__ import annotations

from functools import cache
from typing import Any

import structlog

log = structlog.get_logger()


@cache
def _tools() -> tuple[Any, Any] | None:
    try:
        from natasha import NewsEmbedding, NewsNERTagger, Segmenter
    except ImportError:
        return None
    try:
        return Segmenter(), NewsNERTagger(NewsEmbedding())
    except Exception:  # noqa: BLE001 — модели недоступны: работаем правилами
        log.warning("natasha_unavailable")
        return None


def available() -> bool:
    return _tools() is not None


def entities(line: str) -> list[tuple[str, str]]:
    """`[(тип, текст)]` для одной строки: PER, ORG, LOC. Строка — чтобы спаны не клеили строки."""
    tools = _tools()
    if tools is None or not line.strip():
        return []
    from natasha import Doc

    segmenter, tagger = tools
    doc = Doc(line)
    doc.segment(segmenter)
    doc.tag_ner(tagger)
    return [(s.type, s.text.strip()) for s in doc.spans]
