"""HTTP `/admin/professions*`, `/admin/skill-cards*`, `/admin/profession-suggestions*`: справочник
для роли `fsp_admin`."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from fsp_contracts.assessment import ProfessionInfo, ProfessionSlug
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.taxonomy import admin
from app.taxonomy import profession_suggest as suggest
from app.taxonomy.cards import SkillCard
from app.taxonomy.models import ProfessionSuggestion, Role, Skill

router = APIRouter(prefix="/admin", tags=["admin"])
_admin = require_roles("fsp_admin")


class ProfessionOut(ProfessionInfo):
    taxonomy_version: int | None = None  # версия справочника после правки


class ProfessionIn(BaseModel):
    slug: ProfessionSlug
    title: str = Field(min_length=1, max_length=80)
    skill_weights: dict[str, float] = Field(min_length=1)


class ProfessionPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    skill_weights: dict[str, float] | None = Field(default=None, min_length=1)


class RetiredOut(BaseModel):
    slug: str
    taxonomy_version: int


class CardOut(BaseModel):
    skill: str
    source: str  # admin | file | draft
    version: int  # правки админа; у файла и черновика 0
    card: SkillCard


class CardRef(BaseModel):
    skill: str
    type: str
    source: str
    version: int


class CardSaved(CardOut):
    taxonomy_version: int


def _prof(info: ProfessionInfo, version: int | None = None) -> ProfessionOut:
    return ProfessionOut(**info.model_dump(), taxonomy_version=version)


@router.get(
    "/professions", response_model=list[ProfessionOut], responses=problem_responses(401, 403)
)
async def list_professions(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    return [_prof(p) for p in await admin.list_professions(session)]


@router.post(
    "/professions",
    status_code=201,
    response_model=ProfessionOut,
    responses=problem_responses(401, 403, 409, 422),
)
async def create_profession(
    body: ProfessionIn,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Новая профессия теста с весами навыков (покрыты все шесть типов)."""
    info, version = await admin.create_profession(
        session, body.slug, body.title, body.skill_weights
    )
    return _prof(info, version)


@router.get(
    "/professions/{slug}",
    response_model=ProfessionOut,
    responses=problem_responses(401, 403, 404),
)
async def get_profession(
    slug: str, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    return _prof(await admin.get_profession(session, slug))


@router.patch(
    "/professions/{slug}",
    response_model=ProfessionOut,
    responses=problem_responses(401, 403, 404, 422),
)
async def update_profession(
    slug: str,
    body: ProfessionPatch,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Название и/или веса навыков (замена целиком)."""
    info, version = await admin.update_profession(session, slug, body.title, body.skill_weights)
    return _prof(info, version)


@router.delete(
    "/professions/{slug}",
    response_model=RetiredOut,
    responses=problem_responses(401, 403, 404),
)
async def retire_profession(
    slug: str, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    """Снимает профессию с теста; веса остаются в справочнике."""
    return RetiredOut(slug=slug, taxonomy_version=await admin.retire_profession(session, slug))


@router.get("/skill-cards", response_model=list[CardRef], responses=problem_responses(401, 403))
async def list_cards(_: User = Depends(_admin), session: AsyncSession = Depends(get_session)):
    return [
        CardRef(skill=c.slug, type=c.card.type.value, source=c.source, version=c.version)
        for c in await admin.list_cards(session)
    ]


@router.get(
    "/skill-cards/{slug}", response_model=CardOut, responses=problem_responses(401, 403, 404)
)
async def get_card(
    slug: str, _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    c = await admin.get_card(session, slug)
    return CardOut(skill=c.slug, source=c.source, version=c.version, card=c.card)


@router.put(
    "/skill-cards/{slug}",
    response_model=CardSaved,
    responses=problem_responses(401, 403, 404, 422),
)
async def put_card(
    slug: str,
    card: SkillCard,
    _: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """Сохраняет карточку (схема `SkillCard`); тип обязан совпасть с типом навыка."""
    c, version = await admin.put_card(session, slug, card)
    return CardSaved(
        skill=c.slug, source=c.source, version=c.version, card=c.card, taxonomy_version=version
    )


# --- предложения новых профессий --------------------------------------------------------


class SuggestionSkill(BaseModel):
    slug: str
    name: str
    type: str | None = None  # SkillType
    share: float  # доля вакансий и запросов кластера с навыком


class SuggestionExample(BaseModel):
    vacancy_id: uuid.UUID | None = None
    title: str


class NearestProfession(BaseModel):
    slug: str
    title: str
    overlap: float  # доля ядра среди навыков профессии


class ProfessionSuggestionOut(BaseModel):
    id: uuid.UUID
    title: str  # название-кандидат
    skills: list[SuggestionSkill]  # ядро навыков, по убыванию частоты
    support_vacancies: int
    support_needs: int
    nearest: NearestProfession | None = None
    examples: list[SuggestionExample]
    status: Literal["open", "created", "rejected"]
    profession: str | None = None  # slug созданной профессии
    created_at: datetime


class SuggestionAccept(BaseModel):
    slug: ProfessionSlug | None = None  # по умолчанию — из ядра навыков
    title: str | None = Field(default=None, min_length=1, max_length=80)


class SuggestionAccepted(BaseModel):
    suggestion: ProfessionSuggestionOut
    profession: ProfessionOut


async def _suggestion_out(
    session: AsyncSession, rows: list[ProfessionSuggestion]
) -> list[ProfessionSuggestionOut]:
    slugs = {s for r in rows for s in r.skills}
    skills = {s.slug: s for s in await session.scalars(select(Skill).where(Skill.slug.in_(slugs)))}
    titles = dict((await session.execute(select(Role.slug, Role.name))).all())
    out = []
    for r in rows:
        near = r.nearest_profession
        out.append(
            ProfessionSuggestionOut(
                id=r.id,
                title=r.title,
                skills=[
                    SuggestionSkill(
                        slug=s,
                        name=skills[s].name if s in skills else s,
                        type=skills[s].skill_type if s in skills else None,
                        share=float(r.weights.get(s, 0.0)),
                    )
                    for s in r.skills
                ],
                support_vacancies=r.support_vacancies,
                support_needs=r.support_needs,
                nearest=NearestProfession(slug=near, title=titles[near], overlap=r.nearest_overlap)
                if near in titles
                else None,
                examples=[SuggestionExample.model_validate(e) for e in r.examples],
                status=r.status,
                profession=r.profession,
                created_at=r.created_at,
            )
        )
    return out


@router.get(
    "/profession-suggestions",
    response_model=list[ProfessionSuggestionOut],
    responses=problem_responses(401, 403),
)
async def list_profession_suggestions(
    _: User = Depends(_admin), session: AsyncSession = Depends(get_session)
):
    """Открытые предложения «Новая профессия?» (еженедельный майнинг вакансий и запросов)."""
    return await _suggestion_out(session, await suggest.list_open(session))


@router.post(
    "/profession-suggestions/{suggestion_id}/accept",
    status_code=201,
    response_model=SuggestionAccepted,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def accept_profession_suggestion(
    suggestion_id: uuid.UUID,
    body: SuggestionAccept | None = None,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """«Создать» одной кнопкой: профессия с профилем навыков (ядро + недостающие типы навыков
    ближайшей профессии, по которым есть семейства)."""
    body = body or SuggestionAccept()
    row, info, version = await suggest.accept(
        session, suggestion_id, user.id, slug=body.slug, title=body.title
    )
    (out,) = await _suggestion_out(session, [row])
    return SuggestionAccepted(suggestion=out, profession=_prof(info, version))


@router.post(
    "/profession-suggestions/{suggestion_id}/reject",
    response_model=ProfessionSuggestionOut,
    responses=problem_responses(401, 403, 404, 409),
)
async def reject_profession_suggestion(
    suggestion_id: uuid.UUID,
    user: User = Depends(_admin),
    session: AsyncSession = Depends(get_session),
):
    """«Отклонить»: решение запоминается, похожий кластер больше не предлагается."""
    row = await suggest.reject(session, suggestion_id, user.id)
    (out,) = await _suggestion_out(session, [row])
    return out
