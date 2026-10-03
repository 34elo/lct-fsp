"""Обработчики команд ml.llm / ml.code: команда → события-результаты.

Чистые функции без брокера: воркер публикует то, что они вернули. `message_id` результата
детерминирован от `message_id` команды, поэтому повторная доставка даёт дубликат,
который inbox получателя отбрасывает (AGENTS.md п. 8).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from uuid import NAMESPACE_URL, uuid5

import structlog
from fsp_contracts import Envelope, new_event, parse_payload
from fsp_contracts import commands as cmd
from fsp_contracts import events as evt
from pydantic import BaseModel

from fsp_ml import fake, resume_parser
from fsp_ml.llm import LlmClient, LlmError
from fsp_ml.resume_parser import Progress
from fsp_ml.resume_text import ResumeFileError
from fsp_ml.taxonomy import TaxonomyProvider

log = structlog.get_logger()

PRODUCER = "ml"


def _result(command: Envelope, type: str, payload: BaseModel) -> Envelope:
    env = new_event(type, PRODUCER, payload, correlation_id=command.correlation_id)
    return env.model_copy(
        update={"message_id": uuid5(NAMESPACE_URL, f"{command.message_id}:{type}")}
    )


def resume_parse(c: Envelope, p: cmd.MlResumeParse) -> list[Envelope]:
    if p.object_key.endswith(".scanned"):  # сценарий ошибки для фронта и тестов
        r = evt.MlResumeResult(
            resume_id=p.resume_id, candidate_id=p.candidate_id, error="scanned_pdf"
        )
        return [_result(c, "ml.resume.failed", r)]
    r = evt.MlResumeResult(
        resume_id=p.resume_id, candidate_id=p.candidate_id, parsed=fake.parsed_resume()
    )
    return [_result(c, "ml.resume.completed", r)]


def code_analyze(c: Envelope, p: cmd.MlCodeAnalyze) -> list[Envelope]:
    if p.github_login.lower() == "not-found":
        r = evt.MlCodeResult(
            analysis_id=p.analysis_id, candidate_id=p.candidate_id, error="github_not_found"
        )
        return [_result(c, "ml.code.failed", r)]
    r = evt.MlCodeResult(
        analysis_id=p.analysis_id,
        candidate_id=p.candidate_id,
        result=fake.code_analysis(p.github_login),
    )
    return [_result(c, "ml.code.completed", r)]


def interview_generate(c: Envelope, p: cmd.MlInterviewGenerate) -> list[Envelope]:
    r = evt.MlInterviewGenerated(
        interview_id=p.interview_id,
        candidate_id=p.candidate_id,
        questions=fake.interview_questions(p.repo_full_name, p.questions, p.head_sha),
    )
    return [_result(c, "ml.interview.generated", r)]


def interview_grade(c: Envelope, p: cmd.MlInterviewGrade) -> list[Envelope]:
    grades, total = fake.grade_answers(p.answers)
    r = evt.MlInterviewGraded(
        interview_id=p.interview_id, candidate_id=p.candidate_id, grades=grades, total=total
    )
    return [_result(c, "ml.interview.graded", r)]


def interview_kit_generate(c: Envelope, p: cmd.MlInterviewKitGenerate) -> list[Envelope]:
    r = evt.MlInterviewKitGenerated(
        kit_id=p.kit_id,
        vacancy_id=p.vacancy_id,
        vacancy_version=p.vacancy_version,
        candidate_id=p.candidate_id,
        profile_version=p.profile_version,
        questions=fake.kit_questions(p.skills, p.gaps),
    )
    return [_result(c, "ml.interview_kit.generated", r)]


def skills_resolve(c: Envelope, p: cmd.MlSkillsResolve) -> list[Envelope]:
    items = [fake.resolve_skill(m.raw) for m in p.mentions]
    r = evt.MlSkillsResolved(
        request_id=p.request_id, taxonomy_version=p.taxonomy_version, items=items
    )
    return [_result(c, "ml.skills.resolved", r)]


def matches_explain(c: Envelope, p: cmd.MlMatchesExplain) -> list[Envelope]:
    r = evt.MlMatchesExplained(
        vacancy_id=p.vacancy_id,
        vacancy_version=p.vacancy_version,
        items=fake.rationales(p.items),
    )
    return [_result(c, "ml.matches.explained", r)]


def questions_generate(c: Envelope, p: cmd.MlQuestionsGenerate) -> list[Envelope]:
    r = evt.MlQuestionsGenerated(
        skill_slug=p.skill_slug,
        questions=fake.question_drafts(p.skill_slug, p.count, p.difficulty),
    )
    return [_result(c, "ml.questions.generated", r)]


Handler = Callable[[Envelope, BaseModel], list[Envelope]]

HANDLERS: dict[str, Callable] = {
    "ml.resume.parse": resume_parse,
    "ml.interview.grade": interview_grade,
    "ml.interview.generate": interview_generate,
    "ml.interview_kit.generate": interview_kit_generate,
    "ml.skills.resolve": skills_resolve,
    "ml.matches.explain": matches_explain,
    "ml.questions.generate": questions_generate,
    "ml.code.analyze": code_analyze,
}


def handle(command: Envelope) -> list[Envelope]:
    """Команда → события-результаты (заглушка). Тип без обработчика — ошибка."""
    fn = HANDLERS[command.type]
    return fn(command, parse_payload(command))


# --- реальные обработчики (ML_FAKE=false) ---


async def resume_parse_llm(
    c: Envelope,
    p: cmd.MlResumeParse,
    *,
    load: Callable[[str], Awaitable[bytes]],
    llm: LlmClient,
    taxonomy: TaxonomyProvider,
    model: str,
    today: date,
    progress: Progress | None = None,
) -> list[Envelope]:
    """`ml.resume.parse` через LLM (ml.md §2). Ошибки файла и LLM → `ml.resume.failed`."""

    def failed(code: str) -> list[Envelope]:
        r = evt.MlResumeResult(resume_id=p.resume_id, candidate_id=p.candidate_id, error=code)
        return [_result(c, "ml.resume.failed", r)]

    try:
        data = await load(p.object_key)
    except Exception:  # нет объекта или MinIO недоступен — повторять бессмысленно
        log.warning("resume_file_unavailable", resume_id=str(p.resume_id))
        return failed("file_unavailable")
    index = await taxonomy.get(p.taxonomy_version)
    try:
        parsed = await resume_parser.parse_resume(
            data, llm=llm, index=index, model=model, today=today, progress=progress
        )
    except ResumeFileError as e:
        return failed(e.code)
    except LlmError as e:
        log.warning("resume_llm_failed", resume_id=str(p.resume_id), code=e.code)
        return failed(e.code)
    r = evt.MlResumeResult(resume_id=p.resume_id, candidate_id=p.candidate_id, parsed=parsed)
    return [_result(c, "ml.resume.completed", r)]
