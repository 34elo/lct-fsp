"""Разбор резюме без LLM: опыт, образование, даты, город; навыки F1 ≥ 0.6."""

from pathlib import Path

import pytest
from fsp_ml import resume_ner, resume_parser, resume_structure
from tests.test_resume_parser import INDEX, TEXT, TODAY

DATA = (Path(__file__).parent / "fixtures" / "resume_data.txt").read_text()


def _parse(text):
    out = resume_parser.extract_rules(text, INDEX)
    return resume_parser.assemble(
        text, out, INDEX, version=resume_parser.RULES_VERSION, today=TODAY
    )


def test_backend_resume_experience_education_dates():
    p = _parse(TEXT)
    assert p.person.full_name == "Пётр Вымыслов" and p.person.city == "Казань"
    a, b = p.experience
    assert (a.company, a.title) == ("ООО «Вымышленная логистика»", "Backend-разработчик")
    assert (a.start, a.end) == ("2021-03", None)
    assert (b.title, b.start, b.end) == ("Стажёр-разработчик", "2020-06", "2021-02")
    assert {"python", "fastapi", "redis"} <= set(a.skills) and "pytest" in b.skills
    e = p.education[0]
    assert (e.degree, e.year_end, e.field) == ("бакалавр", 2021, "Прикладная математика")
    assert p.total_experience_months > 60


def test_other_layout():
    p = _parse(DATA)
    assert p.person.full_name == "Иванова Мария Сергеевна"
    assert p.person.city == "Санкт-Петербург"
    assert p.summary and p.summary.startswith("Строю модели")
    a, b = p.experience
    assert (a.company, a.title, a.start, a.end) == (
        "Вымышленный Банк",
        "ML-инженер",
        "2022-09",
        None,
    )
    assert (b.company, b.title, b.start, b.end) == (
        "АО «Придуманные данные»",
        "Аналитик данных",
        "2019-01",
        "2022-12",
    )
    assert p.education[0].degree == "магистр" and p.education[0].year_end == 2019


@pytest.mark.parametrize(
    ("line", "want"),
    [
        ("03.2020 — 05.2023", ("03.2020", "05.2023")),
        ("июн 2020 – фев 2021", ("июн 2020", "фев 2021")),
        ("2019–2022", ("2019", "2022")),
        ("Март 2018 - сейчас", ("Март 2018", "сейчас")),
        ("2022-03 по н.в.", ("2022-03", "н.в.")),
    ],
)
def test_find_period(line, want):
    got = resume_structure.find_period(line)
    assert got and got[:2] == want


def test_no_period_in_plain_text():
    assert resume_structure.find_period("Postgres 15, версия 2020") is None


def test_unrecognized_stays_empty():
    p = _parse("Просто текст без структуры, Python и Redis.")
    assert not p.experience and not p.education and p.person.city is None
    assert {s.slug for s in p.skills} == {"python", "redis"}


def test_skills_f1_without_llm():
    expected = {
        TEXT: {"python", "fastapi", "postgresql", "redis", "rabbitmq", "docker", "git",
               "pytest", "javascript"},
        DATA: {"python", "pytorch", "airflow", "clickhouse", "sql", "pandas", "grafana"},
    }  # fmt: skip
    tp = fp = fn = 0
    for text, want in expected.items():
        got = {s.slug for s in _parse(text).skills}
        tp += len(got & want)
        fp += len(got - want)
        fn += len(want - got)
    prec, rec = tp / (tp + fp), tp / (tp + fn)
    assert 2 * prec * rec / (prec + rec) >= 0.6


def test_natasha_optional(monkeypatch):
    monkeypatch.setattr(resume_ner, "_tools", lambda: None)
    assert resume_ner.entities("Пётр Вымыслов") == []
    p = _parse(TEXT)  # правила работают и без Natasha
    assert p.experience and p.person.full_name == "Пётр Вымыслов"


def test_natasha_finds_person():
    if not resume_ner.available():
        pytest.skip("natasha не установлена")
    assert any(k == "PER" for k, _ in resume_ner.entities("Иванов Пётр Сергеевич, 29 лет"))
