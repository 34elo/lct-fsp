"""Проверка Mermaid-блоков в условиях заданий.

Фронт рисует блок ```mermaid компонентом `Diagram`; невалидный текст показывается сырым.
Здесь — офлайн-проверка без Node: тип диаграммы известен, скобки и кавычки сбалансированы,
в схеме есть содержимое (для flowchart — хотя бы одна связь). Это не полный разбор Mermaid,
а защита от типовых ошибок генераторов (пустой блок, незакрытая скобка, неизвестный тип).
"""

from __future__ import annotations

import re

FENCE = re.compile(r"^[ \t]*```[ \t]*mermaid[^\n]*\n(.*?)^[ \t]*```[ \t]*$", re.S | re.M | re.I)
TYPES = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram-v2",
    "stateDiagram",
    "erDiagram",
    "gantt",
    "pie",
    "journey",
    "gitGraph",
    "mindmap",
    "timeline",
    "quadrantChart",
    "requirementDiagram",
    "C4Context",
    "sankey-beta",
    "xychart-beta",
    "block-beta",
)
_FLOW_DIRS = {"TB", "TD", "BT", "RL", "LR"}
_EDGE = re.compile(r"(-->|---|-\.->|-\.-|==>|===|--[xo]|<-->|--\s.+?\s-->)")
_PAIRS = {"(": ")", "[": "]", "{": "}"}


def blocks(text: str) -> list[str]:
    """Тексты всех блоков ```mermaid в `text`."""
    return [m.group(1) for m in FENCE.finditer(text)]


def _balanced(src: str) -> str | None:
    stack: list[str] = []
    quote = False
    for ch in src:
        if ch == '"':
            quote = not quote
        elif quote:
            continue
        elif ch in _PAIRS:
            stack.append(_PAIRS[ch])
        elif ch in _PAIRS.values():
            if not stack or stack.pop() != ch:
                return f"лишняя или не та скобка «{ch}»"
    if quote:
        return "не закрыта кавычка"
    if stack:
        return f"не закрыта скобка, ожидается «{stack[-1]}»"
    return None


def check_block(src: str) -> list[str]:
    """Ошибки одного блока (пустой список — валиден)."""
    lines = [
        ln.strip() for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("%%")
    ]
    if lines and lines[0] == "---":  # frontmatter
        try:
            end = lines.index("---", 1)
        except ValueError:
            return ["не закрыт frontmatter"]
        lines = lines[end + 1 :]
    if len(lines) < 2:
        return ["схема пустая: нужен тип диаграммы и содержимое"]
    head = lines[0].split()
    kind = head[0].rstrip(";")
    if kind not in TYPES:
        return [f"неизвестный тип диаграммы «{kind}»"]
    errs: list[str] = []
    body = "\n".join(lines[1:])
    if kind in ("flowchart", "graph"):
        if len(head) > 1 and head[1].rstrip(";") not in _FLOW_DIRS:
            errs.append(f"направление «{head[1]}» не из TB/TD/BT/RL/LR")
        if not _EDGE.search(body):
            errs.append("во flowchart нет ни одной связи")
    if kind == "sequenceDiagram" and not re.search(r"->>|-->>|->|-->|-x|--x", body):
        errs.append("в sequenceDiagram нет ни одного сообщения")
    if (msg := _balanced(body)) is not None:
        errs.append(msg)
    return errs


def check_text(text: str) -> list[str]:
    """Ошибки всех блоков ```mermaid в тексте; незакрытое ограждение тоже ошибка."""
    errs = [f"mermaid #{i}: {e}" for i, b in enumerate(blocks(text), 1) for e in check_block(b)]
    opened = len(re.findall(r"^[ \t]*```", text, re.M))
    if "mermaid" in text.lower() and opened % 2:
        errs.append("mermaid: не закрыто ограждение ```")
    return errs
