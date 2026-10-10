"""Разбор резюме `ml.parse_resume` (ml.md §2).

файл → текст → правила → LLM (JSON-схема) → проверка цитат → нормализация → ParsedResume.

LLM только извлекает. Навык попадает в результат, только если его цитата найдена в тексте
и сам навык упомянут в цитате (AGENTS.md п. 4); иначе отбрасывается с записью в `warnings`.
Сопоставление с графом — быстрый путь `TaxonomyIndex` (как `/v1/skills/resolve`).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import jinja2
import structlog
from fsp_contracts.enums import Grade, RoleSlug
from fsp_contracts.ml import (
    ParsedResume,
    ResumeDeclaredGrade,
    ResumeDeclaredRole,
    ResumeEducation,
    ResumeExperience,
    ResumePerson,
    ResumeSkill,
    ResumeSoftSkill,
    SkillMention,
)
from pydantic import BaseModel, Field, ValidationError
from rapidfuzz import fuzz

from fsp_ml import resume_ner, resume_rules, resume_structure
from fsp_ml.llm import LlmClient, LlmError
from fsp_ml.normalize import light, normalize
from fsp_ml.resume_text import extract_text
from fsp_ml.taxonomy import TaxonomyIndex

log = structlog.get_logger()

PROMPT_VERSION = "v2"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
MAX_TEXT_CHARS = 12_000  # ≈ 4–5 тыс. токенов: влезает в слот llama-server 8k вместе с ответом
QUOTE_THRESHOLD = 90.0  # rapidfuzz.partial_ratio цитаты к тексту (ml.md §2, шаг 4)
MENTION_THRESHOLD = 80.0  # навык должен быть упомянут в своей цитате (fuzz.ratio по словам)
CONFIDENCE = {"alias": 0.95, "fuzzy": 0.85}
DROP_WARNINGS = ("quote_not_found:", "skill_not_in_quote:")  # навык отброшен
DECLARED_DROP_WARNINGS = ("soft_dropped:", "grade_dropped:", "role_dropped:")  # E20-5
# E43-8: запасной путь — LLM вернул мало навыков, добавляем найденное правилами
FALLBACK_MIN_SKILLS = 3
FALLBACK_MIN_CHARS = 1000

Progress = Callable[[str, int, str], Awaitable[None]]


# --- схема ответа LLM (внутренняя; наружу уходит ParsedResume из контрактов) ---


class LlmSkill(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=400)


class LlmExperience(BaseModel):
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    start: str | None = Field(default=None, max_length=40)
    end: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    skills: list[str] = Field(default_factory=list, max_length=40)
    is_commercial: bool = True


class LlmEducation(BaseModel):
    institution: str | None = Field(default=None, max_length=300)
    degree: str | None = Field(default=None, max_length=100)
    field: str | None = Field(default=None, max_length=200)
    year_end: int | None = Field(default=None, ge=1950, le=2100)


class LlmGrade(BaseModel):
    grade: Grade
    quote: str = Field(min_length=1, max_length=400)


class LlmRole(BaseModel):
    role: RoleSlug
    quote: str = Field(min_length=1, max_length=400)


class LlmResume(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=80)
    summary: str | None = Field(default=None, max_length=500)
    experience: list[LlmExperience] = Field(default_factory=list, max_length=30)
    education: list[LlmEducation] = Field(default_factory=list, max_length=10)
    skills: list[LlmSkill] = Field(default_factory=list, max_length=80)
    # E20-5: заявленное; каждое поле с цитатой
    soft_skills: list[LlmSkill] = Field(default_factory=list, max_length=20)
    declared_grade: LlmGrade | None = None
    roles: list[LlmRole] = Field(default_factory=list, max_length=6)


@cache
def _template() -> jinja2.Template:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(PROMPTS_DIR), autoescape=False, keep_trailing_newline=False
    )
    return env.get_template(f"parse_resume/{PROMPT_VERSION}.j2")


def build_messages(text: str) -> list[dict[str, Any]]:
    t = _template()
    return [
        {"role": "system", "content": t.render(part="system").strip()},
        {"role": "user", "content": t.render(part="user", text=text).strip()},
    ]


def parser_version(model: str) -> str:
    return f"resume-{PROMPT_VERSION}:{model}"


def _require_all(node: object) -> None:
    """Все поля объектов схемы — обязательные: иначе строгая грамматика llama.cpp позволяет модели
    пропустить `person`, `experience`, `skills` и вернуть почти пустой ответ (E43-8)."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            node["required"] = list(props)
        for v in node.values():
            _require_all(v)
    elif isinstance(node, list):
        for v in node:
            _require_all(v)


async def extract_llm(llm: LlmClient, text: str) -> LlmResume:
    """Одна генерация по схеме; при невалидном ответе — один повтор с ошибкой (ml.md §1.3)."""
    messages = build_messages(text)
    schema = LlmResume.model_json_schema()
    _require_all(schema)
    last_error = ""
    for attempt in range(2):
        data = await llm.complete_json(messages, schema, schema_name="resume", temperature=0.1)
        try:
            return LlmResume.model_validate(data)
        except ValidationError as e:
            last_error = "; ".join(
                f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:10]
            )
            log.warning("resume_llm_invalid", attempt=attempt, errors=len(e.errors()))
            messages = [
                *messages,
                {"role": "assistant", "content": str(data)[:4000]},
                {
                    "role": "user",
                    "content": f"Ответ не прошёл проверку схемы: {last_error}. "
                    "Исправь и верни JSON.",
                },
            ]
    raise LlmError("llm_invalid", last_error)


# --- проверка цитат ---

_SPACES = re.compile(r"\s+")
_QUOTES = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "’": "'", "–": "-",
                         "—": "-"})  # fmt: skip


def norm_text(s: str) -> str:
    return _SPACES.sub(" ", light(s).translate(_QUOTES)).strip()


def quote_in_text(quote: str, text_norm: str) -> bool:
    q = norm_text(quote)
    if len(q) < 3:
        return False
    if q in text_norm:
        return True
    return fuzz.partial_ratio(q, text_norm) >= QUOTE_THRESHOLD


_TOKEN = re.compile(r"[\w+#]+(?:[./-][\w+#]+)*")


def _word_in(word: str, text: str) -> bool:
    return re.search(rf"(?<![\w+#]){re.escape(word)}(?![\w+#])", text) is not None


def mention_in_quote(raw: str, quote_norm: str, aliases: list[str]) -> bool:
    """Навык упомянут в своей цитате: по названию из ответа или по синониму из графа.

    Сравниваем целыми словами, а не подстрокой: «java» не находится в «javascript».
    Нечёткое сравнение (окна слов, `fuzz.ratio ≥ 80`) ловит падежи («питоне») и опечатки;
    для коротких названий («c», «go», «c++») — только точное слово.
    """
    tokens = _TOKEN.findall(quote_norm)
    for name in dict.fromkeys((light(raw), normalize(raw), *aliases)):
        if not name:
            continue
        if _word_in(name, quote_norm):
            return True
        if len(name) <= 3:
            continue
        n = len(_TOKEN.findall(name)) or 1
        for k in (n, n + 1):
            for i in range(len(tokens) - k + 1):
                if fuzz.ratio(name, " ".join(tokens[i : i + k])) >= MENTION_THRESHOLD:
                    return True
    return False


def _aliases_by_slug(index: TaxonomyIndex | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if index is not None:
        for key, slug in index.exact.items():
            out.setdefault(slug, []).append(key)
    return out


# --- заявленное в резюме (E20-5) ---

# маркеры в цитате: без них заявленный грейд/роль отбрасывается (модель не «додумывает»)
_GRADE_MARKERS: dict[Grade, tuple[str, ...]] = {
    Grade.intern: ("intern", "стажер", "стажир", "практикант"),
    Grade.junior: ("junior", "джуниор", "джун", "младш"),
    Grade.junior_plus: ("junior+", "junior plus", "джуниор+", "джун+"),
    Grade.middle: ("middle", "мидл", "миддл", "средн"),
    Grade.middle_plus: ("middle+", "middle plus", "мидл+", "миддл+"),
    Grade.senior: ("senior", "сеньор", "синьор", "старш", "ведущ"),
    Grade.lead: ("lead", "лид", "руководител", "тимлид", "team lead"),
}
_ROLE_MARKERS: dict[RoleSlug, tuple[str, ...]] = {
    RoleSlug.backend: ("backend", "back-end", "бэкенд", "бекенд", "серверн"),
    RoleSlug.frontend: ("frontend", "front-end", "фронтенд", "фронт"),
    RoleSlug.fullstack: ("fullstack", "full-stack", "full stack", "фулстек", "фуллстек"),
    RoleSlug.mobile: ("mobile", "мобильн", "android", "ios"),
    RoleSlug.ml: ("machine learning", "data scientist", "ml", "машинн", "нейрос"),
    RoleSlug.data_engineer: ("data engineer", "инженер данных", "etl", "dwh"),
    RoleSlug.devops: ("devops", "sre", "девопс", "эксплуатац"),
    RoleSlug.qa: ("qa", "тестировщик", "тестирован", "quality"),
    RoleSlug.security: ("security", "безопасност", "pentest", "пентест"),
    RoleSlug.gamedev: ("gamedev", "game dev", "unity", "unreal", "геймдев", "игр"),
    RoleSlug.embedded: ("embedded", "встраиваем", "микроконтроллер", "firmware", "прошивк"),
    RoleSlug.analyst: ("аналитик", "analyst"),
    RoleSlug.product: ("product", "продакт", "продуктов"),
    RoleSlug.designer: ("designer", "дизайнер", "ui/ux", "ux"),
}


def _marker_in(markers: tuple[str, ...], quote_norm: str) -> bool:
    return any(_word_in(m, quote_norm) or (len(m) >= 5 and m in quote_norm) for m in markers)


def assemble_declared(
    text_norm: str, llm_out: LlmResume, warnings: list[str]
) -> tuple[list[ResumeSoftSkill], ResumeDeclaredGrade | None, list[ResumeDeclaredRole]]:
    """Софт-навыки, заявленный грейд и роли: оставляем только с цитатой из текста (AGENTS.md п. 4).

    Цитата должна найтись в резюме, а заявленное значение читаться в самой цитате.
    Отброшенное пишем в `warnings` (`soft_dropped:` / `grade_dropped:` / `role_dropped:`).
    """
    soft: list[ResumeSoftSkill] = []
    seen: set[str] = set()
    for s in llm_out.soft_skills:
        name = s.name.strip()
        if not quote_in_text(s.quote, text_norm) or not mention_in_quote(
            name, norm_text(s.quote), []
        ):
            warnings.append(f"soft_dropped:{name}")
            continue
        key = normalize(name)
        if key not in seen:
            seen.add(key)
            soft.append(ResumeSoftSkill(name=name, quote=s.quote.strip()))

    grade: ResumeDeclaredGrade | None = None
    g = llm_out.declared_grade
    if g is not None:
        if quote_in_text(g.quote, text_norm) and _marker_in(
            _GRADE_MARKERS[g.grade], norm_text(g.quote)
        ):
            grade = ResumeDeclaredGrade(grade=g.grade, quote=g.quote.strip())
        else:
            warnings.append(f"grade_dropped:{g.grade.value}")

    roles: list[ResumeDeclaredRole] = []
    seen_roles: set[RoleSlug] = set()
    for r in llm_out.roles:
        if not quote_in_text(r.quote, text_norm) or not _marker_in(
            _ROLE_MARKERS[r.role], norm_text(r.quote)
        ):
            warnings.append(f"role_dropped:{r.role.value}")
            continue
        if r.role not in seen_roles:
            seen_roles.add(r.role)
            roles.append(ResumeDeclaredRole(role=r.role, quote=r.quote.strip()))
    return soft, grade, roles


# --- сборка результата ---


def assemble(
    text: str,
    llm_out: LlmResume,
    index: TaxonomyIndex | None,
    *,
    version: str,
    today: date,
    warnings: list[str] | None = None,
) -> ParsedResume:
    """Детерминированная часть: цитаты, нормализация, контакты, периоды, стаж."""
    warnings = list(warnings or [])
    text_norm = norm_text(text)
    aliases = _aliases_by_slug(index)
    if index is None:
        warnings.append("taxonomy_unavailable")

    skills: list[ResumeSkill] = []
    unknown: list[str] = []
    seen_slugs: set[str] = set()
    seen_unknown: set[str] = set()
    for s in llm_out.skills:
        raw = s.name.strip()
        if not quote_in_text(s.quote, text_norm):
            warnings.append(f"quote_not_found:{raw}")
            continue
        hit = index.resolve(SkillMention(raw=raw, context=s.quote)) if index else None
        slug = hit.skill_slug if hit else None
        if not mention_in_quote(raw, norm_text(s.quote), aliases.get(slug or "", [])):
            warnings.append(f"skill_not_in_quote:{raw}")
            continue
        if hit is None or slug is None:
            key = normalize(raw)
            if key not in seen_unknown:
                seen_unknown.add(key)
                unknown.append(raw)
            continue
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        skills.append(
            ResumeSkill(
                raw=raw,
                slug=slug,
                quote=s.quote.strip(),
                method=hit.decision,
                confidence=CONFIDENCE.get(hit.decision, 0.7),
            )
        )

    experience: list[ResumeExperience] = []
    for e in llm_out.experience:
        exp_slugs: list[str] = []
        for m in e.skills:
            hit = index.resolve(SkillMention(raw=m)) if index else None
            # в опыт идут только навыки с подтверждённой цитатой
            if hit and hit.skill_slug in seen_slugs and hit.skill_slug not in exp_slugs:
                exp_slugs.append(hit.skill_slug)
        start = resume_rules.parse_month(e.start)
        end = resume_rules.parse_end(e.end)
        if start and end and end < start:
            warnings.append("experience_period_invalid")
            start = end = None
        experience.append(
            ResumeExperience(
                company=e.company,
                title=e.title,
                start=start,
                end=end,
                description=e.description,
                skills=exp_slugs,
                is_commercial=e.is_commercial,
            )
        )

    c = resume_rules.contacts(text)
    full_name = llm_out.full_name
    if full_name and not quote_in_text(full_name, text_norm):
        full_name = None
    person = ResumePerson(
        full_name=full_name,
        email=c.email,
        phone=c.phone,
        telegram=c.telegram,
        city=llm_out.city,
        links=c.links,
    )
    soft_skills, declared_grade, declared_roles = assemble_declared(text_norm, llm_out, warnings)
    return ParsedResume(
        parser_version=version,
        person=person,
        summary=llm_out.summary,
        experience=experience,
        education=[ResumeEducation(**e.model_dump()) for e in llm_out.education],
        skills=skills,
        unknown_skills=unknown,
        total_experience_months=resume_rules.total_experience_months(experience, today),
        warnings=warnings,
        soft_skills=soft_skills,
        declared_grade=declared_grade,
        declared_roles=declared_roles,
    )


RULES_VERSION = "resume-rules-v2"
_NAME_WORD = re.compile(r"[А-ЯЁA-Z][а-яёa-z]+(?:-[А-ЯЁA-Z][а-яёa-z]+)?")


def _skill_mentions(text: str, index: TaxonomyIndex | None) -> list[LlmSkill]:
    skills: list[LlmSkill] = []
    seen: set[str] = set()
    if index is None:
        return skills
    for line in text.splitlines():
        line = line.strip()
        quote = line[:400]
        tokens = _TOKEN.findall(line)
        for n in (3, 2, 1):
            for i in range(len(tokens) - n + 1):
                raw = " ".join(tokens[i : i + n])
                slug = index.lookup(raw)
                if slug and slug not in seen and raw.lower() in quote.lower():
                    seen.add(slug)
                    skills.append(LlmSkill(name=raw[:80], quote=quote))
    return skills[:80]


def _full_name(head: list[str]) -> str | None:
    for line in head[:5]:
        words = line.split()
        if (
            2 <= len(words) <= 3
            and all(_NAME_WORD.fullmatch(w) for w in words)
            and not resume_structure.TITLE_WORDS.search(line)
        ):
            return line.strip()
    for line in head[:5]:  # запасной путь: Natasha, по строке («Фамилия Имя Отчество, 29 лет»)
        for kind, value in resume_ner.entities(line):
            words = value.split()
            if (
                kind == "PER"
                and 2 <= len(words) <= 3
                and all(_NAME_WORD.fullmatch(w) for w in words)
            ):
                return value
    return None


def extract_rules(text: str, index: TaxonomyIndex | None) -> LlmResume:
    """Разбор без LLM (LLM_ENABLED=false, E20-8 + E30-4): правила, словарь графа, Natasha.

    Навыки: каждое слово и пара-тройка слов строки ищутся в словаре синонимов, цитата — строка
    резюме; `assemble` проверяет цитату так же, как для LLM. Опыт, образование, даты, город и
    «о себе» — `resume_structure` (заголовки разделов + периоды); Natasha — запасной путь для
    имени, города и компании. Нераспознанное остаётся пустым.
    """
    skills = _skill_mentions(text, index)
    sec = resume_structure.sections(text)
    names = {s.name.lower() for s in skills}
    exp_lines = sec.get("experience") or [
        ln for k, v in sec.items() if k not in ("education", "skills", "about", "other") for ln in v
    ]
    experience = []
    for e in resume_structure.parse_experience(exp_lines, names):
        blob = f"{e.get('title') or ''}\n{e.get('description') or ''}"
        e["skills"] = [s.name for s in _skill_mentions(blob, index)][:40]
        experience.append(LlmExperience(**e))
    education = [
        LlmEducation(**e) for e in resume_structure.parse_education(sec.get("education", []))
    ]
    return LlmResume(
        full_name=_full_name(sec["head"]),
        city=resume_structure.parse_city(sec["head"]),
        summary=resume_structure.parse_summary(sec.get("about", [])),
        experience=experience[:30],
        education=education,
        skills=skills,
    )


async def _noop(stage: str, pct: int, message: str) -> None:
    return None


def needs_rules_fallback(skills_found: int, text_len: int) -> bool:
    """LLM вернул 0 навыков (при любом тексте) или меньше порога при длинном тексте (E43-8)."""
    if skills_found == 0:
        return text_len > 0
    return skills_found < FALLBACK_MIN_SKILLS and text_len > FALLBACK_MIN_CHARS


def merge_rules_fallback(
    parsed: ParsedResume, text: str, index: TaxonomyIndex | None, today: date
) -> tuple[ParsedResume, int]:
    """Дополнить навыки результата LLM правиловыми (`source: rules`). Цитата обязательна.

    Правиловые навыки проходят ту же `assemble` (цитата найдена в тексте, навык упомянут в ней).
    Навыки LLM не меняются; опыт, образование и контакты остаются от LLM. Возвращает
    (результат, число добавленных навыков).
    """
    if index is None:
        return parsed, 0
    rules = assemble(text, extract_rules(text, index), index, version=RULES_VERSION, today=today)
    have = {s.slug for s in parsed.skills}
    added = [
        s.model_copy(update={"source": "rules"})
        for s in rules.skills
        if s.slug not in have and s.quote.strip()
    ]
    if not added:
        return parsed, 0
    known_unknown = {normalize(u) for u in parsed.unknown_skills}
    unknown = [*parsed.unknown_skills]
    for u in rules.unknown_skills:
        if normalize(u) not in known_unknown:
            unknown.append(u)
    return (
        parsed.model_copy(
            update={
                "skills": [*parsed.skills, *added],
                "unknown_skills": unknown,
                "warnings": [*parsed.warnings, f"llm_fallback_rules:{len(added)}"],
            }
        ),
        len(added),
    )


async def parse_resume(
    data: bytes,
    *,
    llm: LlmClient | None,
    index: TaxonomyIndex | None,
    model: str,
    today: date,
    progress: Progress | None = None,
) -> ParsedResume:
    """Полный конвейер. `llm=None` — правиловая ветка. Ошибки: `ResumeFileError`, `LlmError`."""
    report = progress or _noop
    t0 = time.monotonic()
    await report("text", 10, "Извлекаем текст")
    text = await asyncio.to_thread(extract_text, data)  # PyMuPDF блокирует цикл
    warnings: list[str] = []
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        warnings.append("text_truncated")
    await report("llm", 30, "Разбираем опыт и навыки")
    llm_skills = 0
    if llm is None:
        llm_out = extract_rules(text, index)
        version = RULES_VERSION
        warnings.append("rules_mode")
    else:
        llm_out = await extract_llm(llm, text)
        llm_skills = len(llm_out.skills)
        version = parser_version(model)
    await report("verify", 85, "Проверяем навыки по тексту")
    parsed = assemble(text, llm_out, index, version=version, today=today, warnings=warnings)
    fallback_added = 0
    if llm is not None and needs_rules_fallback(len(parsed.skills), len(text)):
        parsed, fallback_added = merge_rules_fallback(parsed, text, index, today)
    dropped = sum(w.startswith(DROP_WARNINGS) for w in parsed.warnings)
    # без ПДн: только размеры, счётчики и версии
    log.info(
        "resume_parsed",
        prompt_version=PROMPT_VERSION if llm is not None else None,
        parser_version=parsed.parser_version,
        chars=len(text),
        llm_skills=llm_skills,
        skills=len(parsed.skills),
        unknown=len(parsed.unknown_skills),
        experience=len(parsed.experience),
        education=len(parsed.education),
        dropped=dropped,
        dropped_share=round(dropped / llm_skills, 3) if llm_skills else None,
        fallback_rules=fallback_added,
        declared_dropped=sum(w.startswith(DECLARED_DROP_WARNINGS) for w in parsed.warnings),
        seconds=round(time.monotonic() - t0, 2),
    )
    if llm is not None and llm_skills == 0:
        log.warning("resume_llm_empty_skills", chars=len(text), prompt_version=PROMPT_VERSION)
    await report("done", 100, "Готово")
    return parsed


async def _cli(data: bytes, skills: list[dict] | None) -> None:
    """Ручная проверка на реальной модели: LLM_BASE_URL / LLM_API_KEY / LLM_MODEL из окружения."""
    import json
    import sys

    from fsp_ml.config import Settings
    from fsp_ml.llm import OpenAiLlm

    s = Settings()
    if not s.llm_base_url:
        sys.exit("LLM_BASE_URL не задан")
    index = TaxonomyIndex.from_snapshot({"version": 0, "skills": skills}) if skills else None
    llm = OpenAiLlm(
        s.llm_base_url,
        s.llm_api_key,
        s.llm_model,
        timeout=s.llm_timeout,
        max_tokens=s.llm_max_tokens,
    )

    async def progress(stage: str, pct: int, message: str) -> None:
        print(f"[{pct:3d}%] {message}", file=sys.stderr)

    t0 = time.monotonic()
    parsed = await parse_resume(
        data,
        llm=llm,
        index=index,
        model=s.llm_model,
        today=date.today(),
        progress=progress,
    )
    print(json.dumps(parsed.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print(f"{time.monotonic() - t0:.1f} с", file=sys.stderr)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        sys.exit("python -m fsp_ml.resume_parser <resume.pdf|docx> [data/taxonomy/skills.yaml]")
    skills = None
    if len(sys.argv) > 2:
        import yaml  # только для ручного запуска

        skills = yaml.safe_load(Path(sys.argv[2]).read_text())["skills"]
    asyncio.run(_cli(Path(sys.argv[1]).read_bytes(), skills))
