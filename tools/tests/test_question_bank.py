"""Банк вопросов data/questions: формат и совместимость с таксономией."""

from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
BANK = sorted((ROOT / "data/questions").glob("*.yaml"))
SKILLS = [
    "python",
    "javascript",
    "sql",
    "algorithms",
    "data_structures",
    "git",
    "docker",
    "linux",
    "networks",
    "react",
]


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_ten_skills_from_doc():
    assert [p.stem for p in BANK] == sorted(SKILLS)


def test_skills_are_testable_in_taxonomy():
    skills = yaml.safe_load((ROOT / "data/taxonomy/skills.yaml").read_text(encoding="utf-8"))
    skills = skills["skills"] if isinstance(skills, dict) else skills
    testable = {s["slug"] for s in skills if s.get("testable")}
    for p in BANK:
        assert _load(p)["skill"] in testable, p.stem


def test_format_and_coverage():
    ids: set[str] = set()
    for p in BANK:
        doc = _load(p)
        assert doc["skill"] == p.stem
        assert doc["status"] in {"draft", "approved"}
        qs = doc["questions"]
        assert 15 <= len(qs) <= 20, p.stem
        for q in qs:
            assert q["id"].startswith(doc["skill"] + "-") and q["id"] not in ids
            ids.add(q["id"])
            assert q["d"] in {1, 2, 3, 4, 5}
            assert q["text"].strip() and q["explanation"].strip()
            assert len(q["options"]) == 4 and len(set(map(str, q["options"]))) == 4
            assert q["correct"] in "ABCD"
        # все уровни сложности представлены: иначе адаптивный тест не сходится
        assert set(Counter(q["d"] for q in qs)) == {1, 2, 3, 4, 5}, p.stem


def test_correct_letter_not_biased():
    letters = Counter(q["correct"] for p in BANK for q in _load(p)["questions"])
    assert max(letters.values()) / sum(letters.values()) < 0.35
