"""Проверка Mermaid-блоков в условиях заданий (families/mermaid.py)."""

import pytest
from app.assessment.families import check, mermaid
from app.assessment.families.base import BaseFamily, Item, Kind

FENCE = "```"


def doc(body: str) -> str:
    return f"Что выведет схема?\n\n{FENCE}mermaid\n{body}\n{FENCE}\n"


GOOD = [
    "flowchart LR\n  A[Запрос] --> B{Кэш?}\n  B -- да --> C[Ответ]\n  B -- нет --> D[(БД)]",
    "graph TD\n  A --> B\n  B --> C",
    "sequenceDiagram\n  Клиент->>Сервер: запрос\n  Сервер-->>Клиент: ответ",
    "stateDiagram-v2\n  [*] --> Новый\n  Новый --> Готово",
]


@pytest.mark.parametrize("body", GOOD)
def test_valid_blocks_pass(body):
    assert mermaid.check_text(doc(body)) == []


@pytest.mark.parametrize(
    ("body", "part"),
    [
        ("flowchart LR", "пустая"),
        ("пирожок\n  A --> B", "неизвестный тип"),
        ("flowchart XX\n  A --> B", "направление"),
        ("flowchart LR\n  A[Запрос --> B", "скобк"),
        ('flowchart LR\n  A --> B["текст]', "кавычк"),
        ("flowchart LR\n  A B C", "нет ни одной связи"),
    ],
)
def test_invalid_blocks_reported(body, part):
    errs = mermaid.check_text(doc(body))
    assert errs and part in " ".join(errs)


def test_text_without_blocks_and_other_fences_ignored():
    assert mermaid.check_text("Что вернёт запрос?\n\n```sql\nSELECT 1;\n```") == []
    assert mermaid.blocks("нет схем") == []


def test_unclosed_fence_reported():
    assert mermaid.check_text(f"{FENCE}mermaid\nflowchart LR\n A --> B\n")


class _Fam(BaseFamily):
    slug = "t"
    kind = Kind.choice
    skill = "python"
    skill_type = "hard"
    level = 1

    def generate(self, rng, world=None):  # pragma: no cover - не используется
        raise NotImplementedError


def test_check_item_flags_bad_mermaid():
    fam = _Fam()
    bad = Item(kind=Kind.choice, stem=doc("flowchart LR\n  A[x --> B"), key=0, options=["a", "b"])
    good = Item(kind=Kind.choice, stem=doc(GOOD[0]), key=0, options=["a", "b"])
    assert any("mermaid" in e for e in check.check_item(fam, bad))
    assert not any("mermaid" in e for e in check.check_item(fam, good))
