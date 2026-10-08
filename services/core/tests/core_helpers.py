"""Хелперы тестов: «чужой ресурс → 404», повторная доставка события, БД с миграциями."""

import itertools
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

_seq = itertools.count(1)
_CORE = Path(__file__).resolve().parents[1]
_template: Path | None = None


def upgrade_head(target: str | Path) -> None:
    """SQLite-файл `target` (путь или `sqlite+aiosqlite:///…`) с миграциями `head`.

    alembic запускается один раз на процесс в шаблон, дальше файл копируется: прогон миграций
    подпроцессом — секунды, копия — миллисекунды. Сами миграции проверяет test_migrations.py.
    """
    global _template
    path = Path(str(target).removeprefix("sqlite+aiosqlite:///"))
    if _template is None:
        tpl = Path(tempfile.mkdtemp(prefix="core-migrated-")) / "template.db"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-x",
                f"url=sqlite+aiosqlite:///{tpl}",
                "upgrade",
                "head",
            ],
            cwd=_CORE,
            check=True,
            capture_output=True,
        )
        _template = tpl
    shutil.copy(_template, path)


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
