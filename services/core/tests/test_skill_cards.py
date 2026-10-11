"""Схема карточки навыка и проверка карточек data/skills/cards."""

from pathlib import Path

import pytest
import yaml
from app.taxonomy.cards import CARDS_DIR, TAXONOMY_DIR, SkillCard, load_cards, main, parse_card
from app.taxonomy.loader import TaxonomyError, load_taxonomy
from fsp_contracts.assessment import SkillType, TestGrade


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy(TAXONOMY_DIR)


def _card(**over):
    doc = {
        "schema_version": 1,
        "skill": "sql",
        "type": "hard",
        "summary": "Пишет запросы к реляционной базе.",
        "levels": {
            "junior": ["Пишет SELECT с WHERE", "Соединяет две таблицы"],
            "middle": ["Использует оконные функции", "Читает план выполнения"],
            "senior": ["Ускоряет медленный запрос", "Устраняет взаимные блокировки"],
        },
        "concepts": [
            {"term": "JOIN", "note": "соединение таблиц"},
            {"term": "NULL", "note": "нет значения"},
            {"term": "Индекс", "note": "быстрый поиск"},
        ],
        "misconceptions": [
            {"claim": "col = NULL работает", "truth": "нужно IS NULL"},
            {"claim": "порядок без ORDER BY", "truth": "не гарантирован"},
        ],
    }
    doc.update(over)
    return doc


def _write(tmp_path: Path, doc: dict, name: str | None = None) -> Path:
    d = tmp_path / "cards"
    d.mkdir(exist_ok=True)
    p = d / f"{name or doc['skill']}.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return d


def test_repo_cards_valid(taxonomy):
    cards = load_cards(CARDS_DIR, taxonomy)
    assert len(cards) >= 15
    assert {c.type for c in cards.values()} == set(SkillType)  # все шесть типов


def test_statement_numbering(tmp_path, taxonomy):
    cards = load_cards(_write(tmp_path, _card()), taxonomy)
    assert cards["sql"].statement(TestGrade.middle, 2) == "Читает план выполнения"


@pytest.mark.parametrize(
    ("over", "msg"),
    [
        ({"levels": {"junior": ["a1x", "a2x"], "middle": ["b1x", "b2x"]}}, "нет уровней"),
        (
            {"levels": {"junior": ["одно"], "middle": ["b1x", "b2x"], "senior": ["c1x", "c2x"]}},
            "от 2",
        ),
        (
            {
                "levels": {
                    "junior": ["то же", "a2x"],
                    "middle": ["То  же", "b2x"],
                    "senior": ["c1x", "c2x"],
                }
            },
            "повтор",
        ),
        ({"concepts": [{"term": "JOIN", "note": "abc"}]}, "concepts"),
        ({"misconceptions": []}, "misconceptions"),
        ({"type": "magic"}, "type"),
        ({"extra": 1}, "extra"),
    ],
)
def test_schema_rejects(tmp_path, taxonomy, over, msg):
    with pytest.raises(TaxonomyError, match=msg):
        load_cards(_write(tmp_path, _card(**over)), taxonomy)


def test_type_must_match_taxonomy(tmp_path, taxonomy):
    with pytest.raises(TaxonomyError, match="в справочнике hard"):
        load_cards(_write(tmp_path, _card(type="soft")), taxonomy)


def test_unknown_skill(tmp_path, taxonomy):
    with pytest.raises(TaxonomyError, match="нет в справочнике"):
        load_cards(_write(tmp_path, _card(skill="cobol_x")), taxonomy)


def test_filename_must_match_skill(tmp_path):
    d = _write(tmp_path, _card(), name="postgresql")
    with pytest.raises(TaxonomyError, match="именем файла"):
        parse_card(d / "postgresql.yaml")


def test_cli(capsys):
    assert main([]) == 0
    assert "карточек" in capsys.readouterr().out
    assert main(["--schema"]) == 0
    assert '"levels"' in capsys.readouterr().out


def test_schema_model_exported():
    assert SkillCard.model_json_schema()["title"] == "SkillCard"
