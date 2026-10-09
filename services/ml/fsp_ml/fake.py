"""Заглушки ML (`ML_FAKE=true`): детерминированные ответы по контрактам, без GPU и сети.

Тексты и данные вымышленные. Результат зависит только от входа, поэтому повторная
обработка той же команды даёт тот же ответ (идемпотентность для inbox получателя).
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from functools import cache
from pathlib import Path

from fsp_contracts.enums import Grade, RoleSlug, TrustLevel, WorkFormat
from fsp_contracts.ml import (
    CodeAnalysisResult,
    EmbeddingsRequest,
    EmbeddingsResponse,
    FilterChip,
    InterviewGrade,
    InterviewQuestion,
    KitQuestion,
    MatchRationale,
    ParsedQuery,
    ParsedResume,
    QueryParseRequest,
    QuestionDraft,
    QuestionOption,
    SearchFilters,
    SkillRelationGuess,
    SkillRequirement,
    SkillResolveItem,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FAKE_MODEL = "fake-bge-m3"


@cache
def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def parsed_resume() -> ParsedResume:
    return ParsedResume.model_validate_json(_load("parsed_resume.json"))


def code_analysis(github_login: str) -> CodeAnalysisResult:
    """Фикстура с подстановкой логина в имена репозиториев."""
    text = _load("code_analysis.json").replace("demo-candidate", github_login)
    return CodeAnalysisResult.model_validate_json(text)


def _rng(*parts: object) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# --- embeddings ---


def embeddings(req: EmbeddingsRequest, dim: int = 1024) -> EmbeddingsResponse:
    vectors = []
    for text in req.texts:
        rng = _rng(req.kind, text)
        raw = [rng.gauss(0, 1) for _ in range(dim)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        vectors.append([round(x / norm, 6) for x in raw])
    return EmbeddingsResponse(model=FAKE_MODEL, dim=dim, vectors=vectors)


# --- skills.resolve ---

_ALIASES = {
    "python": "python",
    "питон": "python",
    "py": "python",
    "fastapi": "fastapi",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "docker": "docker",
    "докер": "docker",
    "git": "git",
    "react": "react",
    "typescript": "typescript",
    "java": "java",
    "javascript": "javascript",
    "c#": "csharp",
    "c++": "cpp",
    "pytest": "pytest",
}
_FUZZY = {"pythn": "python", "postgre": "postgresql", "typescipt": "typescript"}
_SOFT = {"коммуникация", "лидерство", "teamwork", "работа в команде", "ответственность"}
_NOT_SKILL = {"опыт", "работа", "ответственный", "и", "др", "etc"}
_BANNED = {"хрень"}


def _norm(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().lower())


def resolve_skill(raw: str) -> SkillResolveItem:
    norm = _norm(raw)
    if norm in _BANNED:
        return SkillResolveItem(
            raw=raw, norm=norm, decision="rejected", kind="not_skill", reason="moderation"
        )
    if norm in _NOT_SKILL or len(norm) < 2:
        return SkillResolveItem(
            raw=raw, norm=norm, decision="rejected", kind="not_skill", reason="not_a_skill"
        )
    if norm in _SOFT:
        return SkillResolveItem(
            raw=raw,
            norm=norm,
            decision="new",
            skill_slug=re.sub(r"[^a-zа-я0-9]+", "-", norm).strip("-"),
            kind="soft",
        )
    if norm in _ALIASES:
        return SkillResolveItem(
            raw=raw, norm=norm, decision="alias", skill_slug=_ALIASES[norm], kind="hard"
        )
    if norm in _FUZZY:
        return SkillResolveItem(
            raw=raw, norm=norm, decision="fuzzy", skill_slug=_FUZZY[norm], kind="hard"
        )
    slug = (
        re.sub(r"[^a-z0-9]+", "-", norm).strip("-")
        or "skill-" + hashlib.sha1(norm.encode()).hexdigest()[:8]
    )
    return SkillResolveItem(
        raw=raw,
        norm=norm,
        decision="new",
        skill_slug=slug,
        kind="hard",
        relation=SkillRelationGuess(type="related", to_slug="python", confidence=0.4),
    )


# --- query.parse ---

_ROLE_WORDS = {
    "бэкенд": RoleSlug.backend,
    "backend": RoleSlug.backend,
    "бекенд": RoleSlug.backend,
    "фронтенд": RoleSlug.frontend,
    "frontend": RoleSlug.frontend,
    "девопс": RoleSlug.devops,
    "devops": RoleSlug.devops,
    "qa": RoleSlug.qa,
    "тестировщик": RoleSlug.qa,
    "ml": RoleSlug.ml,
}
_GRADE_WORDS = {
    "junior": Grade.junior,
    "джун": Grade.junior,
    "middle": Grade.middle,
    "мидл": Grade.middle,
    "senior": Grade.senior,
    "сеньор": Grade.senior,
    "lead": Grade.lead,
    "лид": Grade.lead,
}
_FORMAT_WORDS = {
    "удалённо": WorkFormat.remote,
    "удаленно": WorkFormat.remote,
    "remote": WorkFormat.remote,
    "офис": WorkFormat.office,
    "гибрид": WorkFormat.hybrid,
}


def parse_query(req: QueryParseRequest) -> ParsedQuery:
    text = req.text.lower()
    words = re.findall(r"[\w#+.]+", text)
    filters = req.rule_hint.model_copy(deep=True) if req.rule_hint else SearchFilters()
    chips: list[FilterChip] = []

    def chip(key: str, value: object, label: str, conf: float = 0.8) -> None:
        chips.append(FilterChip(key=key, value=value, label=label, source="llm", confidence=conf))

    roles = [r for w, r in _ROLE_WORDS.items() if w in words]
    if roles and not filters.roles:
        filters.roles = list(dict.fromkeys(roles))
        chip(
            "roles",
            [r.value for r in filters.roles],
            "Роль: " + ", ".join(r.value for r in filters.roles),
        )
    for w, g in _GRADE_WORDS.items():
        if w in words and filters.grade_min is None:
            filters.grade_min = filters.grade_max = g
            chip("grade_min", g.value, f"Грейд: {g.value}")
            break
    for w, f in _FORMAT_WORDS.items():
        if w in words and not filters.formats:
            filters.formats = [f]
            chip("formats", [f.value], f"Формат: {f.value}")
            break
    if filters.skills_must is None:
        skills = []
        for w in words:
            slug = _ALIASES.get(w)
            if slug and slug not in skills:
                skills.append(slug)
        if skills:
            filters.skills_must = [
                SkillRequirement(slug=s, min_level=TrustLevel.l2) for s in skills
            ]
            chip("skills_must", skills, "Навыки: " + ", ".join(skills))
    m = re.search(r"до\s*(\d[\d\s]*)\s*(тыс|к|k|т\.?р)?", text)
    if m and filters.salary_max is None:
        value = int(re.sub(r"\s", "", m.group(1)))
        if m.group(2) or value < 1000:
            value *= 1000
        filters.salary_max = value
        chip("salary_max", value, f"До {value} ₽/мес")
    if filters.semantic_text is None:
        filters.semantic_text = req.text.strip() or None
    return ParsedQuery(
        filters=filters, chips=chips, unparsed=[], refining=req.rule_hint is not None
    )


# --- ИИ-интервью, вопросы, обоснования ---


def interview_questions(
    repo_full_name: str, count: int, head_sha: str | None
) -> list[InterviewQuestion]:
    out = []
    for i in range(count):
        rng = _rng(repo_full_name, head_sha, i)
        start = rng.randrange(10, 200)
        out.append(
            InterviewQuestion(
                id=f"q{i + 1}",
                file=f"src/module_{i + 1}.py",
                lines=f"{start}-{start + 24}",
                snippet=f"def handler_{i + 1}(request):\n    return process(request)\n",
                question=(
                    f"Зачем в {repo_full_name} нужна функция handler_{i + 1} "
                    "и что будет при ошибке process?"
                ),
                rubric=[
                    "Называет назначение функции",
                    "Описывает поведение при исключении",
                    "Предлагает способ тестирования",
                ],
                difficulty=1 + i % 5,
            )
        )
    return out


def grade_answers(answers: list) -> tuple[list[InterviewGrade], float]:
    grades = []
    for a in answers:
        words = len(a.answer.split())
        score = 0 if words < 5 else 1 if words < 20 else 2 if words < 50 else 3
        matched = list(range(min(score, len(a.rubric))))
        grades.append(
            InterviewGrade(
                question_id=a.question_id,
                score=score,
                matched_rubric=matched,
                rationale=f"Заглушка: оценка по длине ответа ({words} слов).",
            )
        )
    total = round(sum(g.score for g in grades) / (3 * len(grades)), 3) if grades else 0.0
    return grades, total


def kit_questions(skills: list, gaps: list) -> list[KitQuestion]:
    out = []
    for s in skills[:3]:
        out.append(_kit_q(s.slug, "strength"))
    for g in gaps[:2]:
        out.append(_kit_q(g.slug, "gap"))
    if not out:
        out.append(_kit_q("general", "strength"))
    return out


def _kit_q(slug: str, purpose: str) -> KitQuestion:
    return KitQuestion(
        skill=slug,
        purpose=purpose,  # type: ignore[arg-type]
        question=f"Расскажите о случае, когда вам пришлось применять {slug} в реальном проекте.",
        rubric={
            "weak": "Общие слова без примеров",
            "good": "Конкретный проект и своя роль",
            "strong": "Компромиссы, метрики, выводы",
        },
        follow_ups=["Что бы вы сделали иначе?"],
    )


def rationales(items: list) -> list[MatchRationale]:
    out = []
    for it in items:
        plus = [e.text for e in it.explanation if e.kind == "plus"][:2]
        minus = [e.text for e in it.explanation if e.kind != "plus"][:1]
        text = "Заглушка: " + ("; ".join(plus) if plus else "совпадение по профилю")
        if minus:
            text += ". Учтите: " + "; ".join(minus)
        out.append(
            MatchRationale(
                candidate_id=it.candidate_id, profile_version=it.profile_version, rationale=text
            )
        )
    return out


def question_drafts(skill_slug: str, count: int, difficulty: int | None) -> list[QuestionDraft]:
    out = []
    for i in range(count):
        d = difficulty or 1 + i % 5
        out.append(
            QuestionDraft(
                text=f"Вопрос {i + 1} по навыку {skill_slug}: какой вариант верный?",
                code=None,
                options=[
                    QuestionOption(id="a", text="Вариант A"),
                    QuestionOption(id="b", text="Вариант B"),
                    QuestionOption(id="c", text="Вариант C"),
                ],
                correct_option="abc"[_rng(skill_slug, i).randrange(3)],
                difficulty=d,
                explanation="Заглушка: черновик, требует проверки администратором.",
            )
        )
    return out
