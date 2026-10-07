"""HTTP `/admin/professions*`, `/admin/skill-cards*` (E13-1a): справочник для роли `fsp_admin`."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fsp_contracts.assessment import ProfessionInfo, ProfessionSlug
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session
from app.identity.deps import require_roles
from app.identity.models import User
from app.openapi_errors import problem_responses
from app.taxonomy import admin
from app.taxonomy.cards import SkillCard

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
    active: bool | None = None  # E36-2: скрыть / показать профессию в опросе и UI


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
    """Название, веса навыков (замена целиком) и/или видимость `active`."""
    info, version = await admin.update_profession(
        session, slug, body.title, body.skill_weights, active=body.active
    )
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
