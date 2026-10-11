"""Нормализация упоминания навыка: регистр, ё, версии, мусорные символы."""

from __future__ import annotations

import re

_SPACES = re.compile(r"\s+")
# версия в конце или в середине: «python 3.11», «postgres 15», «java 17+», «v2», «c++17»
_VERSION_TAIL = re.compile(r"[\s\-_]*\(?\bv?\d+(?:\.\d+)*\+?\)?$")
_PAREN = re.compile(r"\([^)]*\)")
_EDGE_JUNK = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)
# символы, значимые внутри названия: c++, c#, node.js, ci/cd, 1с:предприятие
_KEEP_EDGE = re.compile(r"(\+\+|\+|#)$")


def light(raw: str) -> str:
    """Регистр, ё → е, схлопнутые пробелы. Версии не трогаем: «1с», «web3» остаются."""
    text = raw.strip().lower().replace("ё", "е")
    return _SPACES.sub(" ", text)


def _strip_edges(text: str) -> str:
    keep = _KEEP_EDGE.search(text)
    tail = keep.group(0) if keep else ""
    core = _EDGE_JUNK.sub("", text[: len(text) - len(tail)] if tail else text)
    return core + tail


def strip_version(text: str) -> str:
    """«python 3.11» → «python», «c++17» → «c++», «postgres 15» → «postgres»."""
    out = _PAREN.sub(" ", text)
    out = _SPACES.sub(" ", out).strip()
    prev = None
    while prev != out:
        prev = out
        stripped = _VERSION_TAIL.sub("", out).strip()
        # не оставляем пустую строку: «3d» или «2fa» — не версия
        if stripped and not (stripped[-1:].isdigit() and stripped == out):
            out = stripped
    return _strip_edges(out)


def normalize(raw: str) -> str:
    """Каноническая форма для поиска по синонимам."""
    return strip_version(light(raw)) or light(raw)


def variants(raw: str) -> list[str]:
    """Формы для точного поиска от самой точной к самой грубой, без повторов."""
    base = light(raw)
    out: list[str] = []
    for v in (base, _strip_edges(base), strip_version(base)):
        if v and v not in out:
            out.append(v)
    return out
