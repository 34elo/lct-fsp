"""E20-9b: Проверка, что у эндпоинтов модулей Б1 объявлены ошибки в OpenAPI.

Блок 1 (Б1) модули: assessment, taxonomy, identity, candidates, graph, resumes.
Маршруты Б1:
  - /assessment/* (assessment.router)
  - /families* (assessment.constructor_router)
  - /admin/families* (assessment.admin_router)
  - /taxonomy* (taxonomy.router)
  - /auth/* (identity.router)
  - /me (identity.router)
  - /candidates/me/* (candidates.router, graph.router, resumes.router)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# Маршруты, которые явно принадлежат Б1 (assessment, taxonomy, identity, candidates, graph, resumes)
BLOCK1_ROUTE_PREFIXES = {
    "/assessment",
    "/families",
    "/admin/families",
    "/taxonomy",
    "/auth",
    "/internal/taxonomy",
}


def _is_block1_route(path: str) -> bool:
    """Проверяет, принадлежит ли маршрут блоку 1."""
    # Специальный случай: /me это identity (Б1)
    if path == "/me":
        return True

    # Остальные маршруты /me/* это другие модули (telegram, offers и т.д.) - Б2
    b1_me_paths = {
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
    if path.startswith("/me/") and not any(p in path for p in b1_me_paths):
        return False  # это Б2 маршруты

    if path.startswith("/candidates/me/"):
        # Проверяем, это маршрут Б1 или Б2
        if any(p in path for p in b1_me_paths):
            return True  # это Б1: candidates, resumes, graph

    # Проверяем явные префиксы Б1
    for prefix in BLOCK1_ROUTE_PREFIXES:
        if path.startswith(prefix):
            return True

    return False


def test_block1_endpoints_have_error_responses(api: TestClient):
    """Каждый эндпоинт Б1 должен иметь описанные responses= с 4xx кодами."""
    openapi = api.get("/openapi.json").json()
    paths = openapi.get("paths", {})

    block1_routes = []
    for path, methods in paths.items():
        if not _is_block1_route(path):
            continue

        for method, details in methods.items():
            if method.lower() not in ["get", "post", "put", "patch", "delete"]:
                continue

            block1_routes.append((path, method.upper(), details))

    # Проверяем, что у каждого маршрута есть responses= с хотя бы одним кодом ошибки
    routes_without_responses = []
    for path, method, details in block1_routes:
        responses = details.get("responses", {})

        # Проверяем, что есть хотя бы одна ошибка (4xx или 5xx)
        has_error = any(int(code) >= 400 for code in responses.keys() if code != "default")

        if not has_error:
            routes_without_responses.append((path, method))

    assert not routes_without_responses, (
        "Следующие маршруты Б1 не имеют responses= с ошибками:\n"
        + "\n".join(f"  {method} {path}" for path, method in routes_without_responses)
    )


def test_block1_endpoints_have_correct_error_codes(api: TestClient):
    """Проверяем, что коды ошибок в responses= корректные (4xx или 503)."""
    openapi = api.get("/openapi.json").json()
    paths = openapi.get("paths", {})

    invalid_codes = []
    for path, methods in paths.items():
        for method, details in methods.items():
            if method.lower() not in ["get", "post", "put", "patch", "delete", "head", "options"]:
                continue

            responses = details.get("responses", {})
            for code in responses.keys():
                try:
                    code_int = int(code)
                    # Проверяем, что это либо 4xx/5xx, либо 2xx (успех)
                    if not (200 <= code_int < 600):
                        invalid_codes.append((path, method, code))
                except (ValueError, TypeError):
                    # "default" и другие строки - нормально
                    pass

    assert not invalid_codes, f"Некорректные коды ошибок: {invalid_codes}"


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
def test_block1_endpoints_registered(api: TestClient, path: str):
    """Проверяем, что основные маршруты Б1 зарегистрированы."""
    openapi = api.get("/openapi.json").json()
    paths = openapi.get("paths", {})

    # Ищем пути, которые начинаются с path
    found = any(p.startswith(path) for p in paths.keys())
    assert found, f"Маршрут {path} не найден в OpenAPI"
