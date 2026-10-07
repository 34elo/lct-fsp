"""E36-2 (ADR-027 п. 1): покрытие банка «профессия × грейд × тип навыка» и семейства `depth`."""

from app.assessment.config import load_config
from app.assessment.families import REGISTRY, check, coverage
from app.assessment.families.depth import FAMILIES, _event_loop, _lru


def test_depth_families_pass_autocheck():
    seeds = check.seeds(200)
    assert [e for f in FAMILIES for e in check.check_family(f, seeds)] == []


def test_visible_professions_have_no_empty_cells():
    profs = coverage.professions()
    assert [p.slug for p in profs if p.active] == ["backend", "frontend", "ai_engineer"]
    rep = coverage.compute(profs, REGISTRY.values(), load_config())
    assert rep["empty"] == []
    assert coverage.errors() == []
    row = next(p for p in rep["professions"] if p["slug"] == "frontend")
    assert set(row["cells"]) == {"junior", "middle", "senior"}
    assert all(row["cells"][g][t] for g in row["cells"] for t in row["cells"][g])


def test_empty_cell_of_visible_profession_is_error_hidden_is_not():
    cfg = load_config()
    vis = coverage.Profession("backend", "B", True, frozenset({"python"}))
    hid = coverage.Profession("ml", "M", False, frozenset())
    rep = coverage.compute([vis, hid], REGISTRY.values(), cfg)
    assert "backend/junior/hard" not in rep["empty"]  # py_loop_sum, py_find_bug
    assert "backend/senior/soft" in rep["empty"]
    assert not any(c.startswith("ml/") for c in rep["empty"])
    md = coverage.to_markdown(rep)
    assert "| ml (скрыта) | senior |" in md and "Пустых обязательных ячеек" in md


def test_report_files(tmp_path):
    assert coverage.main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / "coverage.json").exists() and (tmp_path / "coverage.md").exists()


def test_event_loop_order():
    stmts = [
        ("sync", ["A"]),
        ("chain", ["B", "C"]),
        ("timeout", ["D", "E"]),
        ("micro", ["F"]),
        ("timeout", ["G"]),
        ("sync", ["H"]),
    ]
    # синхронное → микрозадачи (следующий .then — в конец очереди) → таймер и его микрозадача
    assert _event_loop(stmts) == ["A", "H", "B", "F", "C", "D", "E", "G"]


def test_lru_differs_from_fifo():
    ops = [1, 2, 1, 3, 1]
    assert _lru(ops, 2) == (3, [3, 1])
    assert _lru(ops, 2, lru=False) == (4, [3, 1])
