"""Разбор резюме в раскладке hh.ru (E39-19): набор data/eval/resumes/hh/ и точечные случаи."""

import importlib.util
import sys
from pathlib import Path

from fsp_ml import resume_structure
from fsp_ml.resume_text import clean

ROOT = Path(__file__).resolve().parents[3]


def _runner():
    sys.path.insert(0, str(ROOT / "tools" / "eval"))
    spec = importlib.util.spec_from_file_location(
        "hh_resumes_runner", ROOT / "tools" / "eval" / "runners" / "resumes.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_hh_set_completeness_meets_target():
    r = _runner().run_resumes()
    assert r["n_resumes"] == 10
    assert r["completeness"] >= 0.8, r["files"]
    assert all(v >= 0.8 for v in r["by_section"].values() if v is not None)


def test_hh_experience_pdf_layout():
    lines = [
        "Август 2021 — настоящее время  ООО «Вымышленная логистика»",
        "5 лет 2 месяца                    Москва, vlogistics.example.test",
        "                                  Backend-разработчик",
        "Обязанности: Делал сервисы на Python.",
        "Июнь 2018 — Июль 2021       АО «Придуманные системы»",
        "3 года 2 месяца                  Москва",
        "Верстальщик",
        "Обязанности: Верстал сайты.",
    ]
    a, b = resume_structure.parse_experience(lines, set())
    assert (a["company"], a["title"], a["start"], a["end"]) == (
        "ООО «Вымышленная логистика»",
        "Backend-разработчик",
        "Август 2021",
        "настоящее время",
    )
    assert a["description"] == "Делал сервисы на Python."
    assert (b["company"], b["title"], b["end"]) == (
        "АО «Придуманные системы»",
        "Верстальщик",
        "Июль 2021",
    )


def test_old_layout_not_taken_for_hh():
    lines = ["Сентябрь 2022 — по настоящее время  Вымышленный Банк, ML-инженер", "Обучала модели."]
    assert not resume_structure.is_hh_experience(lines)


def test_hh_education_levels_and_years():
    lines = [
        "Магистр",
        "2023",
        "Томский вымышленный университет, Томск",
        "Институт кибернетики",
        "Искусственный интеллект",
        "Бакалавр",
        "2021",
        "Томский вымышленный университет, Томск",
        "Прикладная информатика",
    ]
    a, b = resume_structure.parse_education(lines)
    assert (a["degree"], a["year_end"], a["field"]) == ("магистр", 2023, "Искусственный интеллект")
    assert (b["degree"], b["institution"], b["field"]) == (
        "бакалавр",
        "Томский вымышленный университет",
        "Прикладная информатика",
    )


def test_headers_with_duration_and_city_label():
    sec = resume_structure.sections(
        "Имя\nПроживает: Казань, м. Центр\nОпыт работы — 3 года 2 месяца\nX"
    )
    assert sec["experience"] == ["X"]
    assert resume_structure.parse_city(sec["head"]) == "Казань"


def test_pdf_ligatures_are_normalized():
    assert clean("Airﬂow и ﬁltering") == "Airflow и filtering"
