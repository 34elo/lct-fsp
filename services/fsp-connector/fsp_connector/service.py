"""Демо-операции ФСП."""

from __future__ import annotations

import random
from datetime import date

import structlog
from fsp_contracts.fsp import FspResult

from fsp_connector.port import FspPort

log = structlog.get_logger()


def _http(port: object) -> object:
    """Снять обёртки (реестр, кеш) до HTTP-адаптера мока."""
    while hasattr(port, "inner"):
        port = port.inner
    return port


async def demo_create_result(port: FspPort) -> None:
    """Демо-кнопка: создать результат ФСП для случайного кандидата."""
    try:
        # Получить всех участников
        participants = await port.find_participant()
        if not participants:
            log.warning("demo_create_result: no participants")
            return

        # Выбрать случайного участника
        participant = random.choice(participants)
        participant_id = participant.id

        # Получить все соревнования
        competitions = await port.get_competitions()
        if not competitions:
            log.warning("demo_create_result: no competitions")
            return

        # Выбрать случайное соревнование
        competition = random.choice(competitions)

        # Создать результат
        result = FspResult(
            competition_id=competition.id,
            discipline=competition.discipline,
            stage=random.choice(["qualifier", "final"]),
            team_id=None,
            team_role="individual",
            place=random.randint(1, 20),
            participants_total=random.randint(20, 100),
            score=random.uniform(50, 100),
            track=None,
            date=date.today(),
        )

        # Отправить результат в мок через /mock/results
        # Для этого нужно использовать internal API мока
        from fsp_connector.http_adapter import HttpFspAdapter

        http = _http(port)
        if isinstance(http, HttpFspAdapter):
            await http._request(
                "POST",
                "/mock/results",
                json={
                    "participant_id": participant_id,
                    "result": result.model_dump(mode="json"),
                },
            )
            log.info(
                "demo_create_result",
                participant_id=participant_id,
                competition_id=competition.id,
            )
        else:
            log.warning("demo_create_result: not HttpFspAdapter")
    except Exception as e:
        log.exception("demo_create_result_failed", error=str(e))


async def demo_reset(port: FspPort) -> None:
    """Демо-кнопка: очистить результаты ФСП."""
    try:
        from fsp_connector.http_adapter import HttpFspAdapter

        http = _http(port)
        if isinstance(http, HttpFspAdapter):
            await http._request("POST", "/mock/reset")
            log.info("demo_reset: results cleared")
        else:
            log.warning("demo_reset: not HttpFspAdapter")
    except Exception as e:
        log.exception("demo_reset_failed", error=str(e))
