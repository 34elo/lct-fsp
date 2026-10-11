"""«Почему вы» для кандидата и надёжность компании.

Только данные самого кандидата и агрегат по компании: чужих кандидатов нет ни в факторах,
ни в рейтинге. Веса и пороги — константы ниже (нормализованы в 0..1), формулы без LLM.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fsp_contracts.enums import Grade
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.candidates.models import Candidate
from app.graph import service as graph
from app.offers.models import Offer
from app.taxonomy import service as taxonomy
from app.vacancies import service as vacancies

TOP_FACTORS = 3
SKILL_CONFIRMED = 0.5  # доверие по навыку, с которого он считается подтверждённым
MIN_SAMPLE = 3  # меньше ответов в выборке — доли и срока нет (не штрафуем за «мало данных»)
WINDOW_DAYS = 90
GRADE_RU = {"junior": "Junior", "middle": "Middle", "senior": "Senior"}
_ORDER = [g.value for g in Grade]


class WhyFactor(BaseModel):
    code: str  # grade | skills | salary | format
    text: str
    weight: float  # вклад ∈ [0, 1]


class WhyYou(BaseModel):
    factors: list[WhyFactor] = []  # топ-3 причины совпадения
    unconfirmed: list[str] = []  # чего не хватает: неподтверждённые навыки, расхождения


class CompanyReliability(BaseModel):
    responsibility_score: float | None = None
    response_rate: float | None = None  # доля ответов компании на отклики и открытые интересы
    avg_response_hours: float | None = None  # средний срок первого ответа
    sample: int = 0  # размер выборки; < MIN_SAMPLE — доли и срока нет


def _plus(code: str, weight: float, text: str) -> WhyFactor:
    return WhyFactor(code=code, weight=weight, text=text)


def _rank(g: str) -> int:
    return _ORDER.index(g) if g in _ORDER else -1


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


async def why_you(session: AsyncSession, offer: Offer, cand: Candidate) -> WhyYou:
    v = await vacancies.get(session, offer.vacancy_id) if offer.vacancy_id else None
    plus: list[WhyFactor] = []
    minus: list[str] = []

    # грейд из теста: профессия вакансии, иначе основная роль, иначе лучший
    grades = await assessment.get_grades(session, cand.user_id)
    g = None
    if grades:
        want = v.role if v else cand.primary_role
        g = next((x for x in grades if x.profession == want), None) or max(
            grades, key=lambda x: x.theta
        )
    if g is not None:
        name = GRADE_RU.get(g.grade.value, g.grade.value)
        if v is None:
            plus.append(_plus("grade", 0.2, f"Подтверждённая категория: {g.profession} · {name}"))
        elif _rank(v.grade_min) <= _rank(g.grade.value) <= _rank(v.grade_max):
            plus.append(
                _plus("grade", 0.3, f"Ваш подтверждённый грейд {name} входит в диапазон вакансии")
            )
        else:
            minus.append(f"Грейд {name} вне диапазона вакансии")

    # навыки: подтверждённые из требований вакансии, без вакансии — самые сильные свои
    if v is not None:
        req = [(vs, slug) for vs, slug in (await vacancies.skills_of(session, [v.id]))[v.id]]
        ids = [vs.skill_id for vs, _ in req]
    else:
        req, ids = [], []
    if ids:
        rows = await graph.skills_of_candidates(session, [cand.user_id], ids)
    else:
        rows = (await graph.all_skills_of(session, [cand.user_id]))[cand.user_id]
    edges = {e.skill_id: e for e in rows}

    def confirmed(skill_id: uuid.UUID) -> bool:
        e = edges.get(skill_id)
        return e is not None and e.confidence >= SKILL_CONFIRMED

    if v is not None:
        names = await taxonomy.skill_names(session, ids)
        have = [names.get(vs.skill_id, slug) for vs, slug in req if confirmed(vs.skill_id)]
        miss = [
            names.get(vs.skill_id, slug)
            for vs, slug in req
            if vs.required and not confirmed(vs.skill_id)
        ]
        if have:
            text = "Подтверждены навыки: " + ", ".join(have[:5])
            plus.append(_plus("skills", round(0.4 * len(have) / len(req), 4), text))
        minus += [f"Не подтверждён навык: {n}" for n in miss]
    else:
        top = sorted(
            (e for e in edges.values() if confirmed(e.skill_id)), key=lambda e: -e.confidence
        )
        if top[:3]:
            names = await taxonomy.skill_names(session, [e.skill_id for e in top[:3]])
            text = "Подтверждены навыки: " + ", ".join(names[e.skill_id] for e in top[:3])
            plus.append(_plus("skills", 0.35, text))

    # вилка против ожиданий
    rng = f"{_fmt(offer.salary_from)}–{_fmt(offer.salary_to)} ₽"
    if cand.salary_min is not None:
        if offer.salary_to >= cand.salary_min:
            plus.append(_plus("salary", 0.2, f"Вилка {rng} не ниже ваших ожиданий"))
        else:
            minus.append(f"Верх вилки {rng} ниже ваших ожиданий")

    # формат работы
    if v is not None and v.formats and cand.formats:
        if set(v.formats) & set(cand.formats):
            plus.append(_plus("format", 0.15, "Формат работы совпадает с вашими предпочтениями"))
        else:
            minus.append("Формат работы не совпадает с вашими предпочтениями")

    plus.sort(key=lambda f: -f.weight)
    return WhyYou(factors=plus[:TOP_FACTORS], unconfirmed=minus)


async def company_reliability(
    session: AsyncSession, company_id: uuid.UUID, score: float | None, now: datetime | None = None
) -> CompanyReliability:
    """Доля ответов и средний срок: отклики кандидатов и открытые кандидатом интересы.

    Закрытые случаи окна: ответ — просмотр/решение по отклику, приглашение по открытому
    интересу; не ответ — срок вышел (`expired`) без ответа. Ещё ждущие ответа не считаются.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=WINDOW_DAYS)
    rows = await session.scalars(
        select(Offer).where(
            Offer.company_id == company_id,
            Offer.created_at >= since,
            (Offer.initiator == "candidate") | Offer.interest_opened_at.is_not(None),
        )
    )
    answered: list[float] = []
    silent = 0
    for o in rows:
        start, end = (
            (o.created_at, o.viewed_at or o.responded_at)
            if o.initiator == "candidate"
            else (o.interest_opened_at, o.invited_at or o.responded_at)
        )
        if end is not None and start is not None:
            a, b = _aware(start), _aware(end)
            answered.append(max(0.0, (b - a).total_seconds() / 3600))
        elif o.status == "expired":
            silent += 1
    n = len(answered) + silent
    if n < MIN_SAMPLE:
        return CompanyReliability(responsibility_score=score, sample=n)
    return CompanyReliability(
        responsibility_score=score,
        sample=n,
        response_rate=round(len(answered) / n, 4),
        avg_response_hours=round(sum(answered) / len(answered), 1) if answered else None,
    )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
