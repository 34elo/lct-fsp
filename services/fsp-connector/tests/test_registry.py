"""Реестр ФСП (E39-28): нормализация, CSV, привязка по контактам, заявки, адаптер-источник."""

from datetime import date
from uuid import uuid4

import fakeredis
import pytest
from fastapi.testclient import TestClient
from fsp_connector.api import router
from fsp_connector.config import Settings
from fsp_connector.linking import LinkService
from fsp_connector.models import FspLink, metadata
from fsp_connector.registry import (
    RegistryAdapter,
    RegistryService,
    normalize_email,
    normalize_phone,
    parse_participants_csv,
    upsert_demo,
)
from fsp_connector.registry_api import router as registry_router
from fsp_connector.sync import SyncService
from fsp_contracts import Envelope
from fsp_platform.app import create_app
from fsp_platform.db import make_engine, make_session_factory, session_scope
from fsp_platform.outbox import OutboxRecord
from sqlalchemy import select

TOKEN = "t"
H = {"Authorization": f"Service {TOKEN}"}


# ------------------------------------------------------------------ нормализация
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Anya@Example.TEST ", "anya@example.test"),
        ("mailto:Jury-Candidate@demo.fsp.test", "jury-candidate@demo.fsp.test"),
        ("not-an-email", None),
        ("a@b", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("8 (900) 123-45-67", "+79001234567"),
        ("+7 900 123 45 67", "+79001234567"),
        ("79001234567", "+79001234567"),
        ("9001234567", "+79001234567"),
        ("+375 29 123 45 67", "+375291234567"),
        ("12345", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_csv_header_semicolon_and_errors():
    text = (
        "ФИО;Телефон;Email\n"
        "Иванов Иван;8 900 111-22-33;IVAN@x.ru\n"
        ";;\n"
        "Без Почты;;плохо\n"
        ";+79000000000;a@b.ru\n"
        "Петров Пётр;;p@x.ru\n"
    )
    parsed = parse_participants_csv(text)
    assert [(r.full_name, r.email, r.phone) for r in parsed.rows] == [
        ("Иванов Иван", "ivan@x.ru", "+79001112233"),
        ("Петров Пётр", "p@x.ru", None),
    ]
    assert {(e["line"], e["reason"]) for e in parsed.errors} == {(4, "bad_email"), (5, "no_name")}


def test_csv_without_header_positional():
    parsed = parse_participants_csv("Сидорова Анна, anna@x.ru, +7 901 000 00 01\n")
    assert parsed.rows[0].email == "anna@x.ru" and parsed.rows[0].phone == "+79010000001"


# ------------------------------------------------------------------ сервис
@pytest.fixture
async def env(tmp_path, adapter):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/r.db")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    factory = make_session_factory(engine)
    port = RegistryAdapter(adapter, factory)
    links = LinkService(port, factory, fakeredis.FakeAsyncRedis())
    reg = RegistryService(factory, links, SyncService(port, factory))
    yield reg, factory, port
    await engine.dispose()


async def _events(factory, type_=None):
    async with factory() as s:
        rows = (await s.execute(select(OutboxRecord).order_by(OutboxRecord.id))).scalars().all()
    envs = [Envelope.model_validate(r.payload) for r in rows]
    return [e for e in envs if type_ is None or e.type == type_]


async def _demo(factory):
    await upsert_demo(
        factory,
        events=[
            {
                "id": "e-jury",
                "title": "Кубок (вымышленный)",
                "discipline": "product",
                "level": "national",
                "date": "2026-05-01",
            },  # fmt: skip
        ],
        participants=[
            {"id": "r-jury", "full_name": "Жюри Кандидат", "email": "Jury-Candidate@demo.fsp.test"},
            {"id": "p-anya", "full_name": "Волкова Анна", "email": "anya@demo.fsp.test"},
            {"id": "r-ph", "full_name": "Телефонов Тест", "phone": "8 900 555-44-33"},
        ],
        results=[
            {"participant_id": "r-jury", "event_id": "e-jury", "place": 2, "team": "Альфа"},
            {"participant_id": "r-ph", "event_id": "e-jury", "place": 5},
        ],
    )


async def test_match_by_email_links_and_publishes(env):
    reg, factory, _ = env
    await _demo(factory)
    await _demo(factory)  # идемпотентно
    cid = uuid4()
    res = await reg.match(cid, ["  JURY-candidate@demo.fsp.test"], [])
    assert res.linked and res.participant_id == "r-jury" and res.matched_by == "email"
    linked = await _events(factory, "fsp.linked")
    assert len(linked) == 1
    assert linked[0].payload["method"] == "registry" and linked[0].payload["verified"] is True
    # повтор — та же привязка, нового события нет
    again = await reg.match(cid, ["jury-candidate@demo.fsp.test"], [])
    assert again.linked and again.participant_id == "r-jury"
    assert len(await _events(factory, "fsp.linked")) == 1


async def test_match_by_phone_and_not_found(env):
    reg, factory, _ = env
    await _demo(factory)
    res = await reg.match(uuid4(), ["nobody@x.ru"], ["+7 (900) 555 44 33"])
    assert res.linked and res.participant_id == "r-ph" and res.matched_by == "phone"
    miss = await reg.match(uuid4(), ["stranger@x.ru"], [])
    assert not miss.linked
    assert len(await _events(factory, "fsp.linked")) == 1


async def test_match_taken_participant_is_conflict(env):
    reg, factory, _ = env
    await _demo(factory)
    await reg.match(uuid4(), ["anya@demo.fsp.test"], [])
    with pytest.raises(Exception) as exc:
        await reg.match(uuid4(), ["anya@demo.fsp.test"], [])
    assert getattr(exc.value, "code", "") == "fsp_already_linked"


async def test_request_accept_and_reject(env):
    reg, factory, _ = env
    await _demo(factory)
    cid = uuid4()
    req = await reg.create_request(cid, "Чужой Человек", "other@x.ru", None, "Кубок")
    again = await reg.create_request(cid, "Чужой Человек", "other2@x.ru", None, None)
    assert again["id"] == req["id"] and again["email"] == "other2@x.ru"  # одна открытая заявка
    pending = await reg.list_requests("pending")
    assert [r["id"] for r in pending] == [req["id"]]
    out = await reg.accept_request(req["id"], "r-ph")
    assert out["status"] == "accepted" and out["participant_id"] == "r-ph"
    assert (await reg.candidate_request(cid))["status"] == "accepted"
    async with factory() as s:
        link = await s.get(FspLink, cid)
    assert link.method == "registry" and link.verified
    with pytest.raises(Exception) as exc:
        await reg.accept_request(req["id"], "r-ph")
    assert getattr(exc.value, "code", "") == "request_decided"

    other = uuid4()
    r2 = await reg.create_request(other, "Ещё Один", None, "8 901 000-00-00", None)
    rej = await reg.reject_request(r2["id"], "Нет в протоколах")
    assert rej["status"] == "rejected" and rej["reason"] == "Нет в протоколах"


async def test_request_needs_contact(env):
    reg, _, _ = env
    with pytest.raises(Exception) as exc:
        await reg.create_request(uuid4(), "Имя Фамилия", "", "", None)
    assert getattr(exc.value, "code", "") == "validation_error"


async def test_adapter_results_and_sync(env):
    reg, factory, port = env
    await _demo(factory)
    results = await port.get_results("r-jury")
    assert len(results) == 1
    r = results[0]
    assert r.competition_id == "e-jury" and r.place == 2 and r.participants_total == 5
    assert r.team_id == "rt:e-jury:Альфа" and r.team_role == "member"
    team = await port.get_team(r.team_id)
    assert team.name == "Альфа" and [m.participant_id for m in team.members] == ["r-jury"]
    comps = await port.get_competitions()
    assert any(c.id == "e-jury" for c in comps)
    part = await port.get_participant("r-jury")
    assert part.last_name == "Жюри" and part.email_masked == "j***@demo.fsp.test"

    cid = uuid4()
    await reg.match(cid, ["jury-candidate@demo.fsp.test"], [])
    async with session_scope(factory) as s:
        assert await SyncService(port, factory).sync_candidate(s, cid, reason="linked")
    imported = await _events(factory, "fsp.results.imported")
    assert imported[-1].payload["results"][0]["competition_id"] == "e-jury"
    comps_evt = await _events(factory, "fsp.competitions.updated")
    assert comps_evt[-1].payload["competitions"][0]["id"] == "e-jury"


async def test_result_change_resyncs_linked(env):
    reg, factory, _ = env
    await _demo(factory)
    cid = uuid4()
    await reg.match(cid, ["jury-candidate@demo.fsp.test"], [])
    before = len(await _events(factory, "fsp.results.imported"))
    ev = await reg.create_event(
        {
            "title": "Хакатон",
            "discipline": "algorithmic",
            "level": "regional",
            "date": date(2026, 6, 1),
        }  # fmt: skip
    )
    await reg.upsert_result("r-jury", ev["id"], 1, None)
    imported = await _events(factory, "fsp.results.imported")
    assert len(imported) == before + 1
    assert {r["competition_id"] for r in imported[-1].payload["results"]} == {"e-jury", ev["id"]}


async def test_create_and_import_participants(env):
    reg, _, _ = env
    p = await reg.create_participant("Новый Участник", "New@X.ru", "8 900 000 00 09")
    assert p["email"] == "new@x.ru" and p["phone"] == "+79000000009"
    with pytest.raises(Exception) as exc:
        await reg.create_participant("Двойник", "new@x.ru", None)
    assert getattr(exc.value, "code", "") == "participant_exists"
    out = await reg.import_csv("ФИО,email,телефон\nНовый Обновлённый,new@x.ru,\nДругой,d@x.ru,\n")
    assert out == {"created": 1, "updated": 1, "errors": []}
    found = await reg.list_participants("обновл")
    assert [x["full_name"] for x in found] == ["Новый Обновлённый"]
    assert [x["id"] for x in await reg.list_participants("+7 900 000-00-09")] == [p["id"]]


# ------------------------------------------------------------------ API
@pytest.fixture
def client(env):
    reg, _, _ = env
    app = create_app("t")
    app.include_router(router)
    app.include_router(registry_router)
    app.state.settings = Settings(service_token_core=TOKEN)
    app.state.registry = reg
    return TestClient(app)


def test_api_requires_service_token_and_works(client):
    c = client
    assert c.get("/internal/registry/events").status_code == 401
    r = c.post(
        "/internal/registry/events",
        json={
            "title": "Кубок",
            "discipline": "product",
            "level": "national",
            "date": "2026-05-01",
        },  # fmt: skip
        headers=H,
    )
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    patched = c.patch(f"/internal/registry/events/{eid}", json={"level": "regional"}, headers=H)
    assert patched.json()["level"] == "regional"
    missing = c.patch("/internal/registry/events/e-none", json={"title": "xx"}, headers=H)
    assert missing.status_code == 404
    p = c.post(
        "/internal/registry/participants",
        json={"full_name": "Тест Тестов", "email": "t@x.ru"},
        headers=H,
    ).json()
    res = c.put(
        "/internal/registry/results",
        json={"participant_id": p["id"], "event_id": eid, "place": 3},
        headers=H,
    )
    assert res.status_code == 200
    assert c.get(f"/internal/registry/results?event_id={eid}", headers=H).json()[0]["place"] == 3
    m = c.post(
        "/internal/registry/match",
        json={"candidate_id": str(uuid4()), "emails": ["T@x.ru"]},
        headers=H,
    ).json()
    assert m == {"linked": True, "participant_id": p["id"], "matched_by": "email"}
    none = c.get(f"/internal/registry/requests/by-candidate/{uuid4()}", headers=H)
    assert none.status_code == 200 and none.json() is None
    rej = c.post(f"/internal/registry/requests/{uuid4()}/reject", json={"reason": "нет"}, headers=H)
    assert rej.status_code == 404
    assert c.delete(f"/internal/registry/results/{res.json()['id']}", headers=H).status_code == 204


# ------------------------------------------------------------------ E43-4: результаты списком
def _results_file() -> str:
    """50 строк данных: 47 годных (в т.ч. 2 новых мероприятия) и 3 с ошибками."""
    rows = ["участник;мероприятие;дата;результат"]
    for i in range(47):
        rows.append(
            f"p{i}@x.ru;"
            + ("Кубок Весны;2026-04-01" if i % 2 else "Кубок Осени;01.10.2026")
            + f";{i + 1}"
        )
    rows.append("нет-такого@x.ru;Кубок Весны;2026-04-01;1")  # участник не найден
    rows.append("p1@x.ru;Кубок Весны;31.31.2026;1")  # формат даты
    rows.append("p2@x.ru;Кубок Весны;2026-04-01;первое")  # результат
    return "\n".join(rows)


async def _seed_p(factory, n=47):
    await upsert_demo(
        factory,
        events=[],
        participants=[
            {"id": f"r-p{i}", "full_name": f"Тестов {i}", "email": f"p{i}@x.ru"} for i in range(n)
        ],
        results=[],
    )


async def test_results_import_preview_commit_and_repeat(env):
    reg, factory, _ = env
    await _seed_p(factory)
    text = _results_file()
    assert text.count("\n") == 50

    prev = await reg.import_results(text, commit=False)
    assert prev["summary"] == {
        "total": 50,
        "errors": 3,
        "created": 47,
        "updated": 0,
        "unchanged": 0,
    }
    assert {ln["error"] for ln in prev["lines"] if ln["status"] == "error"} == {
        "participant_not_found", "bad_date", "bad_result"
    }  # fmt: skip
    assert len(prev["new_events"]) == 2 and not any(e["confirmed"] for e in prev["new_events"])
    assert await reg.list_results(None, None) == []  # превью ничего не пишет

    with pytest.raises(Exception) as exc:
        await reg.import_results(text, commit=True, skip_errors=False)
    assert getattr(exc.value, "code", "") == "has_errors"

    keys = [e["key"] for e in prev["new_events"]]
    # без подтверждения новых мероприятий строки пропускаются
    none = await reg.import_results(text, commit=True, skip_errors=True)
    assert none["summary"]["created"] == 0
    assert await reg.list_events() == []

    done = await reg.import_results(text, commit=True, skip_errors=True, create_events=keys)
    assert done["summary"]["created"] == 47 and done["summary"]["errors"] == 3
    assert len(await reg.list_results(None, None)) == 47
    assert len(await reg.list_events()) == 2

    again = await reg.import_results(text, commit=True, skip_errors=True, create_events=keys)
    assert again["summary"] == {
        "total": 50,
        "errors": 3,
        "created": 0,
        "updated": 0,
        "unchanged": 47,
    }
    assert len(await reg.list_results(None, None)) == 47 and len(await reg.list_events()) == 2

    changed = text.replace("p0@x.ru;Кубок Осени;01.10.2026;1", "p0@x.ru;Кубок Осени;01.10.2026;7")
    upd = await reg.import_results(changed, commit=True, skip_errors=True)
    assert upd["summary"]["updated"] == 1 and upd["summary"]["unchanged"] == 46


async def test_results_import_recomputes_linked_profile_via_outbox(env):
    reg, factory, _ = env
    await _demo(factory)
    cid = uuid4()
    await reg.match(cid, ["jury-candidate@demo.fsp.test"], [])
    before = len(await _events(factory, "fsp.results.imported"))
    text = (
        "участник;мероприятие;дата;результат\n"
        "jury-candidate@demo.fsp.test;Новый Кубок;2026-07-01;3\n"
    )
    prev = await reg.import_results(text, commit=False)
    assert len(await _events(factory, "fsp.results.imported")) == before  # dry-run без событий
    await reg.import_results(text, commit=True, create_events=[prev["new_events"][0]["key"]])
    imported = await _events(factory, "fsp.results.imported")
    assert len(imported) == before + 1
    assert len(imported[-1].payload["results"]) == 2
    await reg.import_results(text, commit=True)  # повтор: ничего не изменилось — событий нет
    assert len(await _events(factory, "fsp.results.imported")) == before + 1


async def test_results_import_lookup_duplicates_and_limits(env):
    reg, factory, _ = env
    await _demo(factory)
    text = (
        "Жюри Кандидат;Кубок (вымышленный);01.05.2026;участие\n"  # без заголовка, ФИО, по дате
        "r-ph;Кубок (вымышленный);;3 место\n"  # по ID, дата необязательна для известного
        "r-ph;Кубок (вымышленный);2026-05-01;4\n"  # дубль в файле
        "Волкова Анна;Неизвестный турнир;;1\n"  # новое мероприятие без даты
        "Волкова Анна;Неизвестный турнир;2026-08-01;1\n"
    )
    out = await reg.import_results(text, commit=False, default_discipline="product")
    st = [(ln["line"], ln["status"], ln["error"]) for ln in out["lines"]]
    assert st == [
        (1, "ok", None), (2, "ok", None), (3, "error", "duplicate"),
        (4, "error", "no_date"), (5, "ok", None),
    ]  # fmt: skip
    assert out["new_events"][0]["discipline"] == "product" and out["new_events"][0]["rows"] == 1
    # вставка из таблицы (TAB)
    tabs = "участник\tмероприятие\tдата\tрезультат\nr-ph\tКубок (вымышленный)\t\t2\n"
    assert (await reg.import_results(tabs, commit=False))["summary"]["created"] == 0
    assert (await reg.import_results(tabs, commit=False))["summary"]["updated"] == 1
    with pytest.raises(Exception) as exc:
        await reg.import_results("\n".join(f"r-ph;Кубок;;{i}" for i in range(1001)), commit=False)
    assert getattr(exc.value, "code", "") == "too_many_rows"


def test_results_import_api_requires_token(client):
    body = {"csv": "r-x;Кубок;2026-01-01;1"}
    assert client.post("/internal/registry/results/import", json=body).status_code == 401
    r = client.post("/internal/registry/results/import", json=body, headers=H)
    assert r.status_code == 200 and r.json()["summary"]["errors"] == 1
