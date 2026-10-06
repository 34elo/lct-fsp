"""Публичные эндпоинты: бейджи SVG, публичный профиль, OG-превью для краулеров."""

from __future__ import annotations

from html import escape as esc

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fsp_contracts.enums import ConsentType
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment_service
from app.candidates import service as candidates_service
from app.candidates.models import Candidate
from app.consents import service as consents_service
from app.deps import get_session
from app.views.service import generate_badge_svg

router = APIRouter()
public = APIRouter(prefix="/public", tags=["public"])
og = APIRouter(tags=["public"])
DASHBOARD_URL = "https://dashboard.fsp.patissons.tech"
CRAWLERS = (
    "telegram",
    "twitterbot",
    "vkshare",
    "vkbot",
    "slackbot",
    "facebookexternalhit",
    "discordbot",
)


@public.get("/badge/{slug}.svg", include_in_schema=False)
async def get_badge_svg(slug: str, session: AsyncSession = Depends(get_session)):
    """SVG бейдж «Подтверждено ФСП · Профессия · Грейд · ●●●●». Кеш 1 ч."""
    candidate = await candidates_service.get_by_pseudo_id(session, slug)
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    if not candidate.visibility.get("public_profile"):
        raise HTTPException(status_code=404, detail="candidate_not_found")

    grades = await assessment_service.get_grades(session, candidate.user_id)
    if not grades:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    # Проверяем согласие profile_publication
    has_publication_consent = await consents_service.has_consent(
        session, candidate.user_id, ConsentType.profile_publication
    )
    if not has_publication_consent:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    # Берём первый грейд для бейджа (профессия может быть несколько)
    grade_info = grades[0]

    # Генерируем SVG
    svg_content = generate_badge_svg(
        profession=grade_info.profession,
        grade=grade_info.grade,
        integrity=grade_info.integrity,
    )

    return Response(content=svg_content, media_type="image/svg+xml")


@public.get("/profiles/{slug}")
async def get_public_profile(slug: str, session: AsyncSession = Depends(get_session)):
    """Публичный профиль кандидата (если он включил видимость)."""
    candidate = await candidates_service.get_by_pseudo_id(session, slug)
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    # Проверяем видимость: должна быть включена public_profile
    if not candidate.visibility.get("public_profile"):
        raise HTTPException(status_code=404, detail="candidate_not_found")

    # Проверяем согласие profile_publication
    has_publication_consent = await consents_service.has_consent(
        session, candidate.user_id, ConsentType.profile_publication
    )
    if not has_publication_consent:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    # Получаем грейды
    grades = await assessment_service.get_grades(session, candidate.user_id)
    if not grades:
        raise HTTPException(status_code=404, detail="candidate_not_found")

    # Формируем профиль
    return {
        "pseudonym": candidate.pseudonym,
        "pseudo_id": candidate.pseudo_id,
        "city": candidate.city,
        "primary_role": candidate.primary_role,
        "grades": [
            {
                "profession": g.profession,
                "grade": g.grade,
                "confirmed_at": g.confirmed_at.isoformat(),
                "integrity": g.integrity,
            }
            for g in grades
        ],
    }


@og.get("/athlete/{slug}", include_in_schema=False)
async def get_athlete_og(slug: str, request: Request, session: AsyncSession = Depends(get_session)):
    """OG-превью для краулеров (Telegram, VK, Slack), редирект для людей на SPA."""
    # Определяем юзер-агент: если краулер, возвращаем HTML с OG; иначе редирект
    user_agent = request.headers.get("user-agent", "").lower()
    is_crawler = any(bot in user_agent for bot in CRAWLERS)

    candidate = await candidates_service.get_by_pseudo_id(session, slug)
    if not candidate:
        if is_crawler:
            return HTMLResponse("<html><body>Candidate not found</body></html>", status_code=404)
        # Редирект на главную если не найден
        return RedirectResponse(url=DASHBOARD_URL)

    # Проверяем видимость
    if not candidate.visibility.get("public_profile"):
        if is_crawler:
            return HTMLResponse("<html><body>Profile is private</body></html>", status_code=404)
        return RedirectResponse(url=DASHBOARD_URL)

    has_publication_consent = await consents_service.has_consent(
        session, candidate.user_id, ConsentType.profile_publication
    )
    if not has_publication_consent:
        if is_crawler:
            return HTMLResponse("<html><body>Profile is private</body></html>", status_code=404)
        return RedirectResponse(url=DASHBOARD_URL)

    # Получаем грейды для OG
    grades = await assessment_service.get_grades(session, candidate.user_id)
    if not grades:
        if is_crawler:
            return HTMLResponse("<html><body>No grades found</body></html>", status_code=404)
        return RedirectResponse(url=DASHBOARD_URL)

    grade_info = grades[0]

    if is_crawler:
        # Возвращаем HTML с OG-тегами для краулеров
        html_content = generate_og_html(
            candidate=candidate,
            grade_info=grade_info,
        )
        return HTMLResponse(content=html_content)
    else:
        # Редирект на SPA для людей
        return RedirectResponse(url=f"{DASHBOARD_URL}/athlete/{slug}")


def generate_og_html(candidate: Candidate, grade_info) -> str:
    """Генерирует HTML с OG-тегами для краулеров."""
    pseudonym = esc(candidate.pseudonym, quote=True)
    profession = esc(grade_info.profession, quote=True)
    grade = esc(grade_info.grade, quote=True)
    title = f"{pseudonym} · {profession} {grade}"
    description = f"Профиль {pseudonym} на платформе ФСП. {profession.capitalize()} {grade}."
    image_url = f"https://api.fsp.patissons.tech/api/v1/public/badge/{candidate.pseudo_id}.svg"

    page = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:image" content="{image_url}">
    <meta property="og:type" content="profile">
    <title>{title}</title>
</head>
<body>
    <p>Redirecting to <a href="{DASHBOARD_URL}/athlete/{candidate.pseudo_id}">profile</a>...</p>
    <script>
        window.location = "{DASHBOARD_URL}/athlete/{candidate.pseudo_id}";
    </script>
</body>
</html>"""
    return page


router.include_router(public)
router.include_router(og)
