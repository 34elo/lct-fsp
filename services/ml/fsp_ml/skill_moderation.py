"""Модерация упоминания навыка (skills.md §3.2): цензурность, ПДн и инъекции, «навык ли это».

Всё здесь детерминированное и работает без моделей. Серая зона классификатора «навык ли это»
(уверенность 0.4–0.7) отдаётся локальной LLM в `skill_pipeline`; без LLM остаётся правиловый ответ.
Малый классификатор токсичности (rubert-tiny-toxicity) и логрегрессия поверх bge-m3 не подключены:
словари и правила закрывают демо-объём, интерфейс `classify_kind` от этого не меняется.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Основы мата и оскорблений (ru/en). Ищем по границе слова, чтобы не цеплять «хлебушек».
_PROFANITY = re.compile(
    # сильные основы ловим и внутри слова («нахуй», «bullshit»)
    r"(хуй|хуе|хуя|пизд|ебан|бляд|мудак|мудил|пидор|пидар|гондон|залуп|шлюх|fuck|shit|bitch|"
    r"asshole|cunt)"
    # слабые — только с начала слова
    r"|(?<![а-яa-z])(ебат|ебл|ебу|сука|суки|дроч|говн|дерьм|хрен\b|хрень|dick|nigg\w+|retard)",
    re.IGNORECASE,
)
_INSULT_WORDS = {"идиот", "дебил", "тупой", "тупица", "урод", "кретин", "лох", "debil", "idiot"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL = re.compile(r"(https?://|www\.|t\.me/|\b[\w-]+\.(?:com|ru|org|io|net|dev|рф)\b/?)", re.I)
_HANDLE = re.compile(r"(?<!\w)@[\w]{3,}")
_PHONE = re.compile(r"(?:\+?\d[\s\-().]*){10,}")
_INJECTION = re.compile(
    r"(игнорируй|игнорировать|забудь|не\s+обращай\s+внимани|отмени\s+инструкци|"
    r"ignore\s+(all\s+|previous\s+|the\s+)*(instructions|rules|above)|disregard|"
    r"system\s*prompt|you\s+are\s+now|ты\s+теперь|выведи\s+(свой\s+)?промпт|"
    r"</?(system|assistant|user)>|\[/?inst\]|```)",
    re.I,
)

_POSITIONS = {
    "разработчик",
    "программист",
    "инженер",
    "developer",
    "engineer",
    "программист-разработчик",
    "менеджер",
    "manager",
    "директор",
    "director",
    "аналитик",
    "analyst",
    "тестировщик",
    "специалист",
    "руководитель",
    "тимлид",
    "тим лид",
    "team lead",
    "lead",
    "тех лид",
    "cto",
    "ceo",
    "архитектор",
    "стажёр",
    "стажер",
    "intern",
    "junior",
    "middle",
    "senior",
    "джуниор",
    "мидл",
    "сеньор",
    "студент",
    "выпускник",
    "фрилансер",
    "дизайнер",
    "designer",
    "devops инженер",
    "fullstack разработчик",
    "backend разработчик",
    "frontend разработчик",
    "бэкенд разработчик",
    "фронтенд разработчик",
    "data scientist",
    "product manager",
    "hr",
    "рекрутер",
    "консультант",
    "администратор",
    "сотрудник",
    "кандидат",
    "эксперт",
    "учитель",
    "преподаватель",
}
_COMPANIES = {
    "яндекс",
    "yandex",
    "google",
    "гугл",
    "сбер",
    "сбербанк",
    "sber",
    "тинькофф",
    "tinkoff",
    "т-банк",
    "vk",
    "вк",
    "mail.ru",
    "озон",
    "ozon",
    "wildberries",
    "вайлдберриз",
    "avito",
    "авито",
    "касперский",
    "kaspersky",
    "microsoft",
    "майкрософт",
    "apple",
    "amazon",
    "meta",
    "facebook",
    "netflix",
    "jetbrains",
    "газпром",
    "ростелеком",
    "мтс",
    "мегафон",
    "билайн",
    "лаборатория касперского",
    "фсп",
    "федерация спортивного программирования",
}
_CITIES = {
    "москва",
    "санкт-петербург",
    "питер",
    "спб",
    "новосибирск",
    "екатеринбург",
    "казань",
    "нижний новгород",
    "самара",
    "омск",
    "челябинск",
    "уфа",
    "красноярск",
    "воронеж",
    "пермь",
    "волгоград",
    "краснодар",
    "саратов",
    "тюмень",
    "томск",
    "минск",
    "киев",
    "алматы",
    "берлин",
    "лондон",
    "moscow",
    "london",
    "berlin",
    "россия",
    "russia",
    "сша",
    "usa",
}
_EVALUATIVE = {
    "красивый",
    "хороший",
    "плохой",
    "отличный",
    "быстрый",
    "опытный",
    "умный",
    "крутой",
    "лучший",
    "классный",
    "надёжный",
    "надежный",
    "удобный",
    "современный",
    "новый",
    "старый",
    "good",
    "bad",
    "great",
    "best",
    "nice",
    "fast",
    "cool",
    "awesome",
    "smart",
    "experienced",
    "молодой",
    "активный",
    "креативный",
    "энергичный",
    "позитивный",
    "ответственный",
}
_JUNK = {
    "опыт",
    "работа",
    "и",
    "др",
    "etc",
    "и т.д",
    "и т.п",
    "прочее",
    "другое",
    "разное",
    "всё",
    "все",
    "нет",
    "да",
    "none",
    "n/a",
    "na",
    "-",
    "тест",
    "test",
    "навык",
    "навыки",
    "skills",
    "скилы",
    "знание",
    "знания",
    "умение",
    "умения",
    "резюме",
    "стаж",
    "образование",
    "год",
    "года",
    "лет",
    "опыт работы",
    "знаю",
    "умею",
    "владею",
    "работаю",
    "пользователь",
    "компьютер",
    "интернет",
    "офис",
    "программа",
    "программы",
}

# Основы софт-навыков: качество человека или команды, не технология.
_SOFT_STEMS = (
    "коммуникабельн",
    "коммуникаци",
    "лидерств",
    "лидер",
    "командн",
    "работа в команд",
    "работа в коман",
    "стрессоустойчив",
    "обучаем",
    "самообучаем",
    "ответственност",
    "тайм-менеджмент",
    "тайм менеджмент",
    "тайм-менеджмент",
    "эмпатия",
    "наставничеств",
    "критическое мышление",
    "креативност",
    "гибкость",
    "адаптивност",
    "инициативност",
    "переговор",
    "публичные выступления",
    "презентаци",
    "умение слушать",
    "конфликт",
    "teamwork",
    "leadership",
    "communication",
    "time management",
    "mentoring",
    "empathy",
    "adaptability",
    "critical thinking",
    "problem solving",
    "ownership",
    "soft skill",
    "самоорганизац",
    "пунктуальн",
    "внимательност",
    "целеустремлен",
    "доброжелательн",
)
_DOMAIN_WORDS = {
    "финтех",
    "fintech",
    "медтех",
    "medtech",
    "edtech",
    "эдтех",
    "e-commerce",
    "ecommerce",
    "ритейл",
    "retail",
    "банкинг",
    "banking",
    "страхование",
    "insurance",
    "логистика",
    "logistics",
    "адтех",
    "adtech",
    "proptech",
    "healthtech",
    "gamedev",
    "геймдев",
    "телеком",
    "telecom",
    "ритейл-аналитика",
    "электронная коммерция",
    "здравоохранение",
    "автомобильная промышленность",
    "агротех",
    "agritech",
    "игровая индустрия",
    "кибербезопасность в банках",
    "госсектор",
    "энергетика",
}

# Признаки технологии: латиница с цифрами или спецсимволами, типичные суффиксы.
_TECH_LIKE = re.compile(r"[a-z][a-z0-9]*(?:[.+#/\-][a-z0-9]+)*[+#]*$")
_TECH_HINT_RU = (
    "програм",
    "алгоритм",
    "баз данн",
    "сеть",
    "сети",
    "шифрован",
    "тестирован",
    "разработк",
    "верстк",
    "анализ данн",
    "машинн",
    "нейрон",
    "контейнер",
    "виртуализац",
    "облачн",
    "отладк",
    "оптимизац",
    "архитектур",
    "api",
    "микросервис",
    "криптограф",
    "парсинг",
)


@dataclass(frozen=True)
class Moderation:
    ok: bool
    reason: str | None = None  # moderation | pii | injection
    hide_text: bool = False  # ПДн и инъекции: текст не сохраняем и не возвращаем в норме


def moderate(raw: str) -> Moderation:
    """Цензурность, ПДн, инъекции. Раньше всех остальных проверок и сопоставления."""
    text = raw.strip()
    low = text.lower().replace("ё", "е")
    if _INJECTION.search(low):
        return Moderation(False, "injection", hide_text=True)
    if _EMAIL.search(text) or _PHONE.search(text) or _URL.search(low) or _HANDLE.search(text):
        return Moderation(False, "pii", hide_text=True)
    if _PROFANITY.search(low) or set(re.findall(r"[a-zа-я]+", low)) & _INSULT_WORDS:
        return Moderation(False, "moderation")
    return Moderation(True)


def _has(words: set[str], low: str) -> bool:
    return low in words or any(low == f"{w}а" or low == f"{w}ы" for w in words)


def classify_kind(norm: str) -> tuple[str, float]:
    """Правила «навык ли это»: (hard, soft, domain или not_skill; уверенность)."""
    low = norm.strip().lower().replace("ё", "е")
    tokens = re.findall(r"[a-zа-я0-9+#.]+", low)
    if not tokens or len(low) < 2 or low in _JUNK or re.fullmatch(r"[\d\W_]+", low):
        return "not_skill", 0.97
    if len(tokens) > 6 or len(low) > 60:
        return "not_skill", 0.9  # предложение, а не название навыка
    if _has(_COMPANIES, low) or _has(_CITIES, low):
        return "not_skill", 0.95
    if low in _POSITIONS or (len(tokens) <= 3 and tokens[-1] in _POSITIONS and len(tokens) > 1):
        return "not_skill", 0.93
    if low in {w.replace("ё", "е") for w in _EVALUATIVE}:
        return "not_skill", 0.93
    if any(low.startswith(s) or s in low for s in _SOFT_STEMS):
        return "soft", 0.92
    if low in _DOMAIN_WORDS:
        return "domain", 0.9
    if _TECH_LIKE.match(low) and (len(low) >= 2):
        return "hard", 0.8
    if any(h in low for h in _TECH_HINT_RU):
        return "hard", 0.75
    # незнакомое русское слово или фраза: правила не уверены → серая зона
    return "hard", 0.5
