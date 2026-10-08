"""E22-6: первые кодовые семейства и `families-check` (assessment.md §4)."""

from random import Random

import pytest
from app.assessment import families as registry
from app.assessment.families import check
from app.assessment.families.base import BaseFamily, Item, Kind
from app.assessment.world import World
from fsp_contracts.assessment import SkillType, TestGrade

FAMILIES = list(registry.REGISTRY.values())


def test_bank_passes_check():
    """То же, что `make families-check`, на меньшем числе сидов (без подпроцессов)."""
    assert check.run(FAMILIES, 200) == []


def test_every_skill_type_and_kind_covered():
    types = {SkillType(f.skill_type) for f in FAMILIES}
    assert types == set(SkillType)
    assert {f.kind for f in FAMILIES} == set(Kind) - {Kind.open}
    anchors = [f.slug for f in FAMILIES if getattr(f, "anchor", False)]
    assert 1 <= len(anchors) <= len(FAMILIES) // 4  # якоря — около 10 % банка


def test_digest_stable_across_hashseed():
    assert check.check_hashseed(20) == []


def test_root_cause_is_unique_failing_with_healthy_deps():
    fam = registry.get("service_graph_root_cause")
    for seed in check.seeds(100):
        item = check.build(fam, seed)
        assert 0 <= item.key < len(item.options)
        assert 2 <= item.meta["knobs"]["n_failing"] <= 5
        assert item.options[item.key] in item.stem.split("Алертят ошибками: ")[1]


def test_mutant_differs_and_key_points_to_mutated_line():
    fam = registry.get("py_find_bug")
    for seed in check.seeds(50):
        item = check.build(fam, seed)
        ok, bug = item.meta["exec_ok"].splitlines(), item.meta["exec_bug"].splitlines()
        assert [i + 1 for i, (a, b) in enumerate(zip(ok, bug, strict=True)) if a != b] == item.key
        assert check.run_python(item.meta["exec_ok"]) != check.run_python(item.meta["exec_bug"])


def test_sjt_key_orders_by_rating():
    fam = registry.get("sjt_code_review")
    item = check.build(fam, 7)
    ratings = item.meta["ratings"]
    assert [ratings[i] for i in item.key] == sorted(ratings, reverse=True)
    assert fam.score(item, item.key) == 1.0
    assert fam.score(item, list(reversed(item.key))) == 0.0


def test_unit_economics_numbers():
    """LTV = ARPU · маржа / отток; окупаемость = CAC / (ARPU · маржа) — целые числа."""
    fam = registry.get("unit_economics_calc")
    for seed in check.seeds(100):
        item = check.build(fam, seed)
        assert isinstance(item.key, int) and item.key > 0


def test_js_default_sort_is_lexicographic():
    fam = registry.get("js_trace")
    sorts = [it for it in (check.build(fam, s) for s in check.seeds(100)) if ".sort()" in it.stem]
    assert sorts
    for it in sorts:
        values = [int(v) for v in it.stem.split("[", 1)[1].split("]", 1)[0].split(", ")]
        assert it.key in values


def test_all_professions_open_core_has_full_bank():
    """E39-6: все профессии справочника открыты; у Backend, Frontend, AI Engineer пустых ячеек нет,
    у остальных тонкий банк — они «бета»."""
    from app.taxonomy.loader import load_taxonomy

    roles = load_taxonomy(check.TAXONOMY).roles
    profs = {r.slug: r.skills for r in roles if r.profession}
    assert all(r.active for r in roles if r.profession)
    assert set(profs) >= {"backend", "frontend", "ai_engineer", "ml", "mobile", "devops", "qa"}
    beta = check.thin_professions(FAMILIES, profs, level_window=1)
    assert not beta & {"backend", "frontend", "ai_engineer"}
    assert beta == {
        p
        for p in profs
        if any(f"{p} ×" in w for w in check.check_coverage(FAMILIES, check.TAXONOMY, 1))
    }


def test_coverage_gap_warns_not_fails():
    """Нет старших семейств бизнеса: ячейка «× senior × business» пуста — предупреждение."""
    rest = [f for f in FAMILIES if not (f.skill_type == SkillType.business and f.level >= 3)]
    warns = check.check_coverage(rest, check.TAXONOMY, level_window=1)
    assert "тонкий банк (бета): backend × senior × business — нет семейств" in warns
    assert "backend" in check.thin_professions(rest, {"backend": _backend()}, level_window=1)
    assert not [e for e in check.run(rest, 1) if "тонкий банк" in e or "покрытие" in e]


def _backend() -> dict[str, float]:
    from app.taxonomy.loader import load_taxonomy

    return next(r.skills for r in load_taxonomy(check.TAXONOMY).roles if r.slug == "backend")


def test_coverage_cells_respect_level_window():
    cells = check.coverage(FAMILIES, {"p": {"data_structures": 0.5}}, level_window=1)
    assert "lru_cache_trace" in cells[("p", TestGrade.senior, SkillType.fundamental)]
    assert "lru_cache_trace" not in cells[("p", TestGrade.junior, SkillType.fundamental)]
    assert cells[("p", TestGrade.junior, SkillType.hard)] == []  # нет навыков этого типа


def test_js_event_loop_sync_then_micro_then_timers():
    fam = registry.get("js_event_loop_order")
    for seed in check.seeds(100):
        it = check.build(fam, seed)
        order = [it.options[i] for i in it.key]
        lines = it.stem.split("\n\n", 1)[1].splitlines()
        sync = [ln.split('"')[1] for ln in lines if ln.startswith("console.log")]
        micro = [ln.split('"')[1] for ln in lines if ln.startswith("Promise")]
        assert order[: len(sync) + len(micro)] == sync + micro
        for a, b in zip(lines, lines[1:], strict=False):
            if a.startswith("  console.log") and b.startswith("  Promise"):
                x, y = a.split('"')[1], b.split('"')[1]
                assert order.index(y) == order.index(x) + 1  # микрозадача таймера — сразу за ним


def test_edge_case_input_key_is_the_only_failing_input():
    fam = registry.get("edge_case_input")
    for seed in check.seeds(50):
        it = check.build(fam, seed)
        assert check.run_python(it.meta["exec"]) == str(it.key)


class _Broken(BaseFamily):
    slug = "broken"
    kind = Kind.choice
    skill = "python"
    skill_type = SkillType.hard
    level = 2
    knob_bounds = {"n": (1, 2)}

    def generate(self, rng: Random, world: World) -> Item:
        return Item(
            kind=self.kind,
            stem="?",
            options=["a", "a"],
            key=5,
            meta={"exec": "print(2)", "knobs": {"n": 9}},
        )


def test_check_catches_broken_family():
    errs = check.check_family(_Broken(), [1])
    text = " ".join(errs)
    assert "повторы" in text and "вне вариантов" in text and "ручка n=9" in text
    assert "решатель" in text


def test_check_bank_flags_gaps_and_taxonomy_mismatch():
    class WrongType(_Broken):
        slug = "wrong_type"
        skill_type = SkillType.soft

    errs = check.check_bank([WrongType()], check.TAXONOMY)
    text = " ".join(errs)
    assert "тип навыка fundamental" in text
    assert "нет семейства kind=order" in text
    assert "нет якорных" in text
    assert "wrong_type: тип soft ≠ hard" in text


@pytest.mark.parametrize("fam", FAMILIES, ids=lambda f: f.slug)
def test_key_never_public(fam):
    item = check.build(fam, 3)
    public = item.public()
    assert "key" not in public and "meta" not in public


@pytest.mark.parametrize(
    ("kind", "key", "answer"),
    [
        (Kind.order, [0, 1, 2], [0, "1", 2]),  # смешанные типы: sorted() падал TypeError
        (Kind.sjt, [0, 1], [[0], [1]]),  # вложенные списки: unhashable в pos[v]
        (Kind.exact, 3, 10**400),  # огромное целое из JSON: float() падал OverflowError
        (Kind.estimate, 100.0, 10**400),
    ],
)
def test_malformed_answer_scores_zero_not_crash(kind, key, answer):
    """E37-1: кривой ответ клиента — балл 0, а не 500 на /answer."""
    fam = BaseFamily()
    assert fam.score(Item(kind=kind, stem="?", key=key), answer) == 0.0
