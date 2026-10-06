"""Онлайн-метрики v2 (E31-4): права, воронки на известных событиях, скрытие малых ячеек, без ПДн."""

import uuid
from datetime import UTC, datetime, timedelta

from app.analytics import metrics
from test_fsp_dashboard import act, admin, push

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _row(event, actor, props=None, ts=NOW):
    return (event, actor, props or {}, ts)


def _uid():
    return str(uuid.uuid4())


def test_requires_fsp_admin(api):
    from core_helpers import register

    assert api.get("/admin/metrics").status_code == 401
    cand = register(api, "candidate")
    assert api.get("/admin/metrics", headers=cand).status_code == 403
    emp = register(api, "employer")
    assert api.get("/admin/metrics", headers=emp).status_code == 403
    h = admin(api)
    assert api.get("/admin/metrics?days=0", headers=h).status_code == 422
    assert api.get("/admin/metrics?days=181", headers=h).status_code == 422


def test_candidate_funnel_known_counts():
    rows = []
    for i in range(10):
        a = act(i)
        rows.append(_row("signup_completed", a))
        if i < 8:
            rows.append(_row("test_started", a))
        if i < 6:
            rows.append(_row("test_completed", a))
        if i < 3:
            rows.append(_row("category_changed", a))
    rows.append(_row("test_completed", act(999)))  # не из когорты регистраций
    f = {s.id: s for s in metrics.funnel(rows, metrics.CANDIDATE_STAGES).stages}
    assert [f[k].count for k in ("registered", "test_started", "test_finished")] == [10, 8, 6]
    assert f["test_started"].pct_of_first == 80.0
    assert f["test_finished"].pct_of_previous == 75.0
    assert f["category"].hidden and f["category"].count is None  # 3 человека < 5
    # шагов без событий (email, опрос) нет в цепочке: конверсия считается от предыдущего доступного
    assert not f["email"].available and f["email"].pct_of_previous is None
    assert not f["survey"].available
    assert f["test_started"].pct_of_previous == 80.0


def test_employer_funnel_and_invites():
    rows = []
    for i in range(10):
        a = act(i)
        rows.append(_row("need_created", a))
        if i < 7:
            rows.append(_row("category_viewed", a))
        if i < 5:
            rows.append(_row("shortlist_added", a))
            rows.append(_row("invite_sent", a, {"time_since_need_s": 100 * (i + 1)}))
    f = {s.id: s.count for s in metrics.funnel(rows, metrics.EMPLOYER_STAGES).stages}
    assert f == {"need": 10, "viewed": 7, "shortlist": 5, "invite": 5}
    inv = metrics.invites(rows)
    assert inv.sent == 5 and inv.answered is None
    assert inv.need_to_invite.median_s == 300 and inv.need_to_invite.n == 5


def test_invite_answers_and_timings():
    rows = []
    for i in range(10):
        rows.append(_row("invite_sent", act(100 + i)))
    reasons = ["low_salary"] * 5 + ["other"] * 1
    for i, reason in enumerate(reasons):
        props = {"decision": "declined", "reason": reason, "time_to_respond_s": 3600 * (i + 1)}
        rows.append(_row("invite_answered", act(i), props))
    for i in range(4):
        props = {"decision": "accepted", "time_to_respond_s": 100 * 3600}
        rows.append(_row("invite_answered", act(i), props))
    inv = metrics.invites(rows)
    assert inv.sent == 10 and inv.answered == 10
    assert inv.accepted is None and inv.declined == 6  # 4 < 5: скрыто
    assert inv.accept_rate is None
    # ответ за 72 ч: 6 отказов быстрее 72 ч из 10 со временем
    assert inv.respond_72h_rate == 60.0
    assert [(r.reason, r.count) for r in inv.decline_reasons] == [("low_salary", 5)]


def test_time_to_first_invite_and_14d_share():
    rows = []
    for i in range(10):
        a = act(i)
        rows.append(_row("signup_completed", a, ts=NOW))
        if i < 6:
            day = 2 if i < 5 else 20  # 5 уложились в 14 дней, один нет
            ts = NOW + timedelta(days=day)
            rows.append(_row("offer_received", a, {"offer_id": _uid()}, ts=ts))
    inv = metrics.invites(rows)
    assert inv.first_invite.n == 6 and inv.first_invite.median_s == 2 * 86400
    assert inv.invited_within_14d_pct == 50.0


def test_responses():
    rows = [_row("response_created", act(i)) for i in range(10)]
    for i in range(6):
        decision = "accepted" if i < 5 else "declined"
        props = {"decision": decision, "time_to_answer_s": 60}
        rows.append(_row("response_answered", act(i), props))
    r = metrics.responses(rows)
    assert (r.created, r.answered, r.accepted) == (10, 6, 5)
    assert r.answer_rate == 60.0 and r.accept_rate == 83.3
    assert r.time_to_answer.median_s == 60


def test_interest_funnel_known_counts():
    """Встречный оффер: интерес → открыл → пригласили → приняли (E33-8)."""
    rows = []
    for i in range(10):
        a = act(i)
        rows.append(_row("interest_shown", a))  # 10
        if i < 8:
            rows.append(_row("interest_answered", a, {"decision": "opened"}))  # 8
        if i < 6:
            rows.append(_row("interest_to_invite", a))  # 6
        if i < 4:
            rows.append(_row("invite_answered", a, {"decision": "accepted"}))  # 4 (но < 5)
    f = {s.id: s for s in metrics.funnel(rows, metrics.INTEREST_STAGES).stages}
    assert f["shown"].count == 10
    assert f["opened"].count == 8
    assert f["invited"].count == 6
    assert f["accepted"].hidden and f["accepted"].count is None  # 4 < 5: скрыто
    # конверсии
    assert f["opened"].pct_of_first == 80.0
    assert f["invited"].pct_of_previous == 75.0


def test_interest_metrics_full_funnel():
    """Полная воронка интереса с причинами отказов и временами."""
    rows = []
    for i in range(20):
        a = act(i)
        rows.append(_row("signup_completed", a, ts=NOW))
        rows.append(_row("interest_shown", a))
        if i < 16:
            open_ts = NOW + timedelta(hours=1 + i)
            rows.append(_row("interest_answered", a, {"decision": "opened"}, ts=open_ts))
        if i < 12:
            invite_ts = open_ts + timedelta(hours=2)
            rows.append(_row("interest_to_invite", a, ts=invite_ts))
        if i < 10:
            rows.append(_row("invite_answered", a, {"decision": "accepted"}))
    # добавим отказы с причинами (>= 5 для видимости)
    for i in range(16, 21):
        a = act(i)
        rows.append(_row("interest_answered", a, {"decision": "declined", "reason": "low_salary"}))

    m = metrics.interests(rows)
    assert m.shown == 20
    assert m.opened == 16
    assert m.invited == 12
    assert m.accepted == 10
    assert m.open_rate == 80.0
    assert m.invite_rate == 75.0
    assert m.accept_rate == 83.3
    assert m.first_contact.n == 16 and m.first_contact.median_s > 0
    assert m.time_to_invite.n == 12 and m.time_to_invite.median_s > 0
    assert len(m.decline_reasons) == 1
    assert m.decline_reasons[0].reason == "low_salary"
    assert m.decline_reasons[0].count == 5


def test_endpoint_end_to_end_real_events_no_pii(api):
    h = admin(api)
    ev = []
    for i in range(6):
        a = act(i)
        ev.append(("signup_completed", a, {"channel": "web"}))
        ev.append(("need_created", a, {"need_id": _uid(), "skills": 3}))
        ev.append(("invite_sent", a, {"invite_id": _uid(), "with_vacancy": True}))
    push(api, ev)
    body = api.get("/admin/metrics", headers=h).json()
    by = {s["id"]: s for s in body["candidate_funnel"]["stages"]}
    assert by["registered"]["count"] == 6 and not by["email"]["available"]
    assert body["employer_funnel"]["stages"][0]["count"] == 6
    assert body["invites"]["sent"] == 6
    assert body["responses"]["created"] is None  # нет событий: скрыто
    assert body["interests"]["shown"] is None  # нет событий интереса: скрыто
    assert act(2) not in api.get("/admin/metrics", headers=h).text
    assert "actor" not in api.get("/admin/metrics", headers=h).text
