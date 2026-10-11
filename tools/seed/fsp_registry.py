"""Демо-реестр ФСП: герои и жюри-кандидат с email своих аккаунтов.

`build_registry(plan)` — чистые данные (без БД); `seed_registry(url, plan)` — запись в БД
fsp-connector через `fsp_connector.registry.upsert_demo` (идемпотентно по ID). Привязок не создаёт:
после `make seed` + `make demo-snapshot` все герои «не привязаны», `make demo-reset` возвращает
это состояние.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from .plan import load_heroes

DATA = Path(__file__).with_name("fsp_registry.yaml")


def _date(item: dict[str, Any], anchor: date) -> str:
    if "date" in item:
        return str(item["date"])
    return (anchor - timedelta(days=int(item.get("days_ago", 0)))).isoformat()


def build_registry(plan: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    anchor = date.fromisoformat(plan["anchor"])
    events = [
        {k: v for k, v in e.items() if k != "days_ago"} | {"date": _date(e, anchor)}
        for e in raw["events"]
    ]
    participants = list(raw["participants"])
    for h in load_heroes().values():
        part = (h.get("fsp") or {}).get("participant")
        if not part or not h.get("email"):
            continue
        name = " ".join(
            x for x in (part["last_name"], part["first_name"], part.get("middle_name")) if x
        )
        # email аккаунта героя (не адрес из источника): «Привязать ФСП» находит его одной кнопкой
        participants.append({"id": part["id"], "full_name": name, "email": h["email"]})
    return {"events": events, "participants": participants, "results": list(raw["results"])}


async def seed_registry(database_url: str, plan: dict[str, Any]) -> dict[str, int]:
    from fsp_connector.registry import upsert_demo
    from fsp_platform.db import make_engine, make_session_factory

    data = build_registry(plan)
    engine = make_engine(database_url)
    try:
        return await upsert_demo(make_session_factory(engine), **data)
    finally:
        await engine.dispose()
