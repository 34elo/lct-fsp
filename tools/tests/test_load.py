import ast
import importlib.util
from pathlib import Path

LOAD = Path(__file__).resolve().parents[1] / "load"


def _report():
    spec = importlib.util.spec_from_file_location("load_report", LOAD / "report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _row(name, reqs, fails, p95):
    return {
        "Name": name,
        "Request Count": str(reqs),
        "Failure Count": str(fails),
        "Median Response Time": "50",
        "95%": str(p95),
        "Requests/s": "1.0",
    }


def test_locustfile_parses_and_has_named_tasks():
    src = ast.unparse(ast.parse((LOAD / "locustfile.py").read_text(encoding="utf-8")))
    assert "name='search'" in src and "name='matches'" in src


def test_thresholds_ok():
    rows = [
        _row("search", 100, 0, 800),
        _row("matches", 100, 0, 999),
        _row("Aggregated", 200, 1, 9),
    ]
    assert _report().check(rows)[1] == []


def test_p95_breach_and_missing():
    _, v = _report().check([_row("search", 100, 0, 1200)])
    assert any("search" in x and "p95" in x for x in v)
    assert any("matches" in x for x in v)


def test_error_rate_breach():
    rows = [_row("search", 10, 0, 1), _row("matches", 10, 0, 1), _row("Aggregated", 100, 5, 1)]
    assert any("ошибки" in x for x in _report().check(rows)[1])
