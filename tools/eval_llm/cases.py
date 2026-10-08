"""Набор для замера LLM: вымышленные резюме с разметкой навыков, задания для ключей и объяснений.

Тексты резюме те же, что в `services/ml/tests/fixtures` (вымышленные данные, ПДн нет). Промпты
повторяют `services/ml/prompts/*/v1.j2` по смыслу; если там меняется версия, обновить здесь.
Разметка (`gold`) — навыки, которые реально есть в тексте; `trap` — навыки, которых в тексте нет
(модель, которая их назовёт, «придумывает»).
"""

from __future__ import annotations

from typing import Any

RESUME_SYSTEM = (
    "Ты извлекаешь факты из резюме ИТ-специалиста. Отвечай только JSON по заданной схеме.\n"
    "Правила:\n"
    "1. Ничего не придумывай. Если поля нет в тексте, верни null или пустой список.\n"
    "2. skills — профессиональные навыки: языки, фреймворки, библиотеки, базы данных, "
    "инструменты, платформы. Для КАЖДОГО навыка поле quote — дословный фрагмент текста резюме "
    "(5–15 слов), в котором навык упомянут. Копируй символы как есть. Навык без такого "
    "фрагмента не включай.\n"
    "3. name навыка — как он написан в тексте. Не обобщай: «FastAPI» не превращай в «Python».\n"
    "4. Личные качества в skills не включай.\n"
    "5. experience — места работы по порядку из текста; skills — названия навыков из описания.\n"
    "6. summary — одно предложение о специализации без имени и контактов."
)

RESUME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "full_name": {"type": ["string", "null"]},
        "city": {"type": ["string", "null"]},
        "summary": {"type": ["string", "null"]},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": ["string", "null"]},
                    "title": {"type": ["string", "null"]},
                    "start": {"type": ["string", "null"]},
                    "end": {"type": ["string", "null"]},
                    "skills": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["name", "quote"],
            },
        },
    },
    "required": ["skills", "experience"],
}

RESUMES: list[dict[str, Any]] = [
    {
        "id": "backend",
        "text": (
            "Пётр Вымыслов\nBackend-разработчик\nГород: Казань\n\nОпыт работы\n\n"
            "ООО «Вымышленная логистика», Backend-разработчик\n03.2021 — н.в.\n"
            "Разрабатываю микросервисы на Python и FastAPI, храню данные в Postgres 15.\n"
            "Очереди задач на RabbitMQ, кеширование в Redis. Сервисы упаковываю в Docker.\n\n"
            "ООО «Учебные системы», Стажёр-разработчик\nиюн 2020 – фев 2021\n"
            "Писал автотесты на pytest и скрипты для выгрузки отчётов.\n\n"
            "Образование\nВымышленный государственный университет, бакалавр, "
            "Прикладная математика, 2021\n\nНавыки\n"
            "Python, FastAPI, PostgreSQL, Redis, RabbitMQ, Docker, Git, Litestar\n"
            "Немного писал на JavaScript для внутренних админок."
        ),
        "gold": [
            "Python",
            "FastAPI",
            "PostgreSQL",
            "RabbitMQ",
            "Redis",
            "Docker",
            "pytest",
            "Git",
            "Litestar",
            "JavaScript",
        ],
        "trap": ["Java", "Kubernetes", "Go"],
    },
    {
        "id": "data",
        "text": (
            "Иванова Мария Сергеевна\nData Scientist\nг. Санкт-Петербург\n\nО себе\n"
            "Строю модели ранжирования и пайплайны данных, люблю воспроизводимые эксперименты.\n\n"
            "Места работы\nСентябрь 2022 — по настоящее время  Вымышленный Банк, ML-инженер\n"
            "Обучала модели на PyTorch, данные собирала в Airflow и хранила в ClickHouse.\n\n"
            "2019–2022 | АО «Придуманные данные» | Аналитик данных\n"
            "Отчёты на SQL и Python (pandas), дашборды в Grafana.\n\n"
            "Образование\nСанкт-Петербургский вымышленный университет, магистр, "
            "Прикладная информатика, 2019"
        ),
        "gold": ["PyTorch", "Airflow", "ClickHouse", "SQL", "Python", "pandas", "Grafana"],
        "trap": ["TensorFlow", "Spark", "Java"],
    },
    {
        "id": "frontend",
        "text": (
            "Орлов Андрей\nFrontend-разработчик\nМосква\n\nОпыт\n"
            "2021–2024 | ООО «Вымышленные интерфейсы» | Frontend-разработчик\n"
            "Писал интерфейсы на React и TypeScript, сборка на Vite, тесты на Vitest. "
            "Вёрстка на Tailwind CSS.\n"
            "2020–2021 | Фриланс | Верстальщик\nВёрстка лендингов на HTML и CSS, "
            "небольшие скрипты на JavaScript.\n\nНавыки\nReact, TypeScript, Vite, Git\n"
            "Командная работа, ответственность."
        ),
        "gold": [
            "React",
            "TypeScript",
            "Vite",
            "Vitest",
            "Tailwind CSS",
            "HTML",
            "CSS",
            "JavaScript",
            "Git",
        ],
        "trap": ["Angular", "Vue", "Node.js"],
    },
]

KEY_SYSTEM = (
    "Ты проверяешь задание для теста ИТ-специалистов и предлагаешь черновик правильного ответа. "
    "Отвечай только JSON по заданной схеме. Заполняй только поле для своего типа задания, "
    "остальные — null. choice: correct — номер верного варианта, считая с 0. "
    "find_bug: bug_lines — номера строк с дефектом, считая с 1. "
    "rationale — одно-два предложения, почему так."
)

KEY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "correct": {"type": ["integer", "null"]},
        "bug_lines": {"type": ["array", "null"], "items": {"type": "integer"}},
        "rationale": {"type": "string"},
    },
    "required": ["correct", "bug_lines", "rationale"],
}

KEYS: list[dict[str, Any]] = [
    {
        "id": "choice-mutable-default",
        "kind": "choice",
        "prompt": (
            'Тип задания: choice\n\nУсловие:\n"""\nЧто выведет код на Python?\n'
            "def f(x, acc=[]):\n    acc.append(x)\n    return acc\n"
            'f(1); print(f(2))\n"""\n\nВарианты:\n0. [2]\n1. [1, 2]\n2. [1]\n3. Ошибка'
        ),
        "expect": {"correct": 1},
    },
    {
        "id": "choice-index",
        "kind": "choice",
        "prompt": (
            'Тип задания: choice\n\nУсловие:\n"""\nКакая сложность поиска значения в '
            'сбалансированном двоичном дереве поиска из n элементов?\n"""\n\nВарианты:\n'
            "0. O(1)\n1. O(n)\n2. O(log n)\n3. O(n log n)"
        ),
        "expect": {"correct": 2},
    },
    {
        "id": "find-bug-sum",
        "kind": "find_bug",
        "prompt": (
            'Тип задания: find_bug\n\nУсловие:\n"""\nФункция должна вернуть сумму чисел от 1 до n '
            'включительно. Найди строку с дефектом.\n"""\n\nКод:\n'
            "1 | def total(n):\n2 |     s = 0\n3 |     for i in range(1, n):\n"
            "4 |         s += i\n5 |     return s"
        ),
        "expect": {"bug_lines": [3]},
    },
]

EXPLAIN_SYSTEM = (
    "Ты наставник на тесте ИТ-специалистов. Кандидат ответил на задание неверно. Причина ошибки "
    "уже определена, не меняй её и не называй правильный ответ. Напиши 2–4 коротких предложения "
    "по-русски: что, вероятно, пошло не так и на что обратить внимание. Не используй факты, "
    "которых нет во входных данных, не оценивай личность. Отвечай только JSON по заданной схеме."
)

EXPLAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}

EXPLAINS: list[dict[str, Any]] = [
    {
        "id": "explain-mutable-default",
        "prompt": (
            "Навык: Python\nТип задания: choice\nПричина: типичное заблуждение\n"
            "Типичное заблуждение: аргумент по умолчанию создаётся заново при каждом вызове\n"
            "Как на самом деле: значение по умолчанию вычисляется один раз при определении "
            'функции\n\nУсловие:\n"""\ndef f(x, acc=[]): acc.append(x); return acc\n'
            'f(1); print(f(2))\n"""'
        ),
        # фразы из «Как на самом деле» и ответа: в объяснении их быть не должно
        "forbidden": ["[1, 2]"],
    },
    {
        "id": "explain-off-by-one",
        "prompt": (
            "Навык: Python\nТип задания: find_bug\nПричина: ошибка границы диапазона\n\n"
            'Условие:\n"""\nСумма от 1 до n включительно считается циклом '
            'for i in range(1, n).\n"""'
        ),
        "forbidden": ["range(1, n + 1)", "range(1, n+1)"],
    },
]
