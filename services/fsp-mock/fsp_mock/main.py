"""fsp-mock: имитация API ФСП (docs/architecture/fsp.md §3). Данные в памяти, ПДн вымышленные."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
import jwt
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fsp_contracts.enums import FspDiscipline
from fsp_contracts.fsp import (
    FspCompetition,
    FspParticipant,
    FspParticipantBrief,
    FspResult,
    FspStandingRow,
    FspTeam,
    FspWebhook,
    MaskedContact,
)
from fsp_platform.app import ProblemError, create_app
from fsp_platform.logging import configure_logging
from pydantic import BaseModel

from fsp_mock.config import Settings
from fsp_mock.data import Store, build_store, load_store

log = structlog.get_logger()


class VerifySend(BaseModel):
    participant_id: str


class VerifyCheck(BaseModel):
    participant_id: str
    code: str


class MockResultIn(BaseModel):
    """Админ: создать результат участнику (и отправить вебхук)."""

    participant_id: str
    result: FspResult


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _load_signing_key(pem: str | None) -> rsa.RSAPrivateKey:
    if pem:
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        if isinstance(key, rsa.RSAPrivateKey):
            return key
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64u_int(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def build_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.service_name, settings.log_level)
    app = create_app(settings.service_name)
    app.description = (
        "Мок API ФСП (fsp.md §3). Данные вымышленные, хранятся в памяти.\n\n"
        "- `/api/v1/*` — требуют заголовок `X-Api-Key`.\n"
        "- `/oauth/*` — OAuth 2.0 code + PKCE (S256): `/oauth/authorize` отдаёт HTML-страницу "
        "выбора участника, редирект на `redirect_uri?code=&state=`; "
        "`/oauth/token` принимает form или JSON.\n"
        "- `/mock/results` — админ: создать результат, мок шлёт вебхук `result.published` на "
        "`FSP_WEBHOOK_URL` с подписью `X-Signature: sha256=HMAC(FSP_WEBHOOK_SECRET, body)`.\n"
        "- `/mock/codes` — админ: последние коды верификации (для демо)."
    )
    app.state.store = store or (
        load_store(settings.fsp_mock_data)
        if settings.fsp_mock_data and Path(settings.fsp_mock_data).is_file()
        else build_store()
    )
    # клиент вебхуков подменяется в тестах
    app.state.http = httpx.AsyncClient(timeout=5)
    st: Store = app.state.store

    # OIDC: подпись id_token (RS256), публичный ключ — в JWKS
    signing_key = _load_signing_key(settings.fsp_mock_oidc_private_key)
    pub = signing_key.public_key().public_numbers()
    kid = hashlib.sha256(f"{pub.n}:{pub.e}".encode()).hexdigest()[:16]
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _b64u_int(pub.n),
        "e": _b64u_int(pub.e),
    }
    issuer = settings.fsp_mock_issuer.rstrip("/")

    def api_key(x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key or not secrets.compare_digest(x_api_key, settings.fsp_mock_api_key):
            raise ProblemError(401, "unauthorized", "Неверный или отсутствует X-Api-Key")

    auth = [Depends(api_key)]

    def get_p(pid: str) -> dict[str, Any]:
        if pid not in st.participants:
            raise ProblemError(404, "not_found", "Участник не найден")
        return st.participants[pid]

    # ------------------------------------------------------------------ API v1
    @app.get("/api/v1/participants/{pid}", dependencies=auth)
    async def participant(pid: str) -> FspParticipant:
        get_p(pid)
        return FspParticipant.model_validate(st.participant_view(pid))

    @app.get("/api/v1/participants", dependencies=auth)
    async def find_participants(
        email: str | None = None, last_name: str | None = None
    ) -> list[FspParticipantBrief]:
        if not email and not last_name:
            raise ProblemError(422, "validation_error", "Нужен email или last_name")
        found = [
            p["id"]
            for p in st.participants.values()
            if (not email or p["email"].lower() == email.lower())
            and (not last_name or p["last_name"].lower() == last_name.lower())
        ]
        return [FspParticipantBrief.model_validate(st.brief_view(i)) for i in found]

    @app.get("/api/v1/participants/{pid}/results", dependencies=auth)
    async def results(pid: str, since: date | None = None) -> list[FspResult]:
        get_p(pid)
        return [
            FspResult.model_validate(r)
            for r in st.results.get(pid, [])
            if since is None or r["date"] >= since
        ]

    @app.get("/api/v1/competitions", dependencies=auth)
    async def competitions(
        from_: Annotated[date | None, Query(alias="from")] = None,
        to: date | None = None,
        discipline: FspDiscipline | None = None,
        status: str | None = None,
    ) -> list[FspCompetition]:
        out = []
        for c in sorted(st.competitions.values(), key=lambda x: x["start_date"]):
            if from_ and c["start_date"] < from_:
                continue
            if to and c["start_date"] > to:
                continue
            if discipline and c["discipline"] != discipline.value:
                continue
            if status and c["status"] != status:
                continue
            out.append(FspCompetition.model_validate(c))
        return out

    @app.get("/api/v1/competitions/{cid}/standings", dependencies=auth)
    async def standings(cid: str) -> list[FspStandingRow]:
        if cid not in st.competitions:
            raise ProblemError(404, "not_found", "Соревнование не найдено")
        return [FspStandingRow.model_validate(r) for r in st.standings(cid)]

    @app.get("/api/v1/teams/{tid}", dependencies=auth)
    async def team(tid: str) -> FspTeam:
        if tid not in st.teams:
            raise ProblemError(404, "not_found", "Команда не найдена")
        return FspTeam.model_validate(st.teams[tid])

    # ------------------------------------------------------------ верификация
    @app.post("/api/v1/verification/send", dependencies=auth)
    async def verification_send(body: VerifySend) -> MaskedContact:
        p = get_p(body.participant_id)
        code = f"{secrets.randbelow(10**6):06d}"
        st.codes.append(
            {
                "participant_id": p["id"],
                "code": code,
                "expires_at": datetime.now(UTC) + timedelta(seconds=settings.code_ttl_seconds),
                "attempts": 0,
                "used": False,
            }
        )
        return MaskedContact(channel="email", masked=st.participant_view(p["id"])["email_masked"])

    @app.post("/api/v1/verification/check", dependencies=auth)
    async def verification_check(body: VerifyCheck) -> dict[str, bool]:
        get_p(body.participant_id)
        active = [
            c for c in st.codes if c["participant_id"] == body.participant_id and not c["used"]
        ]
        if not active:
            return {"ok": False}
        rec = active[-1]
        if rec["expires_at"] < datetime.now(UTC) or rec["attempts"] >= settings.code_max_attempts:
            return {"ok": False}
        rec["attempts"] += 1
        if secrets.compare_digest(rec["code"], body.code):
            rec["used"] = True
            return {"ok": True}
        return {"ok": False}

    # ------------------------------------------------------------------ OAuth
    def page(items: list[dict[str, Any]], q: str, params: dict[str, str]) -> str:
        hidden = "".join(
            f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
            for k, v in params.items()
        )
        rows = "".join(
            f'<li><button name="participant_id" value="{html.escape(p["id"])}">'
            f"{html.escape(p['last_name'])} {html.escape(p['first_name'])}, "
            f"{html.escape(p['region'] or '')}</button></li>"
            for p in items
        )
        return (
            "<!doctype html><html lang='ru'><meta charset='utf-8'>"
            "<title>ФСП — вход (мок)</title><body style='font-family:sans-serif;max-width:480px;"
            "margin:2rem auto'><h1>Федерация спортивного программирования</h1>"
            "<p>Тестовый вход (мок). Выберите участника.</p>"
            f"<form method='get' action='/oauth/authorize'>{hidden}"
            f"<input name='q' value='{html.escape(q)}' placeholder='Фамилия'>"
            "<button>Найти</button></form>"
            f"<form method='post' action='/oauth/authorize'>{hidden}<ul>{rows}</ul></form>"
            "</body></html>"
        )

    oauth_keys = (
        "client_id",
        "redirect_uri",
        "state",
        "code_challenge",
        "code_challenge_method",
        "scope",
        "nonce",
    )

    @app.get("/oauth/authorize", response_class=HTMLResponse)
    async def authorize(request: Request, q: str = "") -> HTMLResponse:
        params = {k: request.query_params.get(k, "") for k in oauth_keys}
        if not params["redirect_uri"] or not params["code_challenge"]:
            raise ProblemError(400, "invalid_request", "Нужны redirect_uri и code_challenge (PKCE)")
        if params["code_challenge_method"] not in ("", "S256"):
            raise ProblemError(400, "invalid_request", "Поддерживается только S256")
        ql = q.lower()
        heroes = [p for pid, p in st.participants.items() if not pid.startswith("p-m")]
        items = [
            p
            for p in st.participants.values()
            if (ql and ql in p["last_name"].lower()) or (not ql and p in heroes)
        ][:20]
        return HTMLResponse(page(items, q, params))

    @app.post("/oauth/authorize")
    async def authorize_select(request: Request) -> RedirectResponse:
        form = await request.form()
        pid = str(form.get("participant_id", ""))
        get_p(pid)
        redirect_uri = str(form.get("redirect_uri", ""))
        challenge = str(form.get("code_challenge", ""))
        if not redirect_uri or not challenge:
            raise ProblemError(400, "invalid_request", "Нужны redirect_uri и code_challenge")
        code = secrets.token_urlsafe(24)
        st.oauth_codes[code] = {
            "participant_id": pid,
            "challenge": challenge,
            "redirect_uri": redirect_uri,
            "client_id": str(form.get("client_id", "")),
            "nonce": str(form.get("nonce", "")),
            "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        }
        query = {"code": code}
        if form.get("state"):
            query["state"] = str(form["state"])
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(f"{redirect_uri}{sep}{urlencode(query)}", status_code=303)

    def full_name(p: dict[str, Any]) -> str:
        return " ".join(x for x in (p["last_name"], p["first_name"], p["middle_name"]) if x)

    @app.get("/.well-known/openid-configuration")
    async def openid_configuration() -> dict[str, Any]:
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize",
            "token_endpoint": f"{issuer}/oauth/token",
            "userinfo_endpoint": f"{issuer}/oauth/userinfo",
            "jwks_uri": f"{issuer}/oauth/jwks",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": ["openid", "profile"],
            "claims_supported": ["sub", "name", "participant_id", "iss", "aud", "exp", "iat"],
        }

    @app.get("/oauth/jwks")
    async def jwks() -> dict[str, Any]:
        return {"keys": [jwk]}

    @app.post("/oauth/token")
    async def token(request: Request) -> dict[str, Any]:
        ctype = request.headers.get("content-type", "")
        data: dict[str, Any] = (
            await request.json()
            if ctype.startswith("application/json")
            else dict((await request.form()).items())
        )
        rec = st.oauth_codes.pop(str(data.get("code", "")), None)  # одноразовый
        if not rec or rec["expires_at"] < datetime.now(UTC):
            raise ProblemError(400, "invalid_grant", "Код недействителен или просрочен")
        if data.get("redirect_uri") and data["redirect_uri"] != rec["redirect_uri"]:
            raise ProblemError(400, "invalid_grant", "redirect_uri не совпадает")
        verifier = str(data.get("code_verifier", ""))
        if not verifier or not secrets.compare_digest(pkce_s256(verifier), rec["challenge"]):
            raise ProblemError(400, "invalid_grant", "PKCE: code_verifier не подходит")
        access = secrets.token_urlsafe(32)
        pid = rec["participant_id"]
        st.tokens[access] = pid
        now = datetime.now(UTC)
        claims: dict[str, Any] = {
            "iss": issuer,
            "sub": pid,
            "aud": str(data.get("client_id") or rec.get("client_id") or "fsp-career"),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
            "name": full_name(st.participants[pid]),
            "participant_id": pid,
        }
        if rec.get("nonce"):
            claims["nonce"] = rec["nonce"]
        id_token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": kid})
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": 3600,
            "id_token": id_token,
        }

    @app.get("/oauth/userinfo")
    async def userinfo(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        scheme, _, tok = (authorization or "").partition(" ")
        pid = st.tokens.get(tok) if scheme.lower() == "bearer" else None
        if not pid:
            raise ProblemError(401, "unauthorized", "Неверный токен")
        name = full_name(st.participants[pid])
        # participant_id/full_name — исходный контракт (FspOAuthIdentity); sub/name — OIDC
        return {"participant_id": pid, "full_name": name, "sub": pid, "name": name}

    # ------------------------------------------------------------------ /mock
    @app.post("/mock/results", dependencies=auth)
    async def mock_create_result(body: MockResultIn) -> dict[str, Any]:
        get_p(body.participant_id)
        if body.result.competition_id not in st.competitions:
            raise ProblemError(404, "not_found", "Соревнование не найдено")
        st.results.setdefault(body.participant_id, [])
        # upsert по (competition_id, stage)
        st.results[body.participant_id] = [
            r
            for r in st.results[body.participant_id]
            if (r["competition_id"], r["stage"]) != (body.result.competition_id, body.result.stage)
        ]
        st.add_result(body.participant_id, **body.result.model_dump(mode="python"))
        event = FspWebhook(
            event_id=str(uuid.uuid4()),
            type="result.published",
            participant_id=body.participant_id,
            competition_id=body.result.competition_id,
            occurred_at=datetime.now(UTC),
        )
        delivered = await send_webhook(event)
        return {"event_id": event.event_id, "webhook_delivered": delivered}

    async def send_webhook(event: FspWebhook) -> bool:
        st.sent_events.append(event.model_dump(mode="json"))
        if not settings.fsp_webhook_url:
            return False
        body = json.dumps(event.model_dump(mode="json"), ensure_ascii=False).encode()
        try:
            resp = await app.state.http.post(
                settings.fsp_webhook_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": sign(settings.fsp_webhook_secret, body),
                },
            )
            return resp.is_success
        except httpx.HTTPError as exc:
            log.warning("webhook_failed", error=type(exc).__name__)
            return False

    @app.get("/mock/codes", dependencies=auth)
    async def mock_codes() -> list[dict[str, Any]]:
        return [
            {"participant_id": c["participant_id"], "code": c["code"], "used": c["used"]}
            for c in st.codes[-20:]
        ]

    @app.post("/mock/reset", dependencies=auth, include_in_schema=False)
    async def mock_reset() -> dict[str, str]:
        """Админ: очистить результаты ФСП (демо-кнопка E13-3)."""
        st.results.clear()
        st.sent_events.clear()
        return {"status": "reset"}

    return app


app = build_app()
