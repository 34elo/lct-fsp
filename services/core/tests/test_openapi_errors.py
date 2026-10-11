"""У эндпоинтов теста, справочника, идентичности и анкеты в OpenAPI объявлены ошибки.

Проверяемые маршруты:
  - /assessment/* (assessment.router)
  - /families* (assessment.constructor_router)
  - /admin/families* (assessment.admin_router)
  - /taxonomy* (taxonomy.router)
  - /auth/* и /me (identity.router)
  - /candidates/me/* (candidates.router, graph.router, resumes.router)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

ROUTE_PREFIXES = {
    "/assessment",
    "/families",
    "/admin/families",
    "/taxonomy",
    "/auth",
    "/internal/taxonomy",
}
# разделы анкеты под /me/* и /candidates/me/*; остальные /me/* — другие модули (telegram, offers…)
PROFILE_PATHS = {
    "profile",
    "assessment",
    "resumes",
    "category",
    "skills",
    "graph",
    "views",
    "preferences",
    "visibility",
    "stoplist",
}


def _is_checked_route(path: str) -> bool:
    if path == "/me":
        return True
    if path.startswith("/me/") and not any(p in path for p in PROFILE_PATHS):
        return False
    if path.startswith("/candidates/me/") and any(p in path for p in PROFILE_PATHS):
        return True
    return any(path.startswith(prefix) for prefix in ROUTE_PREFIXES)


def test_endpoints_have_error_responses(api: TestClient):
    """У каждого проверяемого эндпоинта в `responses=` есть хотя бы один код ошибки."""
    paths = api.get("/openapi.json").json().get("paths", {})
    missing = []
    for path, methods in paths.items():
        if not _is_checked_route(path):
            continue
        for method, details in methods.items():
            if method.lower() not in ["get", "post", "put", "patch", "delete"]:
                continue
            responses = details.get("responses", {})
            if not any(int(code) >= 400 for code in responses if code != "default"):
                missing.append((path, method.upper()))
    assert not missing, "Маршруты без описанных ошибок:\n" + "\n".join(
        f"  {method} {path}" for path, method in missing
    )


def test_response_codes_are_valid(api: TestClient):
    """Коды в `responses=` — настоящие HTTP-коды (2xx–5xx)."""
    paths = api.get("/openapi.json").json().get("paths", {})
    invalid = []
    for path, methods in paths.items():
        for method, details in methods.items():
            if method.lower() not in ["get", "post", "put", "patch", "delete", "head", "options"]:
                continue
            for code in details.get("responses", {}):
                try:
                    if not 200 <= int(code) < 600:
                        invalid.append((path, method, code))
                except (ValueError, TypeError):
                    pass  # "default" и другие строки допустимы
    assert not invalid, f"Некорректные коды ответов: {invalid}"


@pytest.mark.parametrize(
    "path",
    [
        "/assessment/attempts",
        "/assessment/survey",
        "/admin/families",
        "/families",
        "/taxonomy",
        "/internal/taxonomy/snapshot",
        "/taxonomy/professions",
        "/auth/register",
        "/auth/login",
        "/me",
        "/candidates/me/profile",
        "/candidates/me/resumes",
        "/candidates/me/graph",
    ],
)
def test_main_endpoints_registered(api: TestClient, path: str):
    """Основные маршруты теста, справочника, входа и анкеты есть в OpenAPI."""
    paths = api.get("/openapi.json").json().get("paths", {})
    assert any(p.startswith(path) for p in paths), f"Маршрут {path} не найден в OpenAPI"
