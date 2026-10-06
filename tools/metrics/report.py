"""Сборка отчёта `make metrics`: компоненты → строки светофора → JSON и markdown.

Чистые функции без ввода-вывода: детерминированы (никаких дат и времён прогона).
Цели — metrics.md §9.1/§9.3 в редакции ADR-030 (точность грейда мерим вне зоны безразличия).
Светофор: зелёный — цель выполнена; жёлтый — промах не больше `TOLERANCE` от цели;
красный — дальше; серый — не измерено (компонент недоступен или раннера нет).
Метрики с целью «отчёт» показываются без цвета.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TOLERANCE = 0.2  # доля цели, в пределах которой промах жёлтый
GREEN, YELLOW, RED, NONE, INFO = "green", "yellow", "red", "unmeasured", "info"
ICON = {GREEN: "🟢", YELLOW: "🟡", RED: "🔴", NONE: "⚪", INFO: "·"}
WORD = {GREEN: "зелёный", YELLOW: "жёлтый", RED: "красный", NONE: "не измерено", INFO: "отчёт"}


@dataclass(frozen=True)
class Spec:
    id: str
    area: str
    name: str
    op: str | None = None  # ">=" | "<=" | None (цель «отчёт»)
    target: float | None = None
    unit: str = ""  # "%" — значение хранится долей, показывается в процентах
    src: str = ""  # ключ компонента


def light(value: float | None, op: str | None, target: float | None) -> str:
    if value is None:
        return NONE
    if op is None or target is None:
        return INFO
    if op == ">=":
        if value >= target:
            return GREEN
        return YELLOW if value >= target * (1 - TOLERANCE) else RED
    if value <= target:
        return GREEN
    return YELLOW if value <= target * (1 + TOLERANCE) else RED


def fmt(value: float | None, unit: str = "") -> str:
    if value is None:
        return "—"
    if unit == "%":
        return f"{value * 100:.1f} %"
    if unit == "ms":
        return f"{value:.0f} мс"
    return f"{value:g}" if isinstance(value, int) else f"{value:.3f}".rstrip("0").rstrip(".")


def fmt_target(op: str | None, target: float | None, unit: str) -> str:
    if op is None or target is None:
        return "отчёт"
    return f"{op.replace('>=', '≥').replace('<=', '≤').replace('==', '=')} {fmt(target, unit)}"


# (id, область, название, op, цель, единица, ключ метрики в компоненте "assessment")
ASSESSMENT: list[tuple[str, str, str, str | None, float | None, str, str]] = [
    (
        "grade_acc_outside",
        "Тест",
        "Точность грейда вне зоны безразличия |θ − cut| ≥ δ",
        ">=",
        0.90,
        "%",
        "grade_accuracy_outside_indifference",
    ),
    ("kappa", "Тест", "Повторяемость κ (две попытки)", None, None, "", "kappa"),
    ("mean_items", "Тест", "Длина теста, заданий", "<=", 14, "", "mean_items"),
    ("max_share", "Тест", "Доля дошедших до максимума", "<=", 0.10, "%", "max_share"),
    (
        "theta_r",
        "Тест",
        "Восстановление θ: r(θ̂, θ) на полной длине",
        ">=",
        0.85,
        "",
        "theta_r_full",
    ),
    ("calib30", "Тест", "Калибровка RMSE после 30 ответов", "<=", 0.40, "", "calib_rmse_30"),
    ("calib100", "Тест", "Калибровка RMSE после 100 ответов", None, None, "", "calib_rmse_100"),
    ("rpb", "Тест", "Дискриминативность: медиана r_pb", ">=", 0.30, "", "median_rpb"),
    ("exposure", "Тест", "Максимальная экспозиция семейства", "<=", 0.30, "%", "max_exposure"),
    (
        "leak_quarantine",
        "Тест",
        "Ответов до карантина утёкшего семейства",
        "<=",
        100,
        "",
        "leak_answers_to_quarantine",
    ),
    (
        "leak_false_up",
        "Тест",
        "Утечка: ложные повышения у «знающих»",
        None,
        None,
        "%",
        "leak_false_upgrade",
    ),
    ("integrity_fpr", "Тест", "Детектор честности: FPR", "<=", 0.05, "%", "integrity_fpr"),
    ("integrity_tpr", "Тест", "Детектор честности: TPR", None, None, "%", "integrity_tpr"),
    (
        "grade_acc_all",
        "Тест",
        "Общая точность грейда (вся выборка)",
        None,
        None,
        "%",
        "grade_accuracy",
    ),
    ("grade_within1", "Тест", "Грейд ±1", None, None, "%", "grade_accuracy_within1"),
    (
        "ai_solvable",
        "Тест",
        "Решаемость ИИ: доля семейств (симулятор LLM)",
        None,
        None,
        "%",
        "ai_solvable_share",
    ),
]

# Метрики, для которых в проекте нет раннера или нужен стенд: всегда «не измерено» + причина
UNMEASURED: list[tuple[str, str, str, str, float | None, str, str]] = [
    (
        "bank_coverage",
        "Банк",
        "Покрытие: пустых ячеек «тип навыка × грейд × профессия»",
        "==",
        0,
        "",
        "нет раннера покрытия по профессиям",
    ),
    (
        "gen_unique",
        "Банк",
        "Уникальность вариантов на 1000 сидов",
        ">=",
        0.99,
        "%",
        "families-check не печатает долю, только pass/fail",
    ),
    (
        "mutation_mining",
        "Банк",
        "Майнинг мутаций: доля годных семейств",
        "",
        None,
        "",
        "нужен отчёт майнинга (SRC/DIR, песочница)",
    ),
    (
        "express",
        "Тест",
        "Экспресс-режим: длительность и точность",
        "",
        None,
        "",
        "нет раннера экспресс-режима в симуляторе",
    ),
    (
        "categorization",
        "Подбор",
        "Категоризация: точность профессия × грейд",
        ">=",
        0.90,
        "%",
        "`make eval` мерит только попадание роли, без грейда",
    ),
    (
        "fairness",
        "Подбор",
        "Справедливость: impact ratio «без ФСП / с ФСП»",
        "",
        None,
        "",
        "нет раннера fairness (evaluation.md §5)",
    ),
    (
        "unconfirmed_below",
        "Подбор",
        "Неподтверждённые ниже подтверждённых",
        "==",
        0,
        "",
        "нет раннера",
    ),
    (
        "fsp_effort",
        "Подбор",
        "ФСП по результативности (явки < призёрство)",
        "",
        None,
        "",
        "нет раннера",
    ),
    (
        "explainability",
        "Подбор",
        "Объяснимость: карточек с ≥ 3 факторами",
        "==",
        1.0,
        "%",
        "нужен core с БД (matching)",
    ),
    (
        "resume_f1",
        "Резюме",
        "F1 навыков на эталоне резюме",
        ">=",
        0.80,
        "",
        "нет раннера resume.py и эталонов; LLM нужен GPU",
    ),
    ("resume_contacts", "Резюме", "Точность контактов", ">=", 0.60, "", "нет раннера resume.py"),
    (
        "p95_assessment",
        "Скорость",
        "p95 `next`/`answer`",
        "<=",
        200,
        "ms",
        "нужен стенд (make up) и нагрузка на тест",
    ),
    ("ram_lite", "Ресурсы", "RAM профиля lite, ГБ", "<=", 1.5, "", "нужен стенд (docker stats)"),
    ("make_up_time", "Ресурсы", "Время `make up` с нуля, мин", "<=", 10, "", "нужен стенд"),
    (
        "code_coverage",
        "Качество кода",
        "Покрытие тестами core",
        ">=",
        0.70,
        "%",
        "не входит в офлайн-сборку (pytest-cov — отдельный прогон)",
    ),
    ("e2e", "Качество кода", "Сквозной путь (e2e)", "", None, "", "нужен стенд (make e2e)"),
]


def _row(
    spec_id: str,
    area: str,
    name: str,
    op: str | None,
    target: float | None,
    unit: str,
    source: str,
    value: float | None,
    note: str = "",
) -> dict[str, Any]:
    status = light(value, op, target)
    return {
        "id": spec_id,
        "area": area,
        "name": name,
        "value": value,
        "target": {"op": op, "value": target},
        "unit": unit,
        "status": status,
        "source": source,
        "note": note,
    }


def build_rows(comp: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """`comp[имя]` = {"ok": bool, "data": {...}, "reason": str}. Чужие поля не нужны."""
    rows: list[dict[str, Any]] = []

    def data(name: str) -> dict[str, Any] | None:
        c = comp.get(name)
        return c["data"] if c and c.get("ok") else None

    def why(name: str) -> str:
        c = comp.get(name) or {}
        return c.get("reason") or "компонент не запускался"

    a = data("assessment")
    for sid, area, name, op, tgt, unit, key in ASSESSMENT:
        v = a.get(key) if a else None
        rows.append(
            _row(
                sid,
                area,
                name,
                op,
                tgt,
                unit,
                "make eval-assessment",
                v,
                "" if v is not None else why("assessment"),
            )
        )

    m = data("matching")
    lift = (m or {}).get("lift", {})
    rows.append(
        _row(
            "ndcg_lift",
            "Подбор",
            "Релевантность: прирост nDCG@10 к BM25",
            ">=",
            0.20,
            "%",
            "make eval",
            (lift.get("ndcg10") or {}).get("vs_bm25") if m else None,
            "" if m else why("matching"),
        )
    )
    rows.append(
        _row(
            "p10_lift",
            "Подбор",
            "Релевантность: прирост precision@10 к BM25",
            None,
            None,
            "%",
            "make eval",
            (lift.get("p10") or {}).get("vs_bm25") if m else None,
            "" if m else why("matching"),
        )
    )
    rows.append(
        _row(
            "category_hit",
            "Подбор",
            "Категории потребности: роль среди предложенных",
            None,
            None,
            "%",
            "make eval",
            m.get("category_hit") if m else None,
            "" if m else why("matching"),
        )
    )

    f = data("families")
    rows.append(
        _row(
            "families_pass",
            "Банк",
            "Качество генераторов: доля семейств, прошедших families-check",
            ">=",
            1.0,
            "%",
            "make families-check",
            f.get("pass_rate") if f else None,
            "" if f else why("families"),
        )
    )

    ld = data("load")
    for key, label in (("search", "поиска"), ("matches", "подборки")):
        v = (ld or {}).get(key)
        rows.append(
            _row(
                f"p95_{key}",
                "Скорость",
                f"p95 {label} при 50 пользователях",
                "<=",
                1000,
                "ms",
                "make load",
                v,
                "" if v is not None else why("load"),
            )
        )

    for sid, area, name, op, tgt, unit, note in UNMEASURED:
        rows.append(_row(sid, area, name, op or None, tgt, unit, "—", None, note))
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {GREEN: 0, YELLOW: 0, RED: 0, NONE: 0, INFO: 0}
    for r in rows:
        out[r["status"]] += 1
    return out


def build_report(seed: int, comp: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = build_rows(comp)
    return {
        "seed": seed,
        "tolerance": TOLERANCE,
        "components": {
            k: {"ok": bool(v.get("ok")), "reason": v.get("reason", "")}
            for k, v in sorted(comp.items())
        },
        "summary": summarize(rows),
        "rows": rows,
    }


def render_md(rep: dict[str, Any]) -> str:
    s = rep["summary"]
    lines = [
        "# Офлайн-метрики (E31-3)",
        "",
        f"`make metrics` · seed {rep['seed']} · "
        f"{ICON[GREEN]} {s[GREEN]} · {ICON[YELLOW]} {s[YELLOW]} · {ICON[RED]} {s[RED]} · "
        f"{ICON[NONE]} не измерено {s[NONE]} · справочно {s[INFO]}",
        "",
        f"Светофор: зелёный — цель выполнена; жёлтый — промах до {int(rep['tolerance'] * 100)} % "
        "от цели; "
        "красный — больше; серый — не измерено (компонент недоступен без стенда или раннера нет). "
        "Цели — [metrics.md](../../docs/architecture/metrics.md) §9.1 в редакции ADR-030: "
        "точность грейда мерим вне зоны безразличия.",
        "",
    ]
    comps = rep["components"]
    lines += ["| Компонент | Статус |", "|---|---|"]
    for k, v in comps.items():
        lines.append(f"| {k} | {'выполнен' if v['ok'] else 'недоступен: ' + v['reason']} |")
    areas: dict[str, list[dict[str, Any]]] = {}
    for r in rep["rows"]:
        areas.setdefault(r["area"], []).append(r)
    for area, items in areas.items():
        lines += [
            "",
            f"## {area}",
            "",
            "| | Метрика | Значение | Цель | Примечание |",
            "|---|---|---|---|---|",
        ]
        for r in items:
            t = r["target"]
            name = r["name"].replace("|", "\\|")
            lines.append(
                f"| {ICON[r['status']]} | {name} | {fmt(r['value'], r['unit'])} | "
                f"{fmt_target(t['op'], t['value'], r['unit'])} | {r['note']} |"
            )
    lines.append("")
    return "\n".join(lines)
