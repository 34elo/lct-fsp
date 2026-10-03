"""Правиловый парсер текстового запроса работодателя (ml.md §7, п. 1; flows.md F6).

«найди middle python с FastAPI, удалённо, до 250к» → `ParsedQuery` с `source=rule`.
Детерминированно, без сети и LLM: справочник синонимов навыков приходит из `taxonomy`
(`AliasIndex`), роли, грейды, форматы, города и деньги — таблицы ниже. Непонятые слова
уходят в `semantic_text`, понятые, но не выразимые фильтром («от 150 000») — в `unparsed`.
LLM-разбор и слияние — E7-6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from fsp_contracts.enums import EmploymentType, Grade, RoleSlug, WorkFormat
from fsp_contracts.ml import FilterChip, ParsedQuery, SearchFilters, SkillRequirement

MAX_TEXT = 500
_SALARY_MIN, _SALARY_MAX = 1_000, 10_000_000

# --- Таблицы -----------------------------------------------------------------------------------
# Паттерн — кортеж слов; слово с `*` на конце — префикс (падежи), иначе точное совпадение.

_ROLES: dict[RoleSlug, list[tuple[str, ...]]] = {
    RoleSlug.backend: [
        ("бэкенд*",),
        ("бекенд*",),
        ("бэкэнд*",),
        ("backend",),
        ("back-end",),
        ("бэк",),
        ("бэкендер*",),
        ("бекендер*",),
    ],
    RoleSlug.frontend: [
        ("фронтенд*",),
        ("фронтэнд*",),
        ("frontend",),
        ("front-end",),
        ("фронт",),
        ("фронтендер*",),
    ],
    RoleSlug.fullstack: [
        ("фулстек*",),
        ("фуллстек*",),
        ("фуллстэк*",),
        ("fullstack",),
        ("full-stack",),
        ("full", "stack"),
        ("фулл", "стек*"),
    ],
    RoleSlug.mobile: [("мобильн*",), ("mobile",), ("мобильщик*",)],
    RoleSlug.ml: [
        ("ml",),
        ("data", "scientist*"),
        ("дата", "сайентист*"),
        ("датасайентист*",),
        ("ml-инженер*",),
    ],
    RoleSlug.data_engineer: [
        ("data", "engineer*"),
        ("data-engineer*",),
        ("дата-инженер*",),
        ("дата", "инженер*"),
    ],
    RoleSlug.devops: [("devops",), ("девопс*",), ("sre",), ("devops-инженер*",)],
    RoleSlug.qa: [("qa",), ("qaa",), ("тестировщик*",), ("автотестер*",), ("sdet",)],
    RoleSlug.security: [
        ("пентестер*",),
        ("иб",),
        ("infosec",),
        ("кибербезопасност*",),
        ("информационн*", "безопасност*"),
    ],
    RoleSlug.gamedev: [("gamedev",), ("геймдев*",), ("game", "dev*")],
    RoleSlug.embedded: [("embedded",), ("эмбеддед*",), ("встраиваем*",)],
    RoleSlug.analyst: [("аналитик*",), ("analyst",), ("data", "analyst"), ("дата", "аналитик*")],
    RoleSlug.product: [("продакт*",), ("product",), ("продуктов*", "менеджер*")],
    RoleSlug.designer: [("дизайнер*",), ("designer",)],
}
ROLE_LABELS = {
    "backend": "Backend", "frontend": "Frontend", "fullstack": "Fullstack", "mobile": "Mobile",
    "ml": "ML", "data_engineer": "Data Engineer", "devops": "DevOps", "qa": "QA",
    "security": "ИБ", "gamedev": "Gamedev", "embedded": "Embedded", "analyst": "Аналитик",
    "product": "Product", "designer": "Дизайнер",
}  # fmt: skip

# Грейд -> (мин, макс). «senior+» — senior…lead.
_GRADES: dict[tuple[Grade, Grade], list[tuple[str, ...]]] = {
    (Grade.intern, Grade.intern): [("интерн*",), ("intern",)],
    (Grade.junior, Grade.junior): [
        ("джун",),
        ("джуна",),
        ("джуну",),
        ("джуны",),
        ("джуни*",),
        ("junior",),
        ("jun",),
        ("junior-",),
    ],
    (Grade.junior_plus, Grade.junior_plus): [("джун+",), ("junior+",), ("джуниор+",)],
    (Grade.middle, Grade.middle): [
        ("мидл*",),
        ("миддл*",),
        ("middle",),
        ("мид",),
        ("midl",),
        ("мидла",),
    ],
    (Grade.middle_plus, Grade.middle_plus): [("мидл+",), ("миддл+",), ("middle+",), ("мид+",)],
    (Grade.senior, Grade.senior): [
        ("сеньор*",),
        ("сеньер*",),
        ("синьор*",),
        ("senior",),
        ("сениор*",),
    ],
    (Grade.senior, Grade.lead): [("senior+",), ("сеньор+",), ("синьор+",)],
    (Grade.lead, Grade.lead): [
        ("лид",),
        ("lead",),
        ("тимлид*",),
        ("teamlead",),
        ("техлид*",),
        ("team", "lead"),
        ("tech", "lead"),
        ("тим", "лид*"),
        ("тех", "лид*"),
    ],
}
GRADE_LABELS = {
    "intern": "Intern", "junior": "Junior", "junior_plus": "Junior+", "middle": "Middle",
    "middle_plus": "Middle+", "senior": "Senior", "lead": "Lead",
}  # fmt: skip

_FORMATS: dict[WorkFormat, list[tuple[str, ...]]] = {
    WorkFormat.remote: [("удален*",), ("дистанц*",), ("remote",), ("ремоут*",), ("ремотно",)],
    WorkFormat.hybrid: [("гибрид*",), ("hybrid",)],
    WorkFormat.office: [("офис*",), ("office",), ("офлайн",)],
}
FORMAT_LABELS = {"remote": "удалённо", "hybrid": "гибрид", "office": "офис"}

_EMPLOYMENT: dict[EmploymentType, list[tuple[str, ...]]] = {
    EmploymentType.full: [("full-time",), ("fulltime",), ("фулл", "тайм"), ("полн*", "занятост*")],
    EmploymentType.part: [
        ("part-time",),
        ("parttime",),
        ("парт", "тайм"),
        ("подработк*",),
        ("частичн*", "занятост*"),
    ],
    EmploymentType.internship: [("стажир*",), ("стажер*",), ("стажёр*",), ("internship",)],
    EmploymentType.project: [("фриланс*",), ("проектн*",), ("freelance",)],
}
EMPLOYMENT_LABELS = {
    "full": "полная занятость", "part": "частичная занятость",
    "internship": "стажировка", "project": "проектная работа",
}  # fmt: skip

_CITIES: dict[str, list[tuple[str, ...]]] = {
    "Москва": [("москв*",), ("мск",)],
    "Санкт-Петербург": [
        ("спб",),
        ("питер*",),
        ("санкт-петербург*",),
        ("петербург*",),
        ("санкт", "петербург*"),
    ],
    "Казань": [("казан*",)],
    "Новосибирск": [("новосибирск*",)],
    "Екатеринбург": [("екатеринбург*",), ("екб",)],
    "Нижний Новгород": [("нижн*", "новгород*")],
    "Краснодар": [("краснодар*",)],
    "Самара": [("самар*",)],
    "Ростов-на-Дону": [("ростов*",)],
    "Уфа": [("уфа",), ("уфе",), ("уфу",)],
    "Воронеж": [("воронеж*",)],
    "Пермь": [("пермь",), ("перми",)],
    "Красноярск": [("красноярск*",)],
    "Омск": [("омск*",)],
    "Челябинск": [("челябинск*",)],
    "Томск": [("томск*",)],
    "Тюмень": [("тюмен*",)],
    "Иркутск": [("иркутск*",)],
    "Калининград": [("калининград*",)],
    "Владивосток": [("владивосток*",)],
    "Волгоград": [("волгоград*",)],
    "Саратов": [("саратов*",)],
    "Иннополис": [("иннополис*",)],
}

_FLAGS: dict[str, list[tuple[str, ...]]] = {
    "relocation_ok": [("релокац*",), ("релокейт*",), ("релоцир*",), ("переезд*",)],
    "active_only": [("активн*", "ищ*")],
    "fsp_only": [("фсп",), ("fsp",)],
}
FLAG_LABELS = {
    "relocation_ok": "Готов к релокации", "active_only": "Активно ищет", "fsp_only": "Из ФСП",
}  # fmt: skip

# Маркеры «необязательно»: до навыка (желательно X) и после (X будет плюсом).
_NICE_BEFORE = [("желательн*",), ("приветствует*",), ("опционально",), ("nice",), ("nice-to-have",)]
_NICE_AFTER = [("плюсом",), ("плюс",), ("бонусом",)]

_STOP_EXACT = frozenset(
    "с со и а на в во по для из от до к о об без или как не у за это то чтобы также еще ещё "
    "лет год года опыт опыта опытом нужен нужна нужны нужно требуется мне нам нас мы ищу ищем "
    "надо хочу хотим готов готова готовы будет быть бы ли же ну найди найти покажи показать "
    "дай давай нужен человек людей кто который которые чтобы важно умеет умеют знает знание "
    "знанием знаниями плюс из и/или либо чуть более менее около примерно не-менее макс максимум "
    "бюджет зп зарплата оклад вилка руб рублей р тыс к".split()
)
_STOP_PREFIX = (
    "найд", "ищ", "разработчик", "программист", "инженер", "специалист", "кандидат",
    "сотрудник", "эксперт", "developer", "engineer", "опыт", "подбер", "подобр",
)  # fmt: skip

_TOKEN = re.compile(r"[a-zа-я0-9][a-zа-я0-9#+./\\_-]*")
_NUM = r"(\d{1,3}(?:[  ]\d{3})+|\d+(?:[.,]\d+)?)"
_UNIT = r"(к|k|тыс(?:яч\w*)?\.?|т\.?\s?р\.?|тр|млн|₽|руб\w*|р\.?)?(?![a-zа-я0-9])"
_RANGE = re.compile(rf"(?:от\s+)?{_NUM}\s*{_UNIT}\s*(?:-|–|—|до)\s*{_NUM}\s*{_UNIT}")
_UP_TO = re.compile(rf"до\s+{_NUM}\s*{_UNIT}")
_FROM = re.compile(rf"от\s+{_NUM}\s*{_UNIT}")
_BARE = re.compile(
    rf"(?<![a-zа-я0-9#+.])(?:{_NUM}\s*(к|k|тыс(?:яч\w*)?\.?|т\.?\s?р\.?|тр|млн|₽|руб\w*))(?![a-zа-я0-9])"
)


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _money(num: str, unit: str | None) -> int | None:
    value = float(re.sub(r"[  ]", "", num).replace(",", "."))
    u = (unit or "").strip(".")
    if u in ("к", "k") or u.startswith("тыс") or re.fullmatch(r"т\.?\s?р", u) or u == "тр":
        value *= 1000
    elif u == "млн":
        value *= 1_000_000
    v = round(value)
    return v if _SALARY_MIN <= v <= _SALARY_MAX else None


def _extract_money(text: str) -> tuple[str, int | None, list[str]]:
    """Вырезает деньги: возвращает (текст без них, salary_max, неразобранные «от N»)."""
    salary: int | None = None
    unparsed: list[str] = []

    def put(span: re.Match[str], value: int | None, *, ceiling: bool = True) -> str:
        nonlocal salary
        if value is None:
            return span.group(0)
        if ceiling:
            salary = value if salary is None else max(salary, value)
        else:
            unparsed.append(span.group(0).strip())
        return " "

    def range_(m: re.Match[str]) -> str:
        n1, u1, n2, u2 = m.groups()
        hi = _money(n2, u2 or u1)
        lo = _money(n1, u1 or u2)
        if hi is None or lo is None or lo > hi:
            return m.group(0)
        return put(m, hi)

    text = _RANGE.sub(range_, text)
    text = _UP_TO.sub(lambda m: put(m, _money(*m.groups())), text)
    text = _FROM.sub(lambda m: put(m, _money(*m.groups()), ceiling=False), text)
    text = _BARE.sub(lambda m: put(m, _money(*m.groups())), text)
    return text, salary, unparsed


@dataclass
class _Tok:
    text: str
    raw: str
    clause: int
    used: bool = False


def _tokenize(text: str, raw_text: str) -> list[_Tok]:
    toks: list[_Tok] = []
    clause, last = 0, 0
    for m in _TOKEN.finditer(text):
        if re.search(r"[,;\n]|[.!?](\s|$)", text[last : m.start()]):
            clause += 1
        last = m.end()
        word = m.group(0).rstrip("./\\_-")
        toks.append(_Tok(word, raw_text[m.start() : m.start() + len(word)], clause))
    return toks


def _match(pattern: tuple[str, ...], words: list[str]) -> bool:
    return len(pattern) == len(words) and all(
        w.startswith(p[:-1]) if p.endswith("*") else w == p
        for p, w in zip(pattern, words, strict=True)
    )


def _build_phrase_index() -> list[tuple[tuple[str, ...], str, Any]]:
    out: list[tuple[tuple[str, ...], str, Any]] = []
    for role, pats in _ROLES.items():
        out += [(p, "role", role) for p in pats]
    for rng, pats in _GRADES.items():
        out += [(p, "grade", rng) for p in pats]
    for fmt, pats in _FORMATS.items():
        out += [(p, "format", fmt) for p in pats]
    for emp, pats in _EMPLOYMENT.items():
        out += [(p, "employment", emp) for p in pats]
    for city, pats in _CITIES.items():
        out += [(p, "city", city) for p in pats]
    for flag, pats in _FLAGS.items():
        out += [(p, "flag", flag) for p in pats]
    out += [(p, "nice_before", None) for p in _NICE_BEFORE]
    out += [(p, "nice_after", None) for p in _NICE_AFTER]
    return out


_PHRASES = _build_phrase_index()
_MAX_N = 4


def _is_stop(word: str) -> bool:
    return word in _STOP_EXACT or word.startswith(_STOP_PREFIX) or not re.search(r"[a-zа-я]", word)


@dataclass
class _Found:
    roles: list[str] = field(default_factory=list)
    grades: list[tuple[Grade, Grade]] = field(default_factory=list)
    must: list[str] = field(default_factory=list)
    nice: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    employment: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def _add(lst: list, value: Any) -> None:
    if value not in lst:
        lst.append(value)


def parse_query(
    text: str, forms: dict[str, str], names: dict[str, str] | None = None
) -> ParsedQuery:
    """`forms` — нормализованная форма навыка → slug (`taxonomy.service.alias_index`)."""
    names = names or {}
    raw = text[:MAX_TEXT]
    norm = _norm(raw)
    body, salary_max, unparsed = _extract_money(norm)
    # нормализованная форма навыка с дефисом ищем и через пробел: «spring boot» ~ «spring-boot»
    skill_forms = {**{f.replace("-", " "): s for f, s in forms.items()}, **forms}
    role_slugs = {r.value for r in RoleSlug}

    toks = _tokenize(body, body)
    found = _Found()
    leftover: list[str] = []
    nice_mode: dict[int, bool] = {}  # clause -> «желательно» уже встретилось
    skill_hits: list[tuple[str, int]] = []  # slug, clause

    i = 0
    while i < len(toks):
        matched = False
        for n in range(min(_MAX_N, len(toks) - i), 0, -1):
            words = [t.text for t in toks[i : i + n]]
            if len({t.clause for t in toks[i : i + n]}) > 1:
                continue
            hit = next(((k, v) for p, k, v in _PHRASES if _match(p, words)), None)
            slug = None
            if hit is None:
                form = " ".join(words)
                slug = skill_forms.get(form)
                if slug is not None and n == 1:
                    # «го», «си», односимвольные — слишком двусмысленны в живом тексте
                    if len(form) == 1 or (len(form) <= 2 and re.fullmatch(r"[а-я]+", form)):
                        slug = None
            if hit is None and slug is None:
                continue
            clause = toks[i].clause
            if hit is not None:
                kind, value = hit
                if kind == "role":
                    _add(found.roles, value.value)
                elif kind == "grade":
                    _add(found.grades, value)
                elif kind == "format":
                    _add(found.formats, value.value)
                elif kind == "employment":
                    _add(found.employment, value.value)
                    if value is EmploymentType.internship:  # «стажёр» — ещё и грейд
                        _add(found.grades, (Grade.intern, Grade.intern))
                elif kind == "city":
                    _add(found.cities, value)
                elif kind == "flag":
                    _add(found.flags, value)
                elif kind == "nice_before":
                    nice_mode[clause] = True
                elif kind == "nice_after":
                    for s, c in skill_hits:
                        if c == clause and s in found.must:
                            found.must.remove(s)
                            _add(found.nice, s)
            else:
                assert slug is not None
                if slug in role_slugs:
                    _add(found.roles, slug)
                elif nice_mode.get(clause):
                    _add(found.nice, slug)
                    skill_hits.append((slug, clause))
                else:
                    _add(found.must, slug)
                    skill_hits.append((slug, clause))
            i += n
            matched = True
            break
        if matched:
            continue
        tok = toks[i]
        if len(tok.text) > 1 and re.search(r"[-/]", tok.text):
            parts = [p for p in re.split(r"[-/]", tok.text) if p]
            if len(parts) > 1:
                toks[i : i + 1] = [_Tok(p, p, tok.clause) for p in parts]
                continue
        if not _is_stop(tok.text) and len(tok.text) >= 3:
            leftover.append(tok.text)
        i += 1

    # «и» и «.» внутри цепочки не мешают: всё, что не распознано, — смысловой остаток
    f = SearchFilters()
    chips: list[FilterChip] = []

    def chip(key: str, value: Any, label: str, conf: float) -> None:
        chips.append(FilterChip(key=key, value=value, label=label, source="rule", confidence=conf))

    if found.roles:
        f.roles = [RoleSlug(r) for r in found.roles]
        for r in found.roles:
            chip("roles", r, f"Роль: {ROLE_LABELS[r]}", 0.85)
    if found.grades:
        lo = min((g[0] for g in found.grades), key=lambda g: g.order)
        hi = max((g[1] for g in found.grades), key=lambda g: g.order)
        f.grade_min, f.grade_max = lo, hi
        if lo == hi:
            chip("grade_min", lo.value, f"Грейд: {GRADE_LABELS[lo.value]}", 0.9)
        else:
            chip("grade_min", lo.value, f"Грейд от {GRADE_LABELS[lo.value]}", 0.9)
            chip("grade_max", hi.value, f"Грейд до {GRADE_LABELS[hi.value]}", 0.9)
    if found.must:
        f.skills_must = [SkillRequirement(slug=s) for s in found.must]
        for s in found.must:
            chip("skills_must", {"slug": s}, f"Навык: {names.get(s, s)}", 0.9)
    if found.nice:
        f.skills_nice = list(found.nice)
        for s in found.nice:
            chip("skills_nice", s, f"Желательно: {names.get(s, s)}", 0.85)
    if found.formats:
        f.formats = [WorkFormat(x) for x in found.formats]
        for x in found.formats:
            chip("formats", x, f"Формат: {FORMAT_LABELS[x]}", 0.9)
    if found.employment:
        f.employment_types = [EmploymentType(x) for x in found.employment]
        for x in found.employment:
            chip("employment_types", x, f"Занятость: {EMPLOYMENT_LABELS[x]}", 0.85)
    if salary_max is not None:
        f.salary_max = salary_max
        chip("salary_max", salary_max, f"Бюджет: до {salary_max:,} ₽".replace(",", " "), 0.9)
    if found.cities:
        f.cities = list(found.cities)
        for c in found.cities:
            chip("cities", c, f"Город: {c}", 0.85)
    for flag in ("relocation_ok", "active_only", "fsp_only"):
        if flag in found.flags:
            setattr(f, flag, True)
            chip(flag, True, FLAG_LABELS[flag], 0.8)
    if leftover:
        f.semantic_text = " ".join(leftover)
        chip("semantic_text", f.semantic_text, f"Смысл: {f.semantic_text}", 0.5)
    return ParsedQuery(filters=f, chips=chips, unparsed=unparsed, refining=False)
