"""Демо-очередь допуска заданий: по одному заданию на каждую ячейку «профессия × грейд».

7 профессий × 3 грейда = 21 семейство-спецификация (`source = spec`, статус по таблице ниже) со
статистикой пилота, заданной снаружи (`lifecycle.refresh_stats` не затирает её, пока нет ответов).
Часть заданий не проходит пороги: админу есть что показать — «Допустить» закрыто с причиной.
Идемпотентно по `slug`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.assessment.families.spec import FamilySpec
from app.assessment.models import FamilyRow
from app.taxonomy import service as taxonomy
from fsp_platform.db import session_scope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_NS = uuid.UUID("8c1f0a52-3b7d-4e19-a2c6-5d9e7f3b1a40")
GRADES = ("junior", "middle", "senior")
LEVEL = {"junior": 2, "middle": 3, "senior": 4}
B = {"junior": -1.0, "middle": 0.1, "senior": 1.1}

# профессия → (что считаем, навыки для junior / middle / senior); вес навыка в профессии ≥ 0.5
PROFESSIONS: dict[str, tuple[str, list[str]]] = {
    "backend": ("запросов к API", ["rest", "sql", "system_design"]),
    "frontend": ("загрузок страницы", ["html", "javascript", "typescript"]),
    "mobile": ("запусков приложения", ["oop", "android", "mobile"]),
    "ml": ("предсказаний модели", ["pandas", "statistics", "deep_learning"]),
    "devops": ("выкладок на сервер", ["linux", "docker", "kubernetes"]),
    "qa": ("прогонов автотестов", ["api_testing", "test_automation", "edge_case_thinking"]),
    "ai_engineer": ("вызовов языковой модели", ["prompt_engineering", "rag", "llm_evaluation"]),
}

# Статистика пилота: good — все пороги выполнены; few — мало ответов; weak — слабая дискриминация
STATS: dict[str, dict[str, Any]] = {
    "good": {"n": 52, "p": 0.64, "r_pb": 0.38, "seed_spread": 0.07, "dif": 0.03},
    "few": {"n": 17, "p": 0.58, "r_pb": 0.31, "seed_spread": 0.1, "dif": 0.04},
    "weak": {"n": 44, "p": 0.51, "r_pb": 0.09, "seed_spread": 0.12, "dif": 0.05},
    "none": {},
}
DEFAULT = {"junior": ("pilot", "good"), "middle": ("pilot", "good"), "senior": ("draft", "none")}
OVERRIDE: dict[tuple[str, str], tuple[str, str]] = {
    ("frontend", "middle"): ("pilot", "few"),
    ("mobile", "junior"): ("pilot", "weak"),
    ("mobile", "middle"): ("pilot", "few"),
    ("ml", "senior"): ("pilot", "good"),
    ("devops", "senior"): ("quarantine", "weak"),
    ("devops", "middle"): ("pilot", "weak"),
    ("backend", "senior"): ("pilot", "good"),
    ("qa", "senior"): ("pilot", "few"),
    ("ai_engineer", "senior"): ("pilot", "good"),
}


def _form(grade: str, what: str, skill: str) -> dict[str, Any]:
    if grade == "junior":
        raw: dict[str, Any] = {
            "kind": "exact",
            "stem": (
                "В сервисе «{{service}}» компании {{company}} приходит {{n}} " + what + " в час, "
                "из них {{pct}}% заканчиваются ошибкой. Сколько ошибок за час?"
            ),
            "params": {
                "n": {"min": 200, "max": 2000, "step": 100},
                "pct": {"min": 2, "max": 9, "step": 1},
            },
            "answer": "n * pct / 100",
            "precision": 0,
        }
    elif grade == "middle":
        raw = {
            "kind": "choice",
            "stem": (
                "Метрика «{{metric}}» в «{{service}}» выросла с {{a}} до {{b}} за неделю ("
                + what
                + "). Что разумно сделать первым?"
            ),
            "params": {
                "a": {"min": 10, "max": 40, "step": 5},
                "b": {"min": 55, "max": 95, "step": 5},
            },
            "options": [
                "Проверить, не изменился ли способ измерения",
                "Сразу откатить последний релиз",
                "Считать это шумом и ничего не делать",
                "Удвоить ресурсы сервиса",
            ],
            "correct": 0,
        }
    else:
        raw = {
            "kind": "estimate",
            "stem": (
                "Оцените средний поток " + what + " на один экземпляр сервиса «{{service}}»: "
                "{{total}} в сутки, экземпляров — {{inst}}. Ответ — штук в секунду."
            ),
            "params": {
                "total": {"values": [864000, 1728000, 2592000, 4320000]},
                "inst": {"min": 2, "max": 10, "step": 1},
            },
            "answer": "total / 86400 / inst",
        }
    return FamilySpec.model_validate(
        {
            "title": f"{what.capitalize()}: {skill}, {grade}",
            "skill": skill,
            "level": LEVEL[grade],
            **raw,
        }
    ).model_dump(mode="json")


def plan() -> list[dict[str, Any]]:
    """Детерминированный список заданий (без БД)."""
    out = []
    for prof, (what, skills) in PROFESSIONS.items():
        for grade, skill in zip(GRADES, skills, strict=True):
            status, profile = OVERRIDE.get((prof, grade), DEFAULT[grade])
            out.append(
                {
                    "slug": f"demo-{prof.replace('_', '-')}-{grade}",
                    "profession": prof,
                    "grade": grade,
                    "skill": skill,
                    "status": status,
                    "stats": dict(STATS[profile]),
                    "form": _form(grade, what, skill),
                }
            )
    return out


def _row(item: dict[str, Any], now: datetime, idx: int) -> FamilyRow:
    stats = dict(item["stats"])
    at = (now - timedelta(days=2 + idx % 5)).isoformat()
    log: list[dict[str, Any]] = []
    if item["status"] in ("pilot", "quarantine"):
        log.append({"from": "draft", "to": "pilot", "reason": "autocheck", "at": at})
    if item["status"] == "quarantine":
        log.append({"from": "pilot", "to": "quarantine", "reason": "alarm:low_r_pb", "at": at})
    form = item["form"]
    return FamilyRow(
        id=uuid.uuid5(_NS, item["slug"]),
        slug=item["slug"],
        kind=form["kind"],
        source="spec",
        skill_id=taxonomy.skill_id(item["skill"]),
        skill_type="hard",
        level=LEVEL[item["grade"]],
        b=B[item["grade"]],
        n=int(stats.get("n", 0)),
        status=item["status"],
        key_status="approved",
        ai_solvable=0.3,
        spec={"form": form, "author": form, "key_draft": None, "autocheck": {"ok": True}},
        stats={**stats, "log": log, "updated_at": at} if stats or log else {},
    )


async def seed_families(
    factory: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    items = plan()
    async with session_scope(factory) as s:
        have = set(
            await s.scalars(
                select(FamilyRow.slug).where(FamilyRow.slug.in_([i["slug"] for i in items]))
            )
        )
        new = [i for i in items if i["slug"] not in have]
        for idx, item in enumerate(new):
            s.add(_row(item, now, idx))
    return {"families": len(new)}


__all__ = ["plan", "seed_families"]
