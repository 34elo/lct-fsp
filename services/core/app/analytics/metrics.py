"""Онлайн-метрики v2 (E31-4, metrics.md §9.2–9.3): воронки, приглашения, отклики.

Считаем по `analytics_events` на лету, как дашборд ФСП (без материализованных представлений:
так одинаково работает в SQLite тестов и в PostgreSQL). Только агрегаты по псевдонимам;
ячейки меньше `MIN_CELL` человек (событий для распределений) скрываются. Без ПДн и текстов.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection
from datetime import UTC, datetime, timedelta
from statistics import median

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.dashboard import DEFAULT_DAYS, MAX_DAYS, MIN_CELL
from app.analytics.models import AnalyticsEventRow as E

Pred = Callable[[str, dict], bool]

INVITE_WINDOW_DAYS = 14
RESPOND_SLA_S = 72 * 3600

_TEST_STARTED = ("test_started", "assessment_started", "assessment_attempt_started")
_TEST_FINISHED = (
    "test_completed",
    "assessment_finished",
    "assessment_completed",
    "assessment_attempt_finished",
)

# Воронка кандидата. Шаги без единого события в окне помечаются `available=False`
# и в цепочку конверсий не входят (событий Б1 `survey_*`/`assessment_*` может ещё не быть).
CANDIDATE_STAGES: list[tuple[str, str, Pred]] = [
    ("registered", "Регистрация", lambda e, p: e == "signup_completed"),
    ("email", "Подтвердили email", lambda e, p: e == "email_verified"),
    ("survey", "Прошли опрос", lambda e, p: e.startswith("survey_")),
    ("test_started", "Начали тест", lambda e, p: e in _TEST_STARTED),
    ("test_finished", "Завершили тест", lambda e, p: e in _TEST_FINISHED),
    ("category", "Получили категорию", lambda e, p: e == "category_changed"),
]
# Воронка работодателя: когорта — те, кто создал потребность.
EMPLOYER_STAGES: list[tuple[str, str, Pred]] = [
    ("need", "Создали потребность", lambda e, p: e == "need_created"),
    ("viewed", "Открыли категорию", lambda e, p: e == "category_viewed"),
    ("shortlist", "Добавили в шорт-лист", lambda e, p: e == "shortlist_added"),
    ("invite", "Отправили приглашение", lambda e, p: e in ("invite_sent", "offer_sent")),
]
# Воронка интереса (встречный оффер E33): интерес → открыл → приглашение → принял
INTEREST_STAGES: list[tuple[str, str, Pred]] = [
    ("shown", "Показали интерес", lambda e, p: e == "interest_shown"),
    (
        "opened",
        "Открыли интерес",
        lambda e, p: e == "interest_answered" and p.get("decision") == "opened",
    ),
    ("invited", "Отправили приглашение", lambda e, p: e == "interest_to_invite"),
    (
        "accepted",
        "Приняли приглашение",
        lambda e, p: e == "invite_answered" and p.get("decision") == "accepted",
    ),
]
_EVENTS = {
    "signup_completed", "email_verified", "category_changed",
    "need_created", "category_viewed", "shortlist_added", "invite_sent", "offer_sent",
    "invite_answered", "offer_accepted", "offer_declined", "offer_received",
    "response_created", "response_answered",
    "interest_shown", "interest_answered", "interest_to_invite",
    *_TEST_STARTED, *_TEST_FINISHED,
}  # fmt: skip


class Stage(BaseModel):
    id: str
    title: str
    available: bool  # были ли события шага в окне
    count: int | None  # None, если ячейка меньше MIN_CELL
    hidden: bool
    pct_of_first: float | None
    pct_of_previous: float | None


class Funnel(BaseModel):
    stages: list[Stage]


class Timing(BaseModel):
    """Время до события: медиана в секундах и число наблюдений (малые выборки скрыты)."""

    n: int | None
    median_s: int | None
    hidden: bool


class ReasonShare(BaseModel):
    reason: str
    count: int


class InviteMetrics(BaseModel):
    sent: int | None
    answered: int | None
    accepted: int | None
    declined: int | None
    expired: int | None
    accept_rate: float | None  # принятые / отправленные, %
    respond_72h_rate: float | None  # ответили за 72 ч / отвеченные со временем ответа, %
    first_invite: Timing  # регистрация → первое приглашение (по кандидату)
    invited_within_14d_pct: float | None  # доля когорты с приглашением за 14 дней
    need_to_invite: Timing  # потребность → приглашение (`time_since_need_s`)
    decline_reasons: list[ReasonShare]  # только причины, набравшие >= MIN_CELL


class ResponseMetrics(BaseModel):
    created: int | None
    answered: int | None
    accepted: int | None
    answer_rate: float | None
    accept_rate: float | None  # принятые / отвеченные, %
    time_to_answer: Timing


class InterestMetrics(BaseModel):
    """Метрики встречного оффера (интерес кандидата): интерес → открыл → приглашение → принял."""

    shown: int | None
    opened: int | None
    invited: int | None
    accepted: int | None
    open_rate: float | None  # открыли / показали, %
    invite_rate: float | None  # пригласили / открыли, %
    accept_rate: float | None  # приняли / пригласили, %
    first_contact: Timing  # регистрация → открытие интереса
    time_to_invite: Timing  # интерес → приглашение
    decline_reasons: list[ReasonShare]  # причины отказа от интереса


class MetricsOut(BaseModel):
    since: datetime
    days: int
    min_cell: int
    candidate_funnel: Funnel
    employer_funnel: Funnel
    invites: InviteMetrics
    responses: ResponseMetrics
    interests: InterestMetrics


Row = tuple[str, str | None, dict, datetime]


def _pct(n: int, d: int) -> float | None:
    if n < MIN_CELL or d < MIN_CELL:
        return None
    return round(100 * n / d, 1)


def _count(n: int) -> int | None:
    return None if n < MIN_CELL else n


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def _timing(values: list[int]) -> Timing:
    if len(values) < MIN_CELL:
        return Timing(n=None, median_s=None, hidden=True)
    return Timing(n=len(values), median_s=int(median(values)), hidden=False)


def _num(props: dict, key: str) -> int | None:
    v = props.get(key)
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def funnel(rows: list[Row], stages: list[tuple[str, str, Pred]]) -> Funnel:
    """Когортная воронка: когорта — актёры первого шага; дальше пересечение с ней."""
    sets = [{a for e, a, p, _ in rows if a and pred(e, p)} for _, _, pred in stages]
    cohort = sets[0]
    out: list[Stage] = []
    prev = len(cohort)
    for i, (sid, title, _) in enumerate(stages):
        n = len(cohort) if i == 0 else len(sets[i] & cohort)
        available = bool(sets[i])
        shown = i > 0 and available
        out.append(
            Stage(
                id=sid,
                title=title,
                available=available,
                count=_count(n),
                hidden=n < MIN_CELL,
                pct_of_first=_pct(n, len(cohort)) if shown else None,
                pct_of_previous=_pct(n, prev) if shown else None,
            )
        )
        if available:
            prev = n
    return Funnel(stages=out)


def invites(rows: list[Row]) -> InviteMetrics:
    sent = [r for r in rows if r[0] in ("invite_sent", "offer_sent")]
    answered = [r for r in rows if r[0] == "invite_answered"]
    decisions = Counter(r[2].get("decision") for r in answered)
    if not answered:  # прежние события, пока нет новых: иначе считали бы дважды
        decisions = Counter(
            accepted=sum(r[0] == "offer_accepted" for r in rows),
            declined=sum(r[0] == "offer_declined" for r in rows),
        )
    n_answered = sum(decisions.values())
    times = [t for r in answered if (t := _num(r[2], "time_to_respond_s")) is not None]
    reasons = Counter(
        r[2]["reason"]
        for r in answered
        if r[2].get("decision") == "declined" and r[2].get("reason")
    )

    signup: dict[str, datetime] = {}
    for e, a, _, ts in rows:
        if e == "signup_completed" and a:
            signup[a] = min(ts, signup.get(a, ts))
    first_invite: dict[str, datetime] = {}
    for e, a, _, ts in rows:
        if e == "offer_received" and a in signup:
            first_invite[a] = min(ts, first_invite.get(a, ts))
    deltas = [max(0, int((first_invite[a] - signup[a]).total_seconds())) for a in first_invite]
    within = sum(d <= INVITE_WINDOW_DAYS * 86400 for d in deltas)
    need_times = [
        t
        for e, _, p, _ in rows
        if e == "invite_sent" and (t := _num(p, "time_since_need_s")) is not None
    ]
    return InviteMetrics(
        sent=_count(len(sent)),
        answered=_count(n_answered),
        accepted=_count(decisions.get("accepted", 0)),
        declined=_count(decisions.get("declined", 0)),
        expired=_count(decisions.get("expired", 0)),
        accept_rate=_pct(decisions.get("accepted", 0), len(sent)),
        respond_72h_rate=_pct(sum(t <= RESPOND_SLA_S for t in times), len(times)),
        first_invite=_timing(deltas),
        invited_within_14d_pct=_pct(within, len(signup)),
        need_to_invite=_timing(need_times),
        decline_reasons=[
            ReasonShare(reason=r, count=n) for r, n in reasons.most_common() if n >= MIN_CELL
        ],
    )


def responses(rows: list[Row]) -> ResponseMetrics:
    created = [r for r in rows if r[0] == "response_created"]
    answered = [r for r in rows if r[0] == "response_answered"]
    accepted = sum(r[2].get("decision") == "accepted" for r in answered)
    times = [t for r in answered if (t := _num(r[2], "time_to_answer_s")) is not None]
    return ResponseMetrics(
        created=_count(len(created)),
        answered=_count(len(answered)),
        accepted=_count(accepted),
        answer_rate=_pct(len(answered), len(created)),
        accept_rate=_pct(accepted, len(answered)),
        time_to_answer=_timing(times),
    )


def interests(rows: list[Row]) -> InterestMetrics:
    """Метрики встречного оффера: интерес → открыл → приглашение → принял (E33-8)."""
    shown = [r for r in rows if r[0] == "interest_shown"]
    opened = [r for r in rows if r[0] == "interest_answered" and r[2].get("decision") == "opened"]
    invited = [r for r in rows if r[0] == "interest_to_invite"]

    # Для принятия: смотрим invite_answered события, где открыли интерес
    # (то есть candidates из interest_opened intersection с invite_answered decision=accepted)
    interest_candidates = {r[1] for r in opened}
    accepted_from_interest = [
        r
        for r in rows
        if (
            r[0] == "invite_answered"
            and r[2].get("decision") == "accepted"
            and r[1] in interest_candidates
        )
    ]

    # Причины отказа от интереса
    declined = [
        r for r in rows if r[0] == "interest_answered" and r[2].get("decision") == "declined"
    ]
    reasons = Counter(r[2]["reason"] for r in declined if r[2].get("reason"))

    # Время от регистрации до открытия интереса (first contact)
    signup: dict[str, datetime] = {}
    for e, a, _, ts in rows:
        if e == "signup_completed" and a:
            signup[a] = min(ts, signup.get(a, ts))

    open_times: list[int] = []
    for r in opened:
        if r[1] in signup:
            open_times.append(max(0, int((r[3] - signup[r[1]]).total_seconds())))

    # Время от открытия интереса до приглашения
    invite_times: list[int] = []
    for inv_r in invited:
        for open_r in opened:
            if open_r[1] == inv_r[1]:  # same candidate
                invite_times.append(max(0, int((inv_r[3] - open_r[3]).total_seconds())))
                break

    return InterestMetrics(
        shown=_count(len(shown)),
        opened=_count(len(opened)),
        invited=_count(len(invited)),
        accepted=_count(len(accepted_from_interest)),
        open_rate=_pct(len(opened), len(shown)),
        invite_rate=_pct(len(invited), len(opened)),
        accept_rate=_pct(len(accepted_from_interest), len(invited)),
        first_contact=_timing(open_times),
        time_to_invite=_timing(invite_times),
        decline_reasons=[
            ReasonShare(reason=r, count=n) for r, n in reasons.most_common() if n >= MIN_CELL
        ],
    )


async def build(
    session: AsyncSession, days: int = DEFAULT_DAYS, *, exclude_actors: Collection[str] = ()
) -> MetricsOut:
    """Метрики за `days` дней; `exclude_actors` — псевдонимы демо-аккаунтов (E40-1)."""
    days = max(1, min(days, MAX_DAYS))
    since = datetime.now(UTC) - timedelta(days=days)
    raw = (
        await session.execute(
            select(E.event, E.actor, E.props, E.ts).where(E.ts >= since, E.event.in_(_EVENTS))
        )
    ).all()
    skip = set(exclude_actors)
    rows: list[Row] = [(e, a, p or {}, _utc(ts)) for e, a, p, ts in raw if a not in skip]
    return MetricsOut(
        since=since,
        days=days,
        min_cell=MIN_CELL,
        candidate_funnel=funnel(rows, CANDIDATE_STAGES),
        employer_funnel=funnel(rows, EMPLOYER_STAGES),
        invites=invites(rows),
        responses=responses(rows),
        interests=interests(rows),
    )
