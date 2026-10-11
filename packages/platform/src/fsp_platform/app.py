"""Фабрика FastAPI: request_id, Problem Details, healthz."""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fsp_platform.logging import set_correlation_id

PROBLEM = "application/problem+json"


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        errors: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.status, self.code, self.title, self.detail = status, code, title, detail
        self.errors, self.headers = errors, headers


def problem_response(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
):
    """RFC 9457 Problem Details."""
    body: dict = {"type": f"about:blank#{code}", "title": title, "status": status, "code": code}
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM, headers=headers)


def create_app(title: str, lifespan=None) -> FastAPI:
    app = FastAPI(title=title, lifespan=lifespan)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = set_correlation_id(request.headers.get("x-request-id"))
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(ProblemError)
    async def _problem(_: Request, exc: ProblemError):
        return problem_response(
            exc.status, exc.code, exc.title, exc.detail, exc.errors, exc.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else f"http_{exc.status_code}"
        return problem_response(exc.status_code, code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return problem_response(422, "validation_error", "Ошибка валидации", errors=errors)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        structlog.get_logger().error("unhandled_error", error=type(exc).__name__)
        return problem_response(500, "internal_error", "Внутренняя ошибка")

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"status": "ok"}

    return app
