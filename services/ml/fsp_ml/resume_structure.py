"""Структура резюме без LLM (E30-4): разделы, опыт, образование, город, «о себе».

Правила по заголовкам разделов и датам, Natasha (`resume_ner`) — запасной путь для имени,
города и компании. Всё, что не распознано, остаётся пустым: лучше пропуск, чем выдумка.
"""

from __future__ import annotations

import re

from fsp_ml import resume_ner

_HEADERS = {
    "experience": r"опыт(?:\s+работы)?|места\s+работы|карьера|work\s+experience|experience"
    r"|employment",
    "education": r"образование|education",
    "skills": r"(?:ключевые\s+|технические\s+)?навыки|стек|технологии|skills|tech\s+stack",
    "about": r"о\s+себе|обо\s+мне|summary|about(?:\s+me)?|цель|профиль",
    "other": r"контакты|контактная\s+информация|курсы|сертификаты|проекты|достижения|языки"
    r"|дополнительно|рекомендации|публикации|contacts|courses|certificates|projects|languages",
}
_HEADER_RES = {k: re.compile(rf"^\s*(?:{v})\s*:?\s*$", re.I) for k, v in _HEADERS.items()}


def sections(text: str) -> dict[str, list[str]]:
    """Строки по разделам; всё до первого заголовка — `head`."""
    out: dict[str, list[str]] = {"head": []}
    cur = "head"
    for line in text.splitlines():
        for name, rx in _HEADER_RES.items():
            if rx.match(line):
                cur = name
                out.setdefault(cur, [])
                break
        else:
            out[cur].append(line.rstrip())
    return out


# --- даты ---

_MON = (
    r"(?:янв|фев|мар|апр|ма[йя]|июн|июл|авг|сен|окт|ноя|дек|jan|feb|mar|apr|may|jun|jul|aug"
    r"|sep|oct|nov|dec)[а-яёa-z]*\.?"
)
_DATE = rf"(?:\d{{1,2}}[./]\d{{4}}|\d{{4}}[-./]\d{{1,2}}|{_MON}\s*\d{{4}}|(?:19|20)\d{{2}})"
_NOW = r"(?:н\.?\s?в\.?|по\s+наст\w*(?:\s+время)?|наст\w*\s+время|сейчас|present|now|current)"
_RANGE = re.compile(rf"(?<![\w.])({_DATE})\s*(?:[—–−-]|по|to)\s*({_DATE}|{_NOW})(?![\w])", re.I)


def find_period(line: str) -> tuple[str, str, str] | None:
    """`(начало, конец, строка без периода)` или None."""
    m = _RANGE.search(line)
    if not m:
        return None
    rest = (line[: m.start()] + " " + line[m.end() :]).strip(" \t,;|—–-()")
    return m.group(1), m.group(2), re.sub(r"\s{2,}", " ", rest)


# --- опыт ---

TITLE_WORDS = re.compile(
    r"разработчик|программист|инженер|developer|engineer|аналитик|analyst|тестировщик|qa\b"
    r"|devops|администратор|архитектор|architect|руководитель|менеджер|manager|lead|лид"
    r"|стаж[её]р|intern|специалист|дизайнер|ученый|учёный|scientist|researcher",
    re.I,
)
_COMPANY_WORDS = re.compile(
    r"(?<!\w)(?:ооо|ао|зао|пао|оао|ип|llc|inc|ltd|gmbh)(?!\w)|«|\"|компания|company|group|групп",
    re.I,
)
_NON_COMMERCIAL = re.compile(
    r"волонт|pet[-\s]?проект|личн\w+\s+проект|учебн\w+\s+проект|hobby|хобби|фриланс", re.I
)
_SEP = re.compile(r"\s*(?:,|\||\s[—–-]\s|\(|/)\s*")


def _split_header(header: str) -> tuple[str | None, str | None]:
    """«Компания, Должность» в любом порядке: должность — часть со словом-должностью."""
    header = header.strip(" \t,;|—–-()")
    if not header:
        return None, None
    # запятые внутри кавычек «…» не разделяют
    parts: list[str] = []
    depth = 0
    cur = ""
    i = 0
    while i < len(header):
        ch = header[i]
        if ch in '«"':
            depth = 1 - depth if ch == '"' else depth + 1
        elif ch == "»":
            depth = max(0, depth - 1)
        if depth == 0 and (
            ch in ",|" or (ch in "—–-" and cur.endswith(" ") and header[i + 1 : i + 2] == " ")
        ):
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
        elif depth == 0 and ch == "(":
            if cur.strip():
                parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    if cur.strip(" )"):
        parts.append(cur.strip(" )"))
    parts = [p for p in parts if p][:3]
    if not parts:
        return None, None
    title = next((p for p in parts if TITLE_WORDS.search(p) and not _COMPANY_WORDS.search(p)), None)
    company = next((p for p in parts if p is not title and _COMPANY_WORDS.search(p)), None)
    rest = [p for p in parts if p is not title and p is not company]
    if company is None and rest:
        company = rest.pop(0)
    if title is None and rest:
        title = rest.pop(0)
    if company is None and title is None:
        return None, None
    return (company[:200] if company else None, title[:200] if title else None)


def _company_by_ner(header: str, skip: set[str]) -> str | None:
    for kind, value in resume_ner.entities(header):
        if kind == "ORG" and value.lower() not in skip and len(value) > 1:
            return value[:200]
    return None


def parse_experience(lines: list[str], skill_names: set[str]) -> list[dict]:
    """Записи опыта: абзац с периодом; шапка — строка с периодом или строка перед ним.

    `skill_names` — имена навыков из словаря в нижнем регистре (чтобы NER не принял «Redis»
    за организацию). Возвращает dict-и в форме `LlmExperience`, без навыков.
    """
    # абзацы по пустым строкам
    paras: list[list[str]] = [[]]
    for line in lines:
        if line.strip():
            paras[-1].append(line.strip())
        elif paras[-1]:
            paras.append([])
    paras = [p for p in paras if p]

    out: list[dict] = []
    pending: str | None = None  # шапка без периода в предыдущем абзаце
    for para in paras:
        idx = next((i for i, ln in enumerate(para) if find_period(ln)), None)
        if idx is None:
            pending = para[0] if len(para) == 1 and len(para[0]) <= 160 else None
            if out and pending is None:
                out[-1]["description"] = _join(out[-1].get("description"), " ".join(para))
            continue
        start, end, rest = find_period(para[idx])  # type: ignore[misc]
        header_lines = [ln for ln in para[:idx]] or ([rest] if rest else [])
        if not header_lines and pending:
            header_lines = [pending]
        elif header_lines and rest and para[:idx]:
            header_lines.append(rest)
        header = ", ".join(h for h in header_lines if h)
        company, title = _split_header(header)
        if company is None:
            company = _company_by_ner(header, skill_names)
        desc = " ".join(para[idx + 1 :]).strip()
        out.append(
            {
                "company": company,
                "title": title,
                "start": start,
                "end": end,
                "description": desc[:2000] or None,
                "is_commercial": not _NON_COMMERCIAL.search(header),
            }
        )
        pending = None
    return out


def _join(a: str | None, b: str) -> str:
    return f"{a} {b}".strip()[:2000] if a else b[:2000]


# --- образование ---

_INSTITUTION = re.compile(
    r"университет|институт|академия|колледж|техникум|училище|школа|лицей|университета"
    r"|university|institute|college|academy|школа\s+анализа|вшэ|мгу|мфти|итмо|спбгу|мгту|мифи",
    re.I,
)
_DEGREES = [
    (re.compile(r"бакалавр|bachelor|\bbsc\b", re.I), "бакалавр"),
    (re.compile(r"магистр|master|\bmsc\b", re.I), "магистр"),
    (re.compile(r"специалист(?!\s+по)|specialist", re.I), "специалист"),
    (re.compile(r"аспирант|кандидат\s+наук|phd", re.I), "аспирантура"),
    (re.compile(r"среднее\s+профессиональное|колледж|техникум", re.I), "СПО"),
]
_YEARS = re.compile(r"(?<!\d)((?:19[5-9]|20\d)\d)(?!\d)")


def parse_education(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        years = [int(y) for y in _YEARS.findall(line)]
        if not _INSTITUTION.search(line):
            # строка-продолжение: «Факультет …, 2019–2023» после названия вуза
            if out and out[-1]["field"] is None and not years and len(line) < 150:
                out[-1]["field"] = line[:200]
            elif out and years and out[-1]["year_end"] is None:
                out[-1]["year_end"] = max(years)
            continue
        degree = next((name for rx, name in _DEGREES if rx.search(line)), None)
        parts = [p.strip() for p in re.split(r"\s*(?:,|\||\s[—–-]\s)\s*", line) if p.strip()]
        institution = next((p for p in parts if _INSTITUTION.search(p)), None)
        field = None
        for p in parts:
            if p is institution or _YEARS.fullmatch(re.sub(r"[\s—–-]", "", p) or "x"):
                continue
            if any(rx.search(p) for rx, _ in _DEGREES) or _YEARS.search(p):
                continue
            field = p[:200]
            break
        out.append(
            {
                "institution": (institution or line)[:300],
                "degree": degree,
                "field": field,
                "year_end": max(years) if years else None,
            }
        )
    return out[:10]


# --- город и «о себе» ---

_CITY = re.compile(
    r"(?im)^\s*(?:город(?:\s+проживания)?|проживаю|city|location|локация)\s*[:\-]\s*"
    r"([А-ЯЁA-Z][\w .\-]{1,40}?)\s*(?:[,;(]|$)"
)
_CITY_G = re.compile(r"(?:^|[\s,])г\.\s*([А-ЯЁ][а-яё]+(?:-[А-ЯЁ]?[а-яё]+)*(?:\s[А-ЯЁ][а-яё]+)?)")


def parse_city(head: list[str]) -> str | None:
    block = "\n".join(head[:15])
    if m := _CITY.search(block) or _CITY_G.search(block):
        return m.group(1).strip()[:80]
    for line in head[:8]:
        for kind, value in resume_ner.entities(line):
            if kind == "LOC" and len(value.split()) <= 2 and value[:1].isupper():
                return value[:80]
    return None


def parse_summary(about: list[str]) -> str | None:
    text = " ".join(ln.strip() for ln in about if ln.strip())
    return text[:500] or None
