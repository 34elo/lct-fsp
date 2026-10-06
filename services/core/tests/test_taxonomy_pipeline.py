"""E16-4: журнал решений конвейера навыков и черновики карточек (taxonomy/service.py)."""

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from app.taxonomy import service
from app.taxonomy.models import Skill, SkillCardDraftRow
from fsp_contracts.ml import (
    SkillCardConcept,
    SkillCardDraft,
    SkillCardMisconception,
    SkillResolveItem,
)
from fsp_platform.db import make_engine, make_session_factory, session_scope
from sqlalchemy import select

CORE = Path(__file__).resolve().parents[1]


@pytest.fixture
def db_url(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'p.db'}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"url={url}", "upgrade", "head"],
        cwd=CORE,
        check=True,
        capture_output=True,
    )
    return url


@pytest.fixture
async def session(db_url):
    engine = make_engine(db_url)
    async with session_scope(make_session_factory(engine)) as s:
        s.add(
            Skill(
                id=uuid.uuid4(),
                slug="helmfile",
                name="Helmfile",
                kind="hard",
                status="provisional",
                source="pipeline",
                skill_type="hard",
            )
        )
        await s.flush()
        yield s
    await engine.dispose()


def _draft(type_: str = "hard") -> dict:
    d = SkillCardDraft(
        skill="helmfile",
        type=type_,  # type: ignore[arg-type]
        summary="Описывает наборы Helm-релизов одним файлом.",
        levels={
            "junior": ["Запускает готовый helmfile", "Читает diff перед применением"],
            "middle": ["Разделяет окружения", "Использует шаблоны значений"],
            "senior": ["Строит общую библиотеку", "Откатывает релизы по плану"],
        },
        concepts=[SkillCardConcept(term=t, note="поясняющая фраза") for t in ("a", "b", "c")],
        misconceptions=[
            SkillCardMisconception(claim=f"заблуждение {i}", truth="как на самом деле")
            for i in range(2)
        ],
        model="qwen",
    )
    return d.model_dump(mode="json")


async def test_record_mention_and_cache(session):
    item = SkillResolveItem(
        raw="Helmfile",
        norm="helmfile",
        decision="new",
        skill_slug="helmfile",
        kind="hard",
        relation={"type": "narrower", "to_slug": "kubernetes", "confidence": 0.75},
    ).model_dump()
    row = await service.record_mention(session, item, context="resume", model_version="v1")
    assert row and row.skill_id and row.relation == "narrower:kubernetes"
    hit = await service.cached_decision(session, "helmfile")
    assert hit and hit.decision == "new"
    assert await service.cached_decision(session, "другое") is None


async def test_pii_mention_is_not_recorded(session):
    masked = SkillResolveItem(
        raw="[скрыто]", norm="[скрыто]", decision="rejected", kind="not_skill", reason="pii"
    ).model_dump()
    assert await service.record_mention(session, masked) is None


async def test_save_card_draft_upserts_and_validates(session):
    row = await service.save_card_draft(session, "helmfile", _draft())
    assert row.status == "draft" and row.model == "qwen" and row.card["skill"] == "helmfile"
    await service.save_card_draft(session, "helmfile", _draft())
    assert len(list(await session.scalars(select(SkillCardDraftRow)))) == 1
    with pytest.raises(ValueError, match="в справочнике"):
        await service.save_card_draft(session, "helmfile", _draft("soft"))
    with pytest.raises(ValueError, match="нет в справочнике"):
        await service.save_card_draft(session, "unknown", _draft())
