"""Нагрузочные сценарии (E29-2): работодатели ищут и смотрят подборки, кандидаты — профиль и тест.

Запуск: `make load` (стек поднят, `make seed` выполнен). Аккаунты — демо-витрина
(`tools/seed/config.yaml`): hr{NN}@demo.fsp.test и cand{NNNN}@demo.fsp.test, пароль демо.
Имена запросов `search` и `matches` проверяются порогами в `tools/load/report.py`.
"""

from __future__ import annotations

import itertools
import os
import random

from locust import HttpUser, between, task

PASSWORD = os.environ.get("DEMO_PASSWORD", "demo-pass-1234")
EMPLOYERS = int(os.environ.get("LOAD_EMPLOYERS", "20"))  # hr01..hrNN
CANDIDATES = int(os.environ.get("LOAD_CANDIDATES", "100"))  # cand0001..cand<N>
_counter = itertools.count()

SEARCHES: list[dict] = [
    {"filters": {}, "sort": "match"},
    {"filters": {"fsp_only": True}, "sort": "match"},
    {"filters": {"active_only": True}, "sort": "fresh"},
    {"filters": {"roles": ["backend"], "grade_min": "middle"}, "sort": "match"},
    {"filters": {"skills_must": [{"slug": "python"}]}, "sort": "trust"},
]


class _Base(HttpUser):
    abstract = True
    wait_time = between(1, 3)
    email = ""
    logged_in = False

    def on_start(self) -> None:
        with self.client.post(
            "/api/v1/auth/login",
            json={"email": self.email, "password": PASSWORD},
            name="login",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"login {r.status_code}")
                return
            self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
            self.logged_in = True


class Employer(_Base):
    weight = 3

    def on_start(self) -> None:
        n = next(_counter) % EMPLOYERS + 1
        self.email = f"hr{n:02d}@demo.fsp.test"
        self.vacancy_ids: list[str] = []
        super().on_start()
        if not self.logged_in:
            return
        r = self.client.get("/api/v1/vacancies", name="vacancies")
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            self.vacancy_ids = [v["id"] for v in items if v.get("id")]

    @task(5)
    def search(self) -> None:
        if self.logged_in:
            self.client.post(
                "/api/v1/search/candidates", json=random.choice(SEARCHES), name="search"
            )

    @task(4)
    def matches(self) -> None:
        if self.vacancy_ids:
            vid = random.choice(self.vacancy_ids)
            self.client.get(f"/api/v1/vacancies/{vid}/matches", name="matches")


class Candidate(_Base):
    weight = 2

    def on_start(self) -> None:
        n = next(_counter) % CANDIDATES + 1
        self.email = f"cand{n:04d}@demo.fsp.test"
        self.test_available = True
        super().on_start()

    @task(5)
    def profile(self) -> None:
        if self.logged_in:
            self.client.get("/api/v1/candidates/me/profile", name="profile")

    @task(2)
    def category(self) -> None:
        if self.logged_in:
            self.client.get("/api/v1/candidates/me/category", name="category")

    @task(1)
    def test(self) -> None:
        """Старт попытки и первое задание. Кулдаун/согласия (403/409) — штатный отказ, не ошибка."""
        if not (self.logged_in and self.test_available):
            return
        with self.client.post(
            "/api/v1/assessment/attempts",
            json={"profession": "backend", "declared_grade": "middle"},
            name="test_start",
            catch_response=True,
        ) as r:
            if r.status_code in (403, 409, 422):
                r.success()
                return
            if r.status_code in (404, 405):  # ручки теста нет в этом стенде
                r.success()
                self.test_available = False
                return
            if r.status_code not in (200, 201):
                r.failure(f"test_start {r.status_code}")
                return
            body = r.json()
            attempt_id = body.get("id") or body.get("attempt_id")
        if attempt_id:
            self.client.get(f"/api/v1/assessment/attempts/{attempt_id}/next", name="test_next")
