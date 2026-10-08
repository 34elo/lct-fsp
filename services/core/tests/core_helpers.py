"""Хелперы тестов: «чужой ресурс → 404» и «повторная доставка события не меняет результат»."""

import itertools
import uuid
from collections.abc import Awaitable, Callable

_seq = itertools.count(1)
PASSWORD = "correct-horse-battery"


def register(client, role: str = "candidate", **extra) -> dict[str, str]:
    """Регистрирует пользователя через API, возвращает заголовок `Authorization`."""
    email = f"u{next(_seq)}-{uuid.uuid4().hex[:6]}@example.test"
    r = client.post(
        "/auth/register", json={"email": email, "password": PASSWORD, "role": role, **extra}
    )
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def assert_foreign_is_404(client, method: str, url: str, intruder: dict[str, str], **kw) -> None:
    """Чужой ресурс: запрос от постороннего пользователя даёт 404 (не 403) с Problem Details."""
    r = client.request(method, url, headers=intruder, **kw)
    assert r.status_code == 404, f"{method} {url}: ждали 404, получили {r.status_code} {r.text}"
    assert "code" in r.json()


async def assert_idempotent_delivery(
    deliver: Callable[[], Awaitable[object]],
    snapshot: Callable[[], Awaitable[object]],
    *,
    times: int = 2,
) -> None:
    """Повторная доставка не меняет результат.

    `deliver` — обработка одного и того же сообщения (одно `message_id`), `snapshot` — срез
    состояния (строки БД, число записей outbox). После первой доставки срез фиксируется,
    после повторов должен совпасть.
    """
    await deliver()
    before = await snapshot()
    for _ in range(times - 1):
        await deliver()
    assert await snapshot() == before, "повторная доставка изменила состояние"
