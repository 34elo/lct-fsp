"""Фабрика FastAPI: request_id, Problem Details, healthz."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from fsp_platform.logging import set_correlation_id

PROBLEM = "application/problem+json"


class ProblemError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str | None = None):
        self.status, self.code, self.title, self.detail = status, code, title, detail


def problem_response(status: int, code: str, title: str, detail: str | None = None):
    body = {"type": f"about:blank#{code}", "title": title, "status": status, "code": code}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def create_app(title: str) -> FastAPI:
    app = FastAPI(title=title)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = set_correlation_id(request.headers.get("x-request-id"))
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(ProblemError)
    async def _problem(_: Request, exc: ProblemError):
        return problem_response(exc.status, exc.code, exc.title, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else f"http_{exc.status_code}"
        return problem_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return problem_response(422, "validation_error", "Ошибка валидации", str(exc.errors()))

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"status": "ok"}

    return app
