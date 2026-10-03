"""Резюме: загрузка, приём результата разбора, подтверждение → evidence (ml.md §2, api.md §2.3).

Файл кладётся в MinIO, в outbox уходит команда `ml.resume.parse`. Результат приходит событием
`ml.resume.completed|failed` (обработчик в `handlers.py`). Подтверждение превращает навыки со
slug в доказательства `source=resume`, а правки кандидата — в `source=self`.
"""

from __future__ import annotations

import hashlib
import io
import uuid
import zipfile
from datetime import UTC, date, datetime

import structlog
from fsp_contracts import new_envelope
from fsp_contracts.commands import MlResumeParse
from fsp_contracts.enums import EvidenceSource
from fsp_contracts.events import ResumeEvent
from fsp_contracts.ml import ParsedResume, ResumeEducation, ResumeExperience
from fsp_platform.app import ProblemError
from fsp_platform.outbox import add_to_outbox
from fsp_platform.storage import ObjectStorage
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates.models import Candidate
from app.graph import service as graph
from app.graph.service import EvidenceIn
from app.identity.models import utcnow
from app.resumes.models import Education, Experience, Resume
from app.taxonomy.models import Skill
from app.taxonomy.service import get_version

log = structlog.get_logger()

MAX_BYTES = 10 * 1024 * 1024  # security.md §3
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
UPLOAD_LIMIT = 10  # в сутки (messaging.md §7)
UPLOAD_WINDOW = 24 * 3600

STRENGTH_LISTED = 0.25  # навык из блока «Навыки» без привязки к опыту
STRENGTH_EXPERIENCE = 0.30  # навык упомянут в опыте
STRENGTH_LONG = 0.40  # …в опыте длительностью >= 12 мес
STRENGTH_SELF = 0.15  # добавлено кандидатом вручную
LONG_MONTHS = 12


# ---------------------------------------------------------------------------- файл
def detect_mime(data: bytes) -> str | None:
    """Тип по сигнатуре, а не по расширению (security.md §3). Содержимое не исполняется."""
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return None
        if "[Content_Types].xml" in names and "word/document.xml" in names:
            return DOCX
    return None


def file_key(candidate_id: uuid.UUID, resume_id: uuid.UUID, mime: str) -> str:
    ext = "pdf" if mime == PDF else "docx"
    return f"resumes/{candidate_id}/{resume_id}.{ext}"


async def upload(
    session: AsyncSession, storage: ObjectStorage, candidate_id: uuid.UUID, data: bytes
) -> tuple[Resume, uuid.UUID]:
    """Сохранить файл, создать запись и поставить `ml.resume.parse` (одна транзакция с outbox)."""
    if not data:
        raise ProblemError(422, "empty_file", "Пустой файл")
    if len(data) > MAX_BYTES:
        raise ProblemError(413, "file_too_large", "Файл больше 10 МБ")
    mime = detect_mime(data)
    if mime is None:
        raise ProblemError(415, "unsupported_file_type", "Нужен PDF или DOCX")
    resume_id = uuid.uuid4()
    key = file_key(candidate_id, resume_id, mime)
    sha = hashlib.sha256(data).hexdigest()
    await storage.put(key, data, mime)
    resume = Resume(
        id=resume_id,
        candidate_id=candidate_id,
        file_key=key,
        sha256=sha,
        mime=mime,
        status="queued",
    )
    session.add(resume)
    await session.flush()
    cmd = MlResumeParse(
        resume_id=resume_id,
        candidate_id=candidate_id,
        object_key=key,
        mime=mime,  # type: ignore[arg-type]
        sha256=sha,
        taxonomy_version=await get_version(session),
    )
    env = new_envelope("ml.resume.parse", "core", cmd)
    await add_to_outbox(session, env, candidate_id)
    return resume, env.message_id


async def get_owned(session: AsyncSession, candidate_id: uuid.UUID, resume_id: uuid.UUID) -> Resume:
    """Чужое резюме неотличимо от несуществующего."""
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.candidate_id != candidate_id:
        raise ProblemError(404, "resume_not_found", "Резюме не найдено")
    return resume


# ------------------------------------------------------------------ результат разбора
async def apply_result(
    session: AsyncSession,
    resume_id: uuid.UUID,
    candidate_id: uuid.UUID,
    parsed: ParsedResume | None,
    error: str | None,
) -> Resume | None:
    """Записать результат ml. Подтверждённое резюме и чужие/неизвестные id не трогаем."""
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.candidate_id != candidate_id:
        log.warning("resume_result_unknown", resume_id=str(resume_id))
        return None
    if resume.status == "confirmed":
        return None
    if parsed is not None:
        resume.status = "parsed"
        resume.parsed = parsed.model_dump(mode="json")
        resume.parser_version = parsed.parser_version
        resume.error = None
        await add_to_outbox(
            session,
            new_envelope(
                "resume.parsed", "core", ResumeEvent(resume_id=resume_id, candidate_id=candidate_id)
            ),
            candidate_id,
        )
    else:
        resume.status = "failed"
        resume.error = error or "unknown"
    await session.flush()
    return resume


# ------------------------------------------------------------------------ подтверждение
class ParsedResumeEdits(BaseModel):
    """Правки кандидата при подтверждении (api.md §3)."""

    model_config = ConfigDict(extra="forbid")

    remove_skills: list[str] = Field(default_factory=list, max_length=200)
    add_skills: list[str] = Field(default_factory=list, max_length=50)
    experience: list[ResumeExperience] | None = Field(default=None, max_length=50)
    education: list[ResumeEducation] | None = Field(default=None, max_length=20)


def parse_month(value: str | None) -> date | None:
    if not value:
        return None
    try:
        y, m = value.strip()[:7].split("-")
        return date(int(y), int(m), 1)
    except (ValueError, TypeError):
        return None


def _months(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month)


def experience_months(items: list[ResumeExperience], today: date) -> int:
    """Сумма непересекающихся интервалов коммерческого опыта (ml.md §2.6)."""
    spans: list[tuple[date, date]] = []
    for e in items:
        start = parse_month(e.start)
        if start is None or not e.is_commercial:
            continue
        end = parse_month(e.end) or today
        if end > start:
            spans.append((start, end))
    spans.sort()
    total, cur_s, cur_e = 0, None, None
    for s, e in spans:
        if cur_e is None or s > cur_e:
            if cur_s is not None and cur_e is not None:
                total += _months(cur_s, cur_e)
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_s is not None and cur_e is not None:
        total += _months(cur_s, cur_e)
    return total


def skill_strength(slug: str, experience: list[ResumeExperience], today: date) -> float:
    """Сила доказательства из резюме (ml.md §2.7): 0.25 / 0.30 / 0.40."""
    best = STRENGTH_LISTED
    for e in experience:
        if slug not in e.skills:
            continue
        best = max(best, STRENGTH_EXPERIENCE)
        start = parse_month(e.start)
        if start is not None and _months(start, parse_month(e.end) or today) >= LONG_MONTHS:
            best = STRENGTH_LONG
    return best


async def _skills_by_slug(session: AsyncSession, slugs: set[str]) -> dict[str, Skill]:
    """slug → навык; слитые вершины разворачиваются в целевую."""
    if not slugs:
        return {}
    rows = {s.slug: s for s in await session.scalars(select(Skill).where(Skill.slug.in_(slugs)))}
    for slug, sk in list(rows.items()):
        if sk.merged_into is not None:
            target = await session.get(Skill, sk.merged_into)
            if target is not None:
                rows[slug] = target
    return rows


async def confirm(
    session: AsyncSession, resume: Resume, edits: ParsedResumeEdits, today: date | None = None
) -> Resume:
    """Подтвердить разбор: факты → evidence, опыт и образование → таблицы, пересчёт профиля."""
    if resume.status == "confirmed":
        return resume  # повтор безвреден
    if resume.status != "parsed" or resume.parsed is None:
        raise ProblemError(409, "resume_not_parsed", "Резюме ещё не разобрано")
    today = today or datetime.now(UTC).date()
    parsed = ParsedResume.model_validate(resume.parsed)
    experience = edits.experience if edits.experience is not None else parsed.experience
    education = edits.education if edits.education is not None else parsed.education
    removed = set(edits.remove_skills)

    resume_slugs = {s.slug for s in parsed.skills if s.slug and s.slug not in removed}
    added = [s for s in dict.fromkeys(edits.add_skills) if s not in resume_slugs]
    exp_slugs = {slug for e in experience for slug in e.skills}
    by_slug = await _skills_by_slug(session, resume_slugs | set(added) | exp_slugs)
    unknown = [s for s in added if s not in by_slug]
    if unknown:
        raise ProblemError(
            422,
            "unknown_skill",
            "Неизвестный навык",
            errors=[{"field": "add_skills", "message": s} for s in unknown],
        )

    cand = await session.get(Candidate, resume.candidate_id)
    if cand is None:
        raise ProblemError(404, "resume_not_found", "Резюме не найдено")

    items: list[EvidenceIn] = []
    soft: list[str] = []
    seen: set[tuple[uuid.UUID, str]] = set()

    def add(slug: str, source: EvidenceSource, strength: float) -> None:
        sk = by_slug.get(slug)
        if sk is None:  # slug из резюме, которого нет в графе: пропускаем
            return
        if sk.kind == "soft":  # софт-навыки заявлены, но не доказаны (skills.md §8)
            if sk.name not in soft:
                soft.append(sk.name)
            return
        if (sk.id, source) in seen:
            return
        seen.add((sk.id, source))
        items.append(
            EvidenceIn(
                skill_id=sk.id,
                source=source,
                strength=strength,
                observed_at=today,
                fact_type="resume",
                fact_id=resume.id,
                details={"resume_id": str(resume.id)},
                verified=False,
            )
        )

    for slug in sorted(resume_slugs):
        add(slug, EvidenceSource.resume, skill_strength(slug, experience, today))
    for slug in added:
        add(slug, EvidenceSource.self_, STRENGTH_SELF)

    # прошлые подтверждённые резюме заменяются новым
    prev = await session.scalars(
        select(Resume.id).where(
            Resume.candidate_id == resume.candidate_id,
            Resume.status == "confirmed",
            Resume.id != resume.id,
        )
    )
    for old_id in prev:
        await graph.deactivate(session, resume.candidate_id, fact_type="resume", fact_id=old_id)
    res = await graph.upsert_evidence(session, resume.candidate_id, items)

    await session.execute(
        delete(Experience).where(
            Experience.candidate_id == resume.candidate_id, Experience.source == "resume"
        )
    )
    await session.execute(delete(Education).where(Education.candidate_id == resume.candidate_id))
    for e in experience:
        session.add(
            Experience(
                candidate_id=resume.candidate_id,
                company=e.company,
                title=e.title,
                start_date=parse_month(e.start),
                end_date=parse_month(e.end),
                description=e.description,
                skill_ids=[str(by_slug[s].id) for s in e.skills if s in by_slug],
                is_commercial=e.is_commercial,
                source="resume",
            )
        )
    for ed in education:
        session.add(
            Education(
                candidate_id=resume.candidate_id,
                institution=ed.institution,
                degree=ed.degree,
                field=ed.field,
                year_end=ed.year_end,
            )
        )

    cand.claimed_soft = soft
    cand.experience_months = (
        experience_months(experience, today)
        if edits.experience is not None
        else parsed.total_experience_months
    )
    resume.status = "confirmed"
    resume.confirmed_at = utcnow()
    await session.flush()
    await add_to_outbox(
        session,
        new_envelope(
            "resume.confirmed",
            "core",
            ResumeEvent(resume_id=resume.id, candidate_id=resume.candidate_id),
        ),
        resume.candidate_id,
    )
    if not res.changed:  # стаж и софт-навыки тоже влияют на профиль
        await graph.request_recompute(session, resume.candidate_id)
    return resume


async def experience_for_profile(session: AsyncSession, candidate_id: uuid.UUID) -> list[dict]:
    """Опыт для `CandidateProfile.experience`: свежие первыми, навыки — slug."""
    rows = list(
        await session.scalars(
            select(Experience)
            .where(Experience.candidate_id == candidate_id)
            .order_by(Experience.start_date.desc().nulls_last(), Experience.id)
        )
    )
    ids = {uuid.UUID(s) for r in rows for s in (r.skill_ids or [])}
    slugs: dict[uuid.UUID, str] = {}
    if ids:
        found = await session.execute(select(Skill.id, Skill.slug).where(Skill.id.in_(ids)))
        slugs = {sid: slug for sid, slug in found.all()}
    return [
        {
            "title": r.title,
            "company": r.company,
            "start": r.start_date.strftime("%Y-%m") if r.start_date else None,
            "end": r.end_date.strftime("%Y-%m") if r.end_date else None,
            "skills": [slugs[uuid.UUID(s)] for s in (r.skill_ids or []) if uuid.UUID(s) in slugs],
        }
        for r in rows
    ]
