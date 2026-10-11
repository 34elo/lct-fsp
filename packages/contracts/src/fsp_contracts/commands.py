"""Команды: обменник `commands` (direct), routing key = имя очереди исполнителя.

`Envelope.type` = имя команды, AMQP priority = `CommandSpec.priority` (важно для `ml.llm`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from fsp_contracts.enums import TeamSignalKind
from fsp_contracts.ml import (
    FamilyKind,
    InterviewAnswer,
    KitGap,
    KitSkill,
    MatchToExplain,
    SkillMention,
)
from fsp_contracts.notify import NotifyTelegram

COMMANDS_EXCHANGE = "commands"

# --- ml.llm ---


class MlResumeParse(BaseModel):
    resume_id: UUID
    candidate_id: UUID  # = user_id, для прогресса в ui.user.<id>
    object_key: str  # MinIO
    mime: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    sha256: str
    taxonomy_version: int


class MlInterviewGenerate(BaseModel):
    interview_id: UUID
    candidate_id: UUID
    github_login: str
    repo_full_name: str
    head_sha: str | None = None
    questions: int = Field(default=3, ge=1, le=5)


class MlInterviewGrade(BaseModel):
    interview_id: UUID
    candidate_id: UUID
    answers: list[InterviewAnswer]


class MlInterviewKitGenerate(BaseModel):
    """Вход без ПДн."""

    kit_id: UUID
    vacancy_id: UUID
    vacancy_version: int
    candidate_id: UUID
    profile_version: int
    requirements: list[str]  # обязательные и желательные навыки вакансии, slug
    skills: list[KitSkill]
    gaps: list[KitGap] = Field(default_factory=list)
    team_signals: list[TeamSignalKind] = Field(default_factory=list)


class MlSkillsResolve(BaseModel):
    request_id: UUID
    mentions: list[SkillMention] = Field(min_length=1, max_length=50)
    taxonomy_version: int


class MlMatchesExplain(BaseModel):
    vacancy_id: UUID
    vacancy_version: int
    requirements: list[str]
    items: list[MatchToExplain] = Field(max_length=5)


class MlQuestionsGenerate(BaseModel):
    skill_slug: str
    count: int = Field(default=10, ge=1, le=30)
    difficulty: int | None = Field(default=None, ge=1, le=5)


class MlFamiliesGenerate(BaseModel):
    """Заказ админа на LLM-задания (навык × `kind` × уровень, до 10 штук).

    Низший приоритет `ml.llm`: не мешает разбору резюме и остальным задачам GPU. Ответ —
    `ml.families.started`, затем `ml.families.generated`.
    """

    order_id: UUID
    skill: str = Field(min_length=1, max_length=80)  # slug из справочника
    skill_type: str = Field(default="", max_length=40)  # SkillType навыка (подсказка генератору)
    kind: FamilyKind
    level: int = Field(ge=1, le=5)
    n: int = Field(ge=1, le=10)
    domain: str | None = Field(default=None, max_length=40)


# --- ml.code ---


class MlCodeAnalyze(BaseModel):
    analysis_id: UUID
    candidate_id: UUID
    github_login: str


# --- fsp.sync ---


class FspSync(BaseModel):
    candidate_id: UUID
    reason: Literal["linked", "webhook", "manual", "schedule"]
    since: date | None = None


class FspSyncAll(BaseModel):
    pass


# --- core.* ---


class CoreRecompute(BaseModel):
    candidate_id: UUID
    requested_at: datetime


class CoreMatchVacancy(BaseModel):
    vacancy_id: UUID
    version: int


class CoreMatchCandidate(BaseModel):
    candidate_id: UUID
    profile_version: int


class CoreJob(BaseModel):
    """Cron-команды и фоновые задачи `core.jobs`."""

    candidate_id: UUID | None = None  # для candidate.delete


@dataclass(frozen=True)
class CommandSpec:
    queue: str
    model: type[BaseModel]
    priority: int | None = None
    consumer: str = "core"


_LLM = "ml.llm"

COMMANDS: dict[str, CommandSpec] = {
    "ml.resume.parse": CommandSpec(_LLM, MlResumeParse, 9, "ml"),
    "ml.interview.grade": CommandSpec(_LLM, MlInterviewGrade, 8, "ml"),
    "ml.interview.generate": CommandSpec(_LLM, MlInterviewGenerate, 7, "ml"),
    "ml.interview_kit.generate": CommandSpec(_LLM, MlInterviewKitGenerate, 5, "ml"),
    "ml.skills.resolve": CommandSpec(_LLM, MlSkillsResolve, 3, "ml"),
    "ml.matches.explain": CommandSpec(_LLM, MlMatchesExplain, 2, "ml"),
    "ml.questions.generate": CommandSpec(_LLM, MlQuestionsGenerate, 1, "ml"),
    "ml.families.generate": CommandSpec(_LLM, MlFamiliesGenerate, 0, "ml"),  # фон
    "ml.code.analyze": CommandSpec("ml.code", MlCodeAnalyze, consumer="ml"),
    "fsp.sync": CommandSpec("fsp.sync", FspSync, consumer="fsp-connector"),
    "fsp.sync_all": CommandSpec("fsp.sync", FspSyncAll, consumer="fsp-connector"),
    "notify.telegram": CommandSpec("bot.telegram", NotifyTelegram, consumer="bot"),
    "core.recompute": CommandSpec("core.recompute", CoreRecompute),
    "core.match.vacancy": CommandSpec("core.match", CoreMatchVacancy),
    "core.match.candidate": CommandSpec("core.match", CoreMatchCandidate),
    **{
        job: CommandSpec("core.jobs", CoreJob)
        for job in (
            "offers.expire",
            "active_status.expire",
            "market.refresh",
            "company.rating",
            "candidate_links.refresh",
            "cleanup",
            "recompute_all",
            "candidate.delete",
            "taxonomy.professions.suggest",  # раз в неделю, предложения новых профессий
        )
    },
}

LLM_MAX_PRIORITY = 10  # x-max-priority очереди ml.llm
