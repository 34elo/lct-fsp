"""Тесты демо-операций ФСП: создание результата и сброс."""

import pytest
from fsp_connector.service import demo_create_result, demo_reset


@pytest.mark.asyncio
async def test_demo_create_result(adapter) -> None:
    """Демо: создать результат для случайного кандидата."""
    # Проверяем, что функция вызывает adapter._request с правильным путём
    await demo_create_result(adapter)
    # Функция должна завершиться без ошибок


@pytest.mark.asyncio
async def test_demo_reset(adapter) -> None:
    """Демо: сбросить результаты ФСП."""
    # Проверяем, что функция вызывает adapter._request с правильным путём
    await demo_reset(adapter)
    # Функция должна завершиться без ошибок
