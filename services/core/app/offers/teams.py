"""Команды ФСП и командный оффер (E15-2, fsp.md §6, data-model.md `offers.team_offer_id`).

- Список команд для работодателя: только участники, которые есть на платформе и видимы
  (не `dnd`, есть роль, компания не в стоп-листе, `visibility.teams` не выключен).
  Команда показывается, если видимых участников не меньше двух; скрытые не раскрываются.
- Командный оффер - N обычных офферов с общим `team_offer_id`: каждый участник принимает свой.
  Всё в одной транзакции запроса: ошибка на любом участнике откатывает весь оффер.
- Идемпотентность: ключ запроса `K` превращается в `K#<pseudo_id>` для каждого оффера
  (уникальность `company_id + idempotency_key`), повтор возвращает исходные офферы.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fsp_platform.app import ProblemError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph.fsp_models import FspCompetitionRow, FspResultRow, FspTeamMember, FspTeamRow

MIN_TEAM = 2


@dataclass(slots=True)
class TeamMemberView:
    candidate: Candidate
    role: str | None


@dataclass(slots=True)
class TeamView:
    id: str
    name: str | None
    competition_id: str | None
    competition_title: str | None
    discipline: str | None
    best_place: int | None
    members: list[TeamMemberView] = field(default_factory=list)


def team_not_found() -> ProblemError:
    return ProblemError(404, "team_not_found", "Команда не найдена")


def is_visible(c: Candidate, company_id: uuid.UUID) -> bool:
    """Кандидат виден компании в составе команды."""
    return (
        c.search_status != "dnd"
        and c.primary_role is not None
        and str(company_id) not in (c.stoplist_company_ids or ())
        and (c.visibility or {}).get("teams", True) is not False
        and c.deleted_at is None
    )


async def _load(
    session: AsyncSession, company_id: uuid.UUID, team_ids: list[str] | None
) -> list[TeamView]:
    q = (
        select(FspTeamRow, FspTeamMember, Candidate)
        .join(FspTeamMember, FspTeamMember.team_id == FspTeamRow.id)
        .join(Candidate, Candidate.user_id == FspTeamMember.candidate_id)
        .order_by(FspTeamRow.id, Candidate.pseudo_id)
    )
    if team_ids is not None:
        q = q.where(FspTeamRow.id.in_(team_ids))
    teams: dict[str, TeamView] = {}
    for team, member, cand in (await session.execute(q)).all():
        if not is_visible(cand, company_id):
            continue
        view = teams.setdefault(
            team.id,
            TeamView(team.id, team.name, team.competition_id, None, None, None),
        )
        view.members.append(TeamMemberView(cand, member.role))
    if not teams:
        return []
    comps = {
        c.id: c
        for c in (
            await session.scalars(
                select(FspCompetitionRow).where(
                    FspCompetitionRow.id.in_({t.competition_id for t in teams.values()} - {None})
                )
            )
        )
    }
    places: dict[str, int] = {}
    for team_id, place in (
        await session.execute(
            select(FspResultRow.team_id, FspResultRow.place).where(
                FspResultRow.team_id.in_(list(teams)),
                FspResultRow.is_active.is_(True),
                FspResultRow.place.is_not(None),
            )
        )
    ).all():
        places[team_id] = min(place, places.get(team_id, place))
    for t in teams.values():
        comp = comps.get(t.competition_id) if t.competition_id else None
        t.competition_title = comp.title if comp else None
        t.discipline = comp.discipline if comp else None
        t.best_place = places.get(t.id)
    return list(teams.values())


async def list_teams(
    session: AsyncSession,
    company_id: uuid.UUID,
    *,
    discipline: str | None = None,
    min_place: int | None = None,
    limit: int = 100,
) -> list[TeamView]:
    """Команды, где у компании есть минимум два видимых участника платформы."""
    out = []
    for t in await _load(session, company_id, None):
        if len(t.members) < MIN_TEAM:
            continue
        if discipline and t.discipline != discipline:
            continue
        if min_place is not None and (t.best_place is None or t.best_place > min_place):
            continue
        out.append(t)
    out.sort(key=lambda t: (t.best_place is None, t.best_place or 0, t.id))
    return out[:limit]


async def get_team(session: AsyncSession, company_id: uuid.UUID, team_id: str) -> TeamView:
    teams = await _load(session, company_id, [team_id])
    if not teams or len(teams[0].members) < MIN_TEAM:
        raise team_not_found()
    return teams[0]


def member_by_pseudo(team: TeamView, pseudo_id: str) -> Candidate:
    for m in team.members:
        if m.candidate.pseudo_id == pseudo_id:
            return m.candidate
    raise ProblemError(404, "candidate_not_found", "Кандидат не найден в этой команде")
