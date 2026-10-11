"""Карточки навыков: `data/skills/cards/<skill>.yaml`.

Карточка нужна авторам заданий и для объяснений грейда («Middle: выполнены утверждения 1, 2, 4»).
Движок теста её не читает. Формат:

    schema_version: 1
    skill: sql                    # slug навыка из data/taxonomy, совпадает с именем файла
    type: hard                    # тип навыка; обязан совпадать с типом в справочнике
    summary: Что проверяем одной-двумя фразами.
    levels:                       # наблюдаемые утверждения «умеет …», нумерация с 1 по порядку
      junior: [..., ...]
      middle: [..., ...]
      senior: [..., ...]
    concepts:                     # ключевые понятия навыка, не меньше 3
      - term: Индекс
        note: "структура для быстрого поиска ценой места и медленной записи"
    misconceptions:               # частые заблуждения (материал для дистракторов), не меньше 2
      - claim: "Чем больше индексов, тем быстрее база"
        truth: "каждый индекс замедляет запись"

Проверка: `python -m app.taxonomy.cards` (make cards-check, CI). `--schema` печатает JSON Schema.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from fsp_contracts.assessment import TEST_GRADE_ORDER, SkillType, TestGrade
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.taxonomy.loader import TaxonomyData, TaxonomyError, load_taxonomy, norm_alias

CARD_SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parents[4]
CARDS_DIR = ROOT / "data" / "skills" / "cards"
TAXONOMY_DIR = ROOT / "data" / "taxonomy"

_Text = Field(min_length=3, max_length=300)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Concept(_Strict):
    term: str = Field(min_length=1, max_length=80)
    note: str = _Text


class Misconception(_Strict):
    claim: str = _Text
    truth: str = _Text


class SkillCard(_Strict):
    """Схема карточки навыка, `schema_version` 1."""

    schema_version: int = Field(ge=1, le=CARD_SCHEMA_VERSION)
    skill: str = Field(min_length=1)
    type: SkillType
    summary: str = Field(min_length=10, max_length=400)
    levels: dict[TestGrade, list[str]]
    concepts: list[Concept] = Field(min_length=3)
    misconceptions: list[Misconception] = Field(min_length=2)

    @field_validator("levels")
    @classmethod
    def _levels(cls, v: dict[TestGrade, list[str]]) -> dict[TestGrade, list[str]]:
        if missing := [g.value for g in TEST_GRADE_ORDER if g not in v]:
            raise ValueError(f"нет уровней {missing}")
        seen: set[str] = set()
        for grade in TEST_GRADE_ORDER:
            items = v[grade]
            if not 2 <= len(items) <= 8:
                raise ValueError(f"{grade.value}: нужно от 2 до 8 утверждений")
            for text in items:
                if not 3 <= len(text.strip()) <= 300:
                    raise ValueError(f"{grade.value}: утверждение длиной не 3..300 символов")
                key = norm_alias(text)
                if key in seen:
                    raise ValueError(f"повтор утверждения {text!r}")
                seen.add(key)
        return {g: [t.strip() for t in v[g]] for g in TEST_GRADE_ORDER}

    @field_validator("concepts")
    @classmethod
    def _concepts(cls, v: list[Concept]) -> list[Concept]:
        terms = [norm_alias(c.term) for c in v]
        if len(set(terms)) != len(terms):
            raise ValueError("повтор понятия")
        return v

    def statement(self, grade: TestGrade, n: int) -> str:
        """Утверждение уровня по номеру с 1 (как в объяснении грейда)."""
        return self.levels[grade][n - 1]


def parse_card(path: Path) -> SkillCard:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise TaxonomyError(f"{path.name}: не YAML ({exc})") from exc
    if not isinstance(doc, dict):
        raise TaxonomyError(f"{path.name}: ожидается словарь верхнего уровня")
    try:
        card = SkillCard.model_validate(doc)
    except ValidationError as exc:
        err = exc.errors()[0]
        loc = ".".join(str(p) for p in err["loc"])
        raise TaxonomyError(f"{path.name}: {loc}: {err['msg']}") from exc
    if card.skill != path.stem:
        raise TaxonomyError(f"{path.name}: skill={card.skill!r} не совпадает с именем файла")
    return card


def load_cards(directory: Path, taxonomy: TaxonomyData) -> dict[str, SkillCard]:
    """Читает и проверяет все карточки каталога против справочника. Ошибка — `TaxonomyError`."""
    if not directory.is_dir():
        raise TaxonomyError(f"нет каталога {directory}")
    cards: dict[str, SkillCard] = {}
    for path in sorted(directory.glob("*.yaml")):
        card = parse_card(path)
        expected = taxonomy.skill_types.get(card.skill)
        if expected is None:
            raise TaxonomyError(f"{path.name}: навыка {card.skill!r} нет в справочнике")
        if card.type != expected:
            raise TaxonomyError(
                f"{path.name}: type={card.type.value}, в справочнике {expected.value}"
            )
        cards[card.skill] = card
    return cards


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Проверить карточки навыков")
    p.add_argument("--dir", type=Path, default=CARDS_DIR)
    p.add_argument("--taxonomy", type=Path, default=TAXONOMY_DIR)
    p.add_argument("--schema", action="store_true", help="напечатать JSON Schema карточки")
    args = p.parse_args(argv)
    if args.schema:
        print(json.dumps(SkillCard.model_json_schema(), ensure_ascii=False, indent=2))
        return 0
    try:
        cards = load_cards(args.dir, load_taxonomy(args.taxonomy))
    except TaxonomyError as exc:
        print(f"Ошибка карточки: {exc}", file=sys.stderr)
        return 1
    by_type: dict[str, int] = {}
    for c in cards.values():
        by_type[c.type.value] = by_type.get(c.type.value, 0) + 1
    print(f"карточек {len(cards)}: " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
