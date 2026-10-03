"""Данные мока в памяти. Минимальный набор + герои демо; полный seed — E5-2 (tools/seed).

Все люди и команды вымышленные.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fsp_contracts.enums import FspDiscipline

DISCIPLINES = [d.value for d in FspDiscipline]

LAST = ["Иванов", "Петров", "Смирнов", "Кузнецов", "Попов", "Соколов", "Лебедев", "Морозов"]
FIRST = ["Алексей", "Мария", "Дмитрий", "Елена", "Сергей", "Ольга", "Андрей", "Наталья"]
REGIONS = [
    "Москва",
    "Санкт-Петербург",
    "Новосибирская область",
    "Татарстан",
    "Свердловская область",
]


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def _mask_phone(phone: str) -> str:
    return f"{phone[:2]}*******{phone[-2:]}"


def _mask_name(last: str, first: str) -> str:
    return f"{last[:1]}*** {first[:1]}."


class Store:
    def __init__(self) -> None:
        self.participants: dict[str, dict[str, Any]] = {}
        self.competitions: dict[str, dict[str, Any]] = {}
        self.teams: dict[str, dict[str, Any]] = {}
        self.results: dict[str, list[dict[str, Any]]] = {}  # participant_id -> результаты
        self.codes: list[dict[str, Any]] = []
        self.oauth_codes: dict[str, dict[str, Any]] = {}
        self.tokens: dict[str, str] = {}  # access_token -> participant_id
        self.sent_events: list[dict[str, Any]] = []

    # --- построение ---
    def add_participant(
        self,
        pid: str,
        last: str,
        first: str,
        *,
        middle: str | None = None,
        birth_year: int,
        region: str,
        email: str,
        phone: str = "+79001234567",
        ranks: list[dict[str, Any]] | None = None,
    ) -> None:
        self.participants[pid] = {
            "id": pid,
            "last_name": last,
            "first_name": first,
            "middle_name": middle,
            "birth_year": birth_year,
            "region": region,
            "email": email,
            "phone": phone,
            "ranks": ranks or [],
        }
        self.results.setdefault(pid, [])

    def add_competition(self, cid: str, **kw: Any) -> None:
        self.competitions[cid] = {
            "id": cid,
            "end_date": None,
            "tracks": [],
            "registration_url": None,
            "region": None,
            **kw,
        }

    def add_result(self, pid: str, **kw: Any) -> dict[str, Any]:
        res = {
            "stage": "final",
            "team_id": None,
            "team_role": "individual",
            "place": None,
            "participants_total": None,
            "score": None,
            "track": None,
            **kw,
        }
        self.results.setdefault(pid, []).append(res)
        return res

    # --- представления (схема fsp.md §3) ---
    def participant_view(self, pid: str) -> dict[str, Any]:
        p = self.participants[pid]
        return {
            "id": p["id"],
            "last_name": p["last_name"],
            "first_name": p["first_name"],
            "middle_name": p["middle_name"],
            "birth_year": p["birth_year"],
            "region": p["region"],
            "email_masked": _mask_email(p["email"]),
            "phone_masked": _mask_phone(p["phone"]),
            "ranks": p["ranks"],
        }

    def brief_view(self, pid: str) -> dict[str, Any]:
        p = self.participants[pid]
        return {
            "id": pid,
            "full_name_masked": _mask_name(p["last_name"], p["first_name"]),
            "region": p["region"],
            "birth_year": p["birth_year"],
        }

    def standings(self, cid: str) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for pid, items in self.results.items():
            for r in items:
                if r["competition_id"] != cid or r["place"] is None:
                    continue
                key = r["team_id"] or pid
                row = rows.setdefault(
                    key,
                    {
                        "place": r["place"],
                        "team_id": r["team_id"],
                        "participant_ids": [],
                        "score": r["score"],
                    },
                )
                row["participant_ids"].append(pid)
        return sorted(rows.values(), key=lambda x: x["place"])


def build_store() -> Store:
    s = Store()
    today = date.today()
    # соревнования: 12 прошедших, 3 будущих
    for i in range(12):
        disc = DISCIPLINES[i % 5]
        start = today - timedelta(days=60 * (i + 1))
        s.add_competition(
            f"c-{i + 1:03d}",
            title=f"Кубок России (вымышленный) №{i + 1}, {disc}",
            discipline=disc,
            level=["regional", "interregional", "national", "international"][i % 4],
            format="online" if i % 2 else "offline",
            start_date=start,
            end_date=start + timedelta(days=2),
            status="finished",
            tracks=["web", "ml"] if disc == "product" else [],
        )
    for j in range(3):
        start = today + timedelta(days=30 * (j + 1))
        s.add_competition(
            f"c-{100 + j}",
            title=f"Будущий этап (вымышленный) №{j + 1}",
            discipline=DISCIPLINES[j],
            level="national",
            format="offline",
            start_date=start,
            end_date=start + timedelta(days=2),
            status="announced" if j else "registration",
            registration_url=f"https://fsp.example/events/c-{100 + j}",
        )

    # герои демо (вручную)
    s.add_participant(
        "p-anya",
        "Волкова",
        "Анна",
        middle="Сергеевна",
        birth_year=2004,
        region="Санкт-Петербург",
        email="anya.volkova@example.test",
        ranks=[{"discipline": "product", "rank": "rank_2", "assigned_at": "2025-06-01"}],
    )
    s.add_participant(
        "p-dima",
        "Орлов",
        "Дмитрий",
        birth_year=1996,
        region="Москва",
        email="dima.orlov@example.test",
    )
    s.teams["t-north-lights"] = {
        "id": "t-north-lights",
        "name": "Северное сияние",
        "competition_id": "c-002",
        "members": [
            {"participant_id": "p-anya", "role": "captain"},
            {"participant_id": "p-m01", "role": "member"},
            {"participant_id": "p-m02", "role": "member"},
        ],
    }

    rng = random.Random(42)
    for i in range(1, 31):
        s.add_participant(
            f"p-m{i:02d}",
            rng.choice(LAST),
            rng.choice(FIRST),
            birth_year=rng.randint(1995, 2006),
            region=rng.choice(REGIONS),
            email=f"user{i:02d}@example.test",
        )
    s.add_result(
        "p-anya",
        competition_id="c-002",
        discipline="product",
        stage="final",
        team_id="t-north-lights",
        team_role="captain",
        place=2,
        participants_total=40,
        score=87.5,
        track="web",
        date=s.competitions["c-002"]["end_date"],
    )
    for m in ("p-m01", "p-m02"):
        s.add_result(
            m,
            competition_id="c-002",
            discipline="product",
            stage="final",
            team_id="t-north-lights",
            team_role="member",
            place=2,
            participants_total=40,
            score=87.5,
            track="web",
            date=s.competitions["c-002"]["end_date"],
        )
    s.add_result(
        "p-dima",
        competition_id="c-001",
        discipline="algorithmic",
        stage="final",
        team_role="individual",
        place=14,
        participants_total=120,
        score=5.0,
        date=s.competitions["c-001"]["end_date"],
    )
    for i in range(3, 31):
        cid = f"c-{rng.randint(1, 12):03d}"
        c = s.competitions[cid]
        s.add_result(
            f"p-m{i:02d}",
            competition_id=cid,
            discipline=c["discipline"],
            stage=rng.choice(["qualifier", "final"]),
            place=rng.randint(1, 60),
            participants_total=60,
            score=round(rng.uniform(1, 100), 1),
            date=c["end_date"],
        )
    return s


def load_store(path: str | Path) -> Store:
    """Данные мока из JSON, который пишет `tools/seed` (`fsp-mock`): участники, соревнования,
    команды, результаты. Даты — ISO-строки."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    s = Store()
    for c in data["competitions"]:
        c = dict(c)
        c["start_date"] = date.fromisoformat(c["start_date"])
        if c.get("end_date"):
            c["end_date"] = date.fromisoformat(c["end_date"])
        s.add_competition(c.pop("id"), **c)
    for p in data["participants"]:
        p = dict(p)
        s.add_participant(
            p["id"],
            p["last_name"],
            p["first_name"],
            middle=p.get("middle_name"),
            birth_year=p["birth_year"],
            region=p["region"],
            email=p["email"],
            phone=p.get("phone") or "+79001234567",
            ranks=p.get("ranks") or [],
        )
    for t in data["teams"]:
        s.teams[t["id"]] = t
    for pid, items in data["results"].items():
        for r in items:
            r = dict(r)
            r["date"] = date.fromisoformat(r["date"])
            s.add_result(pid, **r)
    return s
