"""Подграф доказательств кандидата (graph.md §6): `GET /candidates/me/graph` и анонимный вариант.

Собирается из проекций (`candidate_skills`, `evidence`, `skill_relations`, `fsp_competitions`),
граф не обходится глубже одного шага. Анонимная версия: нет URL репозиториев, названий компаний
и имён участников команд (только «команда, N участников»); репозитории скрыты при
`visibility.repos=false`, команды и соревнования — при `visibility.teams=false`.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.fsp_models import FspCompetitionRow
from app.graph.trust import EvidenceView, TrustConfig, effective_strength
from app.taxonomy import service as taxonomy
from app.taxonomy.models import SkillRelation

TOP_SKILLS = 12
CAND = "cand"

FACT_KINDS = {  # fact_type → (префикс id, тип вершины)
    "fsp_result": ("fsp", "fsp_result"),
    "fsp_rank": ("rank", "fsp_result"),
    "test_attempt": ("test", "test"),
    "code_repo": ("repo", "repo"),
    "ai_interview": ("interview", "interview"),
    "interview": ("interview", "interview"),
    "codeforces": ("cf", "competition"),
}

NodeType = Literal[
    "candidate", "skill", "fsp_result", "repo", "test", "interview", "experience",
    "competition", "team",
]  # fmt: skip
EdgeType = Literal["has_fact", "confirms", "owns", "adjacent", "parent", "at", "member_of"]


class Node(BaseModel):
    id: str
    type: NodeType
    label: str
    level: int | None = None
    confidence: float | None = None
    date: str | None = None
    verified: bool | None = None
    derived_from: str | None = None
    ghost: bool | None = None
    # тип навыка (assessment.md §2: fundamental | hard | thinking | business | soft | experience)
    skill_type: str | None = None


class Edge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")  # `from` — слово Python; в JSON поле `from`
    to: str
    type: EdgeType
    strength: float | None = None
    weight: float | None = None
    evidence_id: str | None = None


class Highlight(BaseModel):
    requirement: str
    path: list[str]


class Subgraph(BaseModel):
    profile_version: int
    nodes: list[Node]
    edges: list[Edge]
    highlight: list[Highlight] = []


def _fact_label(fact_type: str, details: dict[str, Any]) -> str:
    if fact_type in ("fsp_result", "fsp_rank"):
        label = details.get("label")
        if isinstance(label, str) and label:
            return label
        if fact_type == "fsp_rank" and details.get("rank"):
            return f"Разряд ФСП: {details['rank']}"
        return "Результат ФСП"
    if fact_type == "test_attempt":
        prof, grade = details.get("profession"), details.get("grade")
        return f"Тест: {prof}, {grade}" if prof and grade else "Тест навыков"
    if fact_type == "code_repo":
        return "Публичный репозиторий"
    if fact_type in ("ai_interview", "interview"):
        return "ИИ-интервью"
    return "Рейтинг Codeforces"


async def build(
    session: AsyncSession,
    cand: Candidate,
    *,
    trust: TrustConfig,
    anonymous: bool,
    skills: Literal["top", "all"] = "top",
    depth: Literal["facts", "competitions"] = "facts",
    vacancy_id: uuid.UUID | None = None,
    today: date | None = None,
) -> Subgraph:
    day = today or datetime.now(UTC).date()
    vis = {"repos": False, "teams": True, **(cand.visibility or {})}
    owned = (await graph.all_skills_of(session, [cand.user_id]))[cand.user_id]
    chosen = sorted(owned, key=lambda s: (s.claimed_only, -s.confidence, str(s.skill_id)))
    if skills == "top":
        chosen = chosen[:TOP_SKILLS]
    briefs = await taxonomy.skill_briefs(session, [s.skill_id for s in chosen])
    chosen = [s for s in chosen if s.skill_id in briefs]
    slug_of = {s.skill_id: briefs[s.skill_id][0] for s in chosen}
    types = await taxonomy.skill_types_of(session, list(slug_of.values()))

    nodes: dict[str, Node] = {CAND: Node(id=CAND, type="candidate", label=cand.pseudonym)}
    edges: list[Edge] = []
    for s in chosen:
        slug, name, _grp, _st = briefs[s.skill_id]
        nodes[f"s:{slug}"] = Node(
            id=f"s:{slug}", type="skill", label=name, level=s.level,
            confidence=round(s.confidence, 4),
            derived_from=f"s:{briefs[s.derived_from][0]}" if s.derived_from in briefs else None,
            skill_type=types[slug].value if slug in types else None,
        )  # fmt: skip

    # факты → навыки (источник test входит наравне с остальными)
    evidence = await graph.evidence_of(session, [cand.user_id], skill_ids=list(slug_of))
    confirmed: set[uuid.UUID] = set()
    best_fact: dict[uuid.UUID, tuple[float, str]] = {}
    comp_ids: dict[str, list[str]] = defaultdict(list)  # competition_id → [fact node id]
    team_of: dict[str, int] = {}
    for ev in evidence:
        kind = FACT_KINDS.get(ev.fact_type)
        if kind is None:  # заявлено (self/resume) показывается ребром owns, не фактом
            continue
        prefix, ntype = kind
        d = ev.details or {}
        if anonymous and (
            (ev.fact_type == "code_repo" and not vis["repos"]) or d.get("hidden") is True
        ):
            continue
        fid = f"f:{prefix}:{ev.fact_id}"
        if fid not in nodes:
            nodes[fid] = Node(
                id=fid, type=ntype, label=_fact_label(ev.fact_type, d),
                date=ev.observed_at.strftime("%Y-%m"), verified=ev.verified,
            )  # fmt: skip
            edges.append(Edge(from_=CAND, to=fid, type="has_fact"))
        s_eff = effective_strength(
            EvidenceView(ev.id, ev.source, ev.strength, ev.observed_at, ev.verified), day, trust
        )
        edges.append(
            Edge(from_=fid, to=f"s:{slug_of[ev.skill_id]}", type="confirms",
                 strength=round(s_eff, 4), evidence_id=str(ev.id))
        )  # fmt: skip
        confirmed.add(ev.skill_id)
        if s_eff >= best_fact.get(ev.skill_id, (-1.0, ""))[0]:
            best_fact[ev.skill_id] = (s_eff, fid)
        if ev.fact_type == "fsp_result" and d.get("competition_id"):
            comp_ids[str(d["competition_id"])].append(fid)
            team_of[fid] = int(d.get("team_size") or 1)

    for s in chosen:  # навык без фактов (заявлен или выведен по иерархии) — прямое ребро
        if s.skill_id not in confirmed:
            edges.append(
                Edge(from_=CAND, to=f"s:{slug_of[s.skill_id]}", type="owns",
                     weight=round(s.confidence, 4))
            )  # fmt: skip

    if depth == "competitions" and (not anonymous or vis["teams"]):
        await _competitions(session, nodes, edges, comp_ids, team_of)

    # иерархия и смежность между показанными навыками
    ids = list(slug_of)
    if len(ids) > 1:
        q = select(SkillRelation).where(
            SkillRelation.skill_a.in_(ids), SkillRelation.skill_b.in_(ids)
        )
        for r in await session.scalars(q.order_by(SkillRelation.skill_a, SkillRelation.skill_b)):
            if r.kind == "adjacent" and str(r.skill_a) > str(r.skill_b):
                continue  # в справочнике смежность хранится в обе стороны
            edges.append(
                Edge(from_=f"s:{slug_of[r.skill_a]}", to=f"s:{slug_of[r.skill_b]}",
                     type=r.kind, weight=round(r.weight, 4))  # type: ignore[arg-type]
            )  # fmt: skip

    highlight: list[Highlight] = []
    if vacancy_id is not None:
        highlight = await _highlight(session, vacancy_id, nodes, slug_of, owned, best_fact, briefs)

    edges.sort(key=lambda e: (e.type, e.from_, e.to))
    return Subgraph(
        profile_version=cand.profile_version, nodes=list(nodes.values()), edges=edges,
        highlight=highlight,
    )  # fmt: skip


async def _competitions(
    session: AsyncSession,
    nodes: dict[str, Node],
    edges: list[Edge],
    comp_ids: dict[str, list[str]],
    team_of: dict[str, int],
) -> None:
    if not comp_ids:
        return
    rows = await session.scalars(
        select(FspCompetitionRow).where(FspCompetitionRow.id.in_(list(comp_ids)))
    )
    for comp in rows:
        cid = f"c:{comp.id}"
        nodes[cid] = Node(
            id=cid, type="competition", label=comp.title or "Соревнование ФСП",
            date=comp.start_date.strftime("%Y-%m") if comp.start_date else None, verified=True,
        )  # fmt: skip
        for fid in comp_ids[str(comp.id)]:
            edges.append(Edge(from_=fid, to=cid, type="at"))
            size = team_of.get(fid, 1)
            if size > 1:  # без имён: только размер команды
                tid = f"t:{fid.removeprefix('f:fsp:')}"
                nodes[tid] = Node(id=tid, type="team", label=f"Команда, {size} участн.")
                edges.append(Edge(from_=fid, to=tid, type="member_of"))


async def _highlight(
    session: AsyncSession,
    vacancy_id: uuid.UUID,
    nodes: dict[str, Node],
    slug_of: dict[uuid.UUID, str],
    owned: list[Any],
    best_fact: dict[uuid.UUID, tuple[float, str]],
    briefs: dict[uuid.UUID, tuple[str, str, str, str]],
) -> list[Highlight]:
    """Пути под требования вакансии: вакансия → навык → кандидат → лучший факт."""
    from app.vacancies import service as vacancies

    out: list[Highlight] = []
    owned_ids = {s.skill_id for s in owned}
    for vs, slug in (await vacancies.skills_of(session, [vacancy_id]))[vacancy_id]:
        node = f"s:{slug}"
        if vs.skill_id in slug_of:
            path = ["vac", node, CAND]
            if vs.skill_id in best_fact:
                path.append(best_fact[vs.skill_id][1])
        else:
            path = ["vac", node]
            if vs.skill_id not in owned_ids and node not in nodes:  # призрак: навыка нет
                name = (await taxonomy.skill_names(session, [vs.skill_id])).get(vs.skill_id, slug)
                nodes[node] = Node(id=node, type="skill", label=name, level=0, ghost=True)
        out.append(Highlight(requirement=slug, path=path))
    return out
