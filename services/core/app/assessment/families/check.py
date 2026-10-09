"""`python -m app.assessment.families.check` (`make families-check`, CI): автопроверка семейств.

На N сидах (по умолчанию 1000) для каждого кодового семейства (assessment.md §4):
- генерация без ошибок, `kind` совпадает, публичная часть и ключ сериализуются в JSON;
- ключ, пришедший как ответ через JSON, даёт балл 1;
- ключ однозначен: варианты различны, неверные варианты ≠ ключу, порядок — перестановка;
- ответ решателя = исполнению (`meta["exec"]`);
- мутант отличается от оригинала на примере (`meta["exec_ok"]` / `meta["exec_bug"]`);
- ручки в границах уровня (`knob_bounds` ↔ `meta["knobs"]`);
- детерминизм: повторная генерация и два прогона в подпроцессах с разным `PYTHONHASHSEED`.

Банки задач ФСП (`data/questions/fsp`, E32-6) — лицензия, ключ, автопроверка (`fsp_bank`).

По банку: каждый тип навыка покрыт ≥ 2 семействами, каждый `kind` (кроме `open`) — хотя бы одним,
навык семейства есть в `data/taxonomy` и его тип совпадает, есть якорные семейства.

Покрытие (E36-2, E39-6): у каждой активной профессии справочника для каждого грейда и типа навыка
ищется семейство — навык из весов профессии, уровень в окне грейда (`selection.level_ok`). Пустая
ячейка «профессия × грейд × тип навыка» — предупреждение «тонкий банк»: профессия остаётся открытой,
в опросе помечена «бета» (`thin_professions`). Провал — только если активных профессий нет.

Исполняется только код, который сгенерировали сами семейства. Код кандидатов не исполняется.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from random import Random

from fsp_contracts.assessment import SkillType, TestGrade

from app.assessment.config import load_config
from app.assessment.families import REGISTRY
from app.assessment.families.base import SCORERS, Family, Item, Kind, score_exact
from app.assessment.selection import GRADE_LEVEL
from app.assessment.world import World

ROOT = Path(__file__).resolve().parents[5]
TAXONOMY = ROOT / "data" / "taxonomy"
MIN_PER_TYPE = 2
MAX_ERRORS_PER_FAMILY = 3


def seeds(n: int) -> list[int]:
    """Сиды, похожие на боевые (63 бита), детерминированно."""
    return [(i * 2_654_435_761 + 97) % 2**63 for i in range(n)]


def build(fam: Family, seed: int) -> Item:
    """Как `attempts.build_item` при случайном домене: тот же сид → тот же вариант."""
    return fam.generate(Random(seed), World.from_seed(seed))


def run_python(code: str) -> str:
    """Исполняет фрагмент, сгенерированный семейством, и возвращает stdout."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(code, "<family>", "exec"), {"__name__": "__family__"})  # noqa: S102
    return buf.getvalue().strip()


class _Step:
    """Шаг цепочки как семейство для `check_item`: оценка по `kind` шага, без ручек."""

    def __init__(self, kind: Kind) -> None:
        self.kind = kind

    def score(self, item: Item, answer: object) -> float:
        return SCORERS[item.kind](item.key, answer)


def check_chain(fam: Family, item: Item) -> list[str]:
    """`chain` (E26-3): ≥ 2 шагов обычных типов, каждый проходит те же проверки, ключ — их ключи."""
    errs: list[str] = []
    if len(item.steps) < 2:
        return ["в цепочке меньше двух шагов"]
    for i, st in enumerate(item.steps, start=1):
        if st.kind in (Kind.chain, Kind.open):
            errs.append(f"шаг {i}: kind {st.kind.value} недопустим в цепочке")
            continue
        errs += [f"шаг {i}: {e}" for e in check_item(_Step(st.kind), st)]  # type: ignore[arg-type]
    if item.key != [st.key for st in item.steps]:
        errs.append("ключ цепочки ≠ ключам шагов")
    wrong = [None, *json.loads(json.dumps(item.key))[1:]]
    if not 0.0 < fam.score(item, wrong) < 1.0:
        errs.append("ошибка в одном шаге не даёт частичный балл")
    return errs


def check_item(fam: Family, item: Item) -> list[str]:
    errs: list[str] = []
    if item.kind == Kind.chain:
        errs += check_chain(fam, item)
    elif item.steps:
        errs.append("шаги есть только у chain")
    if item.kind != fam.kind:
        errs.append(f"kind {item.kind} ≠ {fam.kind}")
    if item.kind == Kind.open:
        errs.append("open не идёт в θ: кодовым семействам недоступен")
    if not item.stem.strip() or item.time_limit_s <= 0:
        errs.append("пустое условие или лимит времени")
    try:
        json.dumps(item.public(), ensure_ascii=False)
        key = json.loads(json.dumps(item.key))
    except (TypeError, ValueError) as e:
        return [*errs, f"не сериализуется в JSON: {e}"]
    if fam.score(item, key) != 1.0:
        errs.append(f"ключ как ответ не даёт 1: {item.key!r}")

    opts = item.options or []
    if item.kind in (Kind.choice, Kind.order, Kind.sjt):
        if len(opts) < 2 or len(set(opts)) != len(opts):
            errs.append("вариантов меньше двух или есть повторы")
    if item.kind == Kind.choice:
        if not isinstance(item.key, int) or not 0 <= item.key < len(opts):
            errs.append(f"ключ вне вариантов: {item.key!r}")
        elif any(fam.score(item, i) != 0.0 for i in range(len(opts)) if i != item.key):
            errs.append("неверный вариант даёт балл")
    elif item.kind in (Kind.order, Kind.sjt):
        if sorted(item.key) != list(range(len(opts))):
            errs.append(f"ключ не перестановка вариантов: {item.key!r}")
        elif fam.score(item, list(reversed(item.key))) >= 1.0:
            errs.append("обратный порядок даёт 1")
        ratings = item.meta.get("ratings")
        if ratings is not None and len(set(ratings)) != len(ratings):
            errs.append("одинаковые оценки эффективности: ключ неоднозначен")
    elif item.kind == Kind.find_bug:
        if not item.key or not all(isinstance(x, int) and x > 0 for x in item.key):
            errs.append(f"плохие строки дефекта: {item.key!r}")
    elif item.kind == Kind.estimate:
        if not isinstance(item.key, int | float) or not math.isfinite(item.key) or item.key <= 0:
            errs.append(f"оценка должна быть > 0: {item.key!r}")
        elif fam.score(item, item.key * 10) != 0.0:
            errs.append("ответ в 10 раз больше получает балл")

    if "exec" in item.meta:
        out = run_python(item.meta["exec"])
        if score_exact(item.key, out) != 1.0:
            errs.append(f"решатель {item.key!r} ≠ исполнение {out!r}")
    if "exec_ok" in item.meta and run_python(item.meta["exec_ok"]) == run_python(
        item.meta["exec_bug"]
    ):
        errs.append("мутант не отличается от оригинала на примере")

    knobs = item.meta.get("knobs", {})
    for name, (lo, hi) in getattr(fam, "knob_bounds", {}).items():
        v = knobs.get(name)
        if v is None or not lo <= v <= hi:
            errs.append(f"ручка {name}={v!r} вне [{lo}, {hi}]")
    return errs


def check_family(fam: Family, seed_list: Iterable[int]) -> list[str]:
    errs: list[str] = []
    for seed in seed_list:
        try:
            item = build(fam, seed)
            problems = check_item(fam, item)
            if build(fam, seed) != item:
                problems.append("повторная генерация с тем же сидом даёт другой вариант")
        except Exception as e:  # noqa: BLE001 — любая ошибка генерации — провал проверки
            problems = [f"исключение {type(e).__name__}: {e}"]
        errs += [f"{fam.slug} seed={seed}: {p}" for p in problems]
        if len(errs) >= MAX_ERRORS_PER_FAMILY:
            break
    return errs


def check_bank(families: Sequence[Family], taxonomy_dir: Path | None) -> list[str]:
    errs: list[str] = []
    per_type = Counter(SkillType(f.skill_type) for f in families)
    for t in SkillType:
        if per_type[t] < MIN_PER_TYPE:
            errs.append(f"тип навыка {t.value}: семейств {per_type[t]} < {MIN_PER_TYPE}")
    kinds = {f.kind for f in families}
    for k in Kind:
        if k != Kind.open and k not in kinds:
            errs.append(f"нет семейства kind={k.value}")
    if not any(getattr(f, "anchor", False) for f in families):
        errs.append("нет якорных семейств (anchor)")
    if taxonomy_dir is not None:
        from app.taxonomy.loader import load_taxonomy

        types = load_taxonomy(taxonomy_dir).skill_types
        for f in families:
            if f.skill not in types:
                errs.append(f"{f.slug}: навыка {f.skill} нет в справочнике")
            elif types[f.skill] != SkillType(f.skill_type):
                errs.append(f"{f.slug}: тип {f.skill_type} ≠ {types[f.skill].value} в справочнике")
    return errs


def coverage(
    families: Sequence[Family], professions: dict[str, dict[str, float]], level_window: int
) -> dict[tuple[str, TestGrade, SkillType], list[str]]:
    """Ячейка «профессия × грейд × тип навыка» → слаги семейств, которые в неё попадают."""
    out: dict[tuple[str, TestGrade, SkillType], list[str]] = {}
    for prof, weights in professions.items():
        for g in TestGrade:
            for t in SkillType:
                out[(prof, g, t)] = [
                    f.slug
                    for f in families
                    if SkillType(f.skill_type) == t
                    and weights.get(f.skill, 0) > 0
                    and abs(f.level - GRADE_LEVEL[g]) <= level_window
                ]
    return out


def thin_professions(
    families: Sequence[Family],
    professions: dict[str, dict[str, float]],
    level_window: int | None = None,
) -> set[str]:
    """Профессии с тонким банком — есть пустая ячейка «грейд × тип навыка» (E39-6, «бета»)."""
    if level_window is None:
        level_window = load_config().level_window
    return {
        p for (p, _, _), slugs in coverage(families, professions, level_window).items() if not slugs
    }


def _active_professions(taxonomy_dir: Path) -> dict[str, dict[str, float]]:
    from app.taxonomy.loader import load_taxonomy

    return {
        r.slug: r.skills for r in load_taxonomy(taxonomy_dir).roles if r.profession and r.active
    }


def check_coverage(
    families: Sequence[Family], taxonomy_dir: Path, level_window: int | None = None
) -> list[str]:
    """Пустые ячейки покрытия у активных профессий справочника — предупреждения (E39-6)."""
    if level_window is None:
        level_window = load_config().level_window
    professions = _active_professions(taxonomy_dir)
    return [
        f"тонкий банк (бета): {p} × {g.value} × {t.value} — нет семейств"
        for (p, g, t), slugs in coverage(families, professions, level_window).items()
        if not slugs
    ]


def digest(families: Sequence[Family], seed_list: Sequence[int]) -> str:
    h = hashlib.sha256()
    for fam in sorted(families, key=lambda f: f.slug):
        for seed in seed_list:
            it = build(fam, seed)
            h.update(repr((fam.slug, seed, it.kind.value, it.stem, it.options, it.key)).encode())
    return h.hexdigest()


def check_hashseed(n: int) -> list[str]:
    """Два прогона в подпроцессах с разным PYTHONHASHSEED дают те же варианты."""
    out = []
    for hs in ("0", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": hs}
        cmd = [sys.executable, "-m", "app.assessment.families.check", "--digest", "--seeds", str(n)]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            return [f"прогон с PYTHONHASHSEED={hs} упал: {res.stderr.strip()[-500:]}"]
        out.append(res.stdout.strip())
    return [] if out[0] == out[1] else ["варианты зависят от PYTHONHASHSEED"]


def run(families: Sequence[Family], n: int, taxonomy_dir: Path | None = TAXONOMY) -> list[str]:
    seed_list = seeds(n)
    errs = check_bank(families, taxonomy_dir)
    if taxonomy_dir is not None and not _active_professions(taxonomy_dir):
        errs.append("нет активных профессий в справочнике")
    for fam in families:
        errs += check_family(fam, seed_list)
    return errs


def check_fsp_banks() -> list[str]:
    """Банки задач ФСП `data/questions/fsp/*.yaml` (E32-6): лицензия, ключ, автопроверка."""
    from app.assessment import fsp_bank

    return fsp_bank.check_files(fsp_bank.bank_files())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seeds", type=int, default=1000)
    p.add_argument("--taxonomy", type=Path, default=TAXONOMY)
    p.add_argument("--digest", action="store_true", help="только отпечаток вариантов")
    args = p.parse_args(argv)
    families = list(REGISTRY.values())
    if args.digest:
        print(digest(families, seeds(args.seeds)))
        return 0

    errs = run(families, args.seeds, args.taxonomy) + check_hashseed(args.seeds)
    errs += check_fsp_banks()
    for f in sorted(families, key=lambda f: (SkillType(f.skill_type).value, f.slug)):
        anchor = " anchor" if getattr(f, "anchor", False) else ""
        print(f"  {f.skill_type:<11} {f.kind.value:<9} L{f.level} {f.slug} ({f.skill}){anchor}")
    for w in check_coverage(families, args.taxonomy):
        print(f"WARN {w}", file=sys.stderr)
    for e in errs:
        print(f"FAIL {e}", file=sys.stderr)
    beta = sorted(thin_professions(families, _active_professions(args.taxonomy)))
    if beta:
        print(f"families-check: тонкий банк, помечены «бета» — {', '.join(beta)}")
    state = "OK" if not errs else f"ошибок: {len(errs)}"
    print(f"families-check: семейств {len(families)}, сидов {args.seeds} — {state}")
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
