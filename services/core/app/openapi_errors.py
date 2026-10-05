"""Problem Details в OpenAPI (blocks.md §4.10): `responses=problem_responses(401, 404)`."""

from __future__ import annotations

from typing import Any

from fsp_platform.app import PROBLEM
from pydantic import BaseModel

_TITLES = {
    400: "Некорректный запрос",
    401: "Нет авторизации",
    403: "Недостаточно прав (в том числе consent_required, email_not_verified)",
    404: "Не найдено (в том числе чужой ресурс)",
    409: "Конфликт (в том числе cooldown)",
    410: "Ресурс больше недоступен",
    413: "Слишком большой запрос",
    415: "Неподдерживаемый тип данных",
    422: "Ошибка валидации",
    429: "Слишком много запросов",
    503: "Зависимость недоступна",
}


class ProblemOut(BaseModel):
    """RFC 9457 + машинный `code` (api.md §1)."""

    type: str
    title: str
    status: int
    code: str
    detail: str | None = None
    errors: list[dict[str, str]] | None = None


def problem_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Словарь `responses` для декоратора роута: каждый код отдаёт `application/problem+json`."""
    return {
        code: {
            "model": ProblemOut,
            "description": _TITLES.get(code, "Ошибка"),
            "content": {PROBLEM: {"schema": {"$ref": "#/components/schemas/ProblemOut"}}},
        }
        for code in codes
    }
