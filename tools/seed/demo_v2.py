"""Демо-данные v2: герои с историей теста, компании, вакансии, офферы, задания.

Данные — `demo_v2.yaml`. Всё идёт через сервисы core (как `loader.py`): регистрация, анкета,
резюме, `assessment.grading.on_finished` (настоящая запись грейда `source=test`, экспресс,
`needs_confirmation`), `offers.create/apply/transition`, `tasks.create_task/publish/submit`.
Возраст 15–17 и согласие родителя — `candidates.update_profile`. Идемпотентно: пользователи —
по email, попытки — по детерминированному id, офферы — по `Idempotency-Key`, отклики — по паре
«вакансия — кандидат», задания — по названию. Интересов (встречных сигналов) в core ещё нет —
раздел пропущен.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from typing import Any

import yaml
from app.assessment import grading, tasks
from app.assessment import service as assessment_service
from app.assessment.attempts import build_item, family_of
from app.assessment.config import load_config as load_assessment_config
from app.assessment.models import Attempt, FamilyRow, RegularTask, Response
from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.companies import service as companies
from app.companies.models import Company
from app.config import Settings
from app.graph.recompute import recompute_profile
from app.identity import service as identity
from app.identity.models import User
from app.matching import needs as needs_cfg
from app.matching import needs_service
from app.matching import service as matching
from app.matching.models import Need
from app.offers import service as offers
from app.offers.models import Offer
from app.vacancies import service as vacancies
from app.vacancies.models import Vacancy
from app.vacancies.service import SkillReq
from fsp_contracts.assessment import TestGrade
from fsp_contracts.enums import DeclineReason, OfferStatus
from fsp_contracts.ml import SearchFilters
from fsp_platform.app import ProblemError
from fsp_platform.db import session_scope
from sqlalchemy import select

from .loader import Seeder
from .plan import HERE, _hero_candidate, load_config, stable_id

DATA = HERE / "demo_v2.yaml"
FINISH_KINDS = ("exact", "choice", "estimate", "order", "find_bug", "sjt")


def load_data() -> dict[str, Any]:
    return yaml.safe_load(DATA.read_text(encoding="utf-8"))


def plan_attempts(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Чистый план: ключ героя → попытки по возрастанию давности (старые первыми)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for h in data["heroes"]:
        out[h["key"]] = list(h.get("history", []))
    for key, hist in data.get("extra_history", {}).items():
        out.setdefault(key, []).extend(hist)
    return {k: sorted(v, key=lambda a: -a["days_ago"]) for k, v in out.items()}


SHORTLIST_EMAILS = ("olga", "jury-hr", "hr02", "hr03", "hr04", "hr05")
SHORTLIST_NEED_TEXT = "Демо: кандидаты на заметку"


class DemoV2:
    def __init__(self, seeder: Seeder, data: dict[str, Any] | None = None) -> None:
        self.sd = seeder
        self.data = data or load_data()
        self.factory = seeder.factory
        self.user_ids: dict[str, uuid.UUID] = {}
        self.company_ids: dict[str, uuid.UUID] = {}
        self.owner_ids: dict[str, uuid.UUID] = {}
        self.vacancy_ids: dict[str, uuid.UUID] = {}
        self.stats = seeder.stats

    async def run(self) -> dict[str, int]:
        await self.heroes()
        await self.history()
        await self.companies_and_vacancies()
        await self.offers_and_applications()
        await self.regular_tasks()
        await self.shortlists()
        return dict(self.stats)

    # ------------------------------------------------------------------------- герои
    async def _uid(self, key: str, email: str | None = None) -> uuid.UUID:
        if key not in self.user_ids:
            email = email or f"{key}@demo.fsp.test"
            async with session_scope(self.factory) as s:
                u = await self.sd._user_by_email(s, email)
            if u is None:
                raise RuntimeError(f"нет демо-пользователя {email}: сначала make seed")
            self.user_ids[key] = u.id
        return self.user_ids[key]

    async def heroes(self) -> None:
        for h in self.data["heroes"]:
            c = _hero_candidate(load_config(), self.sd.anchor, h)
            await self.sd.candidate(c)
            self.user_ids[h["key"]] = self.sd.user_ids[c["key"]]
            if h.get("age"):
                async with session_scope(self.factory) as s:
                    cand = await s.get(Candidate, self.user_ids[h["key"]])
                    changes: dict[str, Any] = {"age_group": h["age"]}
                    if h["age"] == "minor":
                        changes["parent_consent"] = bool(h.get("parent_consent"))
                    await candidates.update_profile(s, cand, changes, pii_key=Settings().pii_key)

    # ---------------------------------------------------------------- история теста
    async def history(self) -> None:
        cfg = load_assessment_config()
        now_real = self.sd.now
        for key, attempts in plan_attempts(self.data).items():
            uid = await self._uid(key)
            for i, a in enumerate(attempts):
                att_id = stable_id("demo2-attempt", key, i)
                async with session_scope(self.factory) as s:
                    if await s.get(Attempt, att_id) is not None:
                        continue
                    finished = now_real - timedelta(days=a["days_ago"])
                    await self._attempt(s, cfg, uid, key, att_id, a, finished)
                    self.stats["demo2_attempts"] += 1
            async with session_scope(self.factory) as s:
                await recompute_profile(
                    s, uid, None, self.sd.trust, await self.sd.graph_cache.get(s), now=now_real
                )

    async def _attempt(self, s, cfg, uid, key, att_id, a, finished) -> None:
        passed = a["result"] == "passed"
        integrity = float(a.get("integrity", 1.0))
        n = int(a["items"])
        att = Attempt(
            id=att_id,
            candidate_id=uid,
            profession=a["profession"],
            declared_grade=a["declared"],
            stage="main",
            mode=a.get("mode", "standard"),
            status="passed" if passed else "failed",
            plan={
                "target": n,
                "main": {
                    "result": a["result"],
                    "low_confidence": False,
                    "items": n,
                    "llr": 3.2 if passed else -3.4,
                },
                "integrity": {"index": integrity, "demo": True},
                "theta_by_type": {},
            },
            theta=float(a["theta"]),
            se=0.45,
            llr=3.2 if passed else -3.4,
            integrity=integrity,
            started_at=finished - timedelta(minutes=14 if a.get("mode") == "express" else 38),
            finished_at=finished,
        )
        s.add(att)
        await s.flush()
        fams = list(
            await s.scalars(
                select(FamilyRow)
                .where(
                    FamilyRow.company_id.is_(None),
                    FamilyRow.status == "active",
                    FamilyRow.kind.in_(FINISH_KINDS),
                )
                .order_by(FamilyRow.slug)
            )
        )
        rng = random.Random(f"demo2:{key}:{att_id}")
        rng.shuffle(fams)
        p_ok = 0.8 if passed else 0.3
        for seq, fam in enumerate(fams[:n], start=1):
            s.add(
                Response(
                    attempt_id=att.id,
                    seq=seq,
                    family_id=fam.id,
                    seed=rng.getrandbits(62),
                    is_pilot=False,
                    answer="demo",
                    score=1.0 if rng.random() < p_ok else 0.0,
                    rt_ms=rng.randint(9_000, 90_000),
                    created_at=finished - timedelta(minutes=n - seq + 1),
                    answered_at=finished - timedelta(minutes=n - seq),
                )
            )
        await s.flush()
        await grading.on_finished(s, att, cfg, finished)

    # -------------------------------------------------------------- компании, вакансии
    async def companies_and_vacancies(self) -> None:
        for co in self.data["companies"]:
            async with session_scope(self.factory) as s:
                user = await self.sd._user_by_email(s, co["email"])
                if user is None:
                    user = await identity.register(s, co["email"], self.sd.password, "employer")
                    company = await companies.create_company(
                        s,
                        user,
                        {
                            "name": co["name"],
                            "inn": co["inn"],
                            "site": co["site"],
                            "description": co["about"],
                        },
                    )
                    await companies.verify(s, company.id)
                    company.responsibility_score = co["responsibility_score"]
                    self.stats["demo2_companies"] += 1
                else:
                    m = await companies.membership(s, user.id)
                    company = await s.get(Company, m.company_id)
                self.company_ids[co["key"]] = company.id
                self.owner_ids[co["key"]] = user.id
        for v in self.data["vacancies"]:
            async with session_scope(self.factory) as s:
                owner = await s.get(User, self.owner_ids[v["company"]])
                row = await s.scalar(
                    select(Vacancy).where(
                        Vacancy.company_id == self.company_ids[v["company"]],
                        Vacancy.title == v["title"],
                    )
                )
                if row is None:
                    fields = {
                        k: v[k]
                        for k in (
                            "title",
                            "role",
                            "grade_min",
                            "grade_max",
                            "formats",
                            "employment_type",
                            "city",
                            "salary_from",
                            "salary_to",
                            "description",
                        )
                    }
                    skills = [SkillReq(x, True, 2, 1.0) for x in v["required"]] + [
                        SkillReq(x, False, 1, 0.5) for x in v["nice"]
                    ]
                    row = await vacancies.create(s, owner, fields, skills)
                    await vacancies.publish(s, owner, row.id)
                    self.stats["demo2_vacancies"] += 1
                self.vacancy_ids[v["key"]] = row.id
        async with session_scope(
            self.factory
        ) as s:  # вакансия героя Ольги — первая у «Северного кода»
            olga = await self.sd._user_by_email(s, "olga@demo.fsp.test")
            m = await companies.membership(s, olga.id)
            ov = await s.scalar(
                select(Vacancy)
                .where(Vacancy.company_id == m.company_id)
                .order_by(Vacancy.created_at, Vacancy.id)
            )
            self.vacancy_ids["olga"] = ov.id
            self.company_ids["olga"] = m.company_id
            self.owner_ids["olga"] = olga.id
        for vid in sorted(self.vacancy_ids.values(), key=str):
            async with session_scope(self.factory) as s:
                await matching.match_vacancy(
                    s, vid, self.sd.match_cfg, self.sd.trust, today=self.sd.anchor
                )

    # ------------------------------------------------------------ офферы и отклики
    async def offers_and_applications(self) -> None:
        now = self.sd.now
        for o in self.data["offers"]:
            try:
                async with session_scope(self.factory) as s:
                    if await self._offer(s, o, now - timedelta(days=o["days_ago"], hours=2)):
                        self.stats["demo2_offers"] += 1
            except ProblemError as exc:
                self.stats[f"demo2_offers_skipped_{exc.code}"] += 1
        for a in self.data["applications"]:
            try:
                async with session_scope(self.factory) as s:
                    if await self._application(s, a, now - timedelta(days=a["days_ago"], hours=3)):
                        self.stats["demo2_applications"] += 1
            except ProblemError as exc:
                self.stats[f"demo2_applications_skipped_{exc.code}"] += 1

    async def _offer(self, s, o: dict[str, Any], created: datetime) -> bool:
        vac = await s.get(Vacancy, self.vacancy_ids[o["vacancy"]])
        company = await s.get(Company, vac.company_id)
        cand = await s.get(Candidate, await self._uid(o["candidate"]))
        owner = next(k for k, v in self.company_ids.items() if v == company.id)
        offer, replay = await offers.create(
            s,
            company=company,
            user_id=self.owner_ids[owner],
            vacancy=vac,
            candidate=cand,
            salary_from=vac.salary_from,
            salary_to=vac.salary_to,
            message=o.get("message") or f"Приглашаем вас на позицию «{vac.title}».",
            idempotency_key=f"demo2-{self.sd.plan['seed']}-{o['n']}",
            limits=self.sd.limits,
            now=created,
        )
        if replay:
            return False
        st, t = o["status"], created
        if st == "sent":
            return True
        await offers.mark_viewed(s, offer, t + timedelta(minutes=40))
        if st == "declined":
            await offers.decline(
                s, offer, DeclineReason(o["decline_reason"]), None, t + timedelta(hours=3)
            )
        elif st != "viewed":
            await offers.accept(s, offer, t + timedelta(hours=5))
            for step in {
                "accepted": [],
                "interview": ["interview"],
                "hired": ["interview", "hired"],
            }[st]:
                t += timedelta(hours=8)
                await offers.set_status(s, offer, OfferStatus(step), t + timedelta(hours=5))
        return True

    async def _application(self, s, a: dict[str, Any], created: datetime) -> bool:
        vac = await s.get(Vacancy, self.vacancy_ids[a["vacancy"]])
        cand = await s.get(Candidate, await self._uid(a["candidate"]))
        have = await s.scalar(
            select(Offer.id).where(Offer.vacancy_id == vac.id, Offer.candidate_id == cand.user_id)
        )
        if have is not None:
            return False
        offer = await offers.apply(
            s,
            vacancy=vac,
            candidate=cand,
            message=a.get("message"),
            limits=self.sd.limits,
            now=created,
        )
        if a["status"] == "viewed":
            await offers.mark_viewed_by_company(s, offer, created + timedelta(hours=6))
        elif a["status"] == "withdrawn":
            await offers.withdraw_application(s, offer, created + timedelta(hours=6))
        return True

    # ------------------------------------------------------- регулярные задания
    async def regular_tasks(self) -> None:
        for t in self.data["tasks"]:
            ckey = t["company"]
            async with session_scope(self.factory) as s:
                if await s.scalar(
                    select(RegularTask.id).where(
                        RegularTask.company_id == self.company_ids[ckey],
                        RegularTask.title == t["title"],
                    )
                ):
                    continue
                fam = await s.scalar(
                    select(FamilyRow).where(
                        FamilyRow.slug == t["family"], FamilyRow.company_id.is_(None)
                    )
                )
                if fam is None:
                    self.stats["demo2_tasks_skipped_no_family"] += 1
                    continue
                task = await tasks.create_task(
                    s,
                    company_id=self.company_ids[ckey],
                    author_id=self.owner_ids[ckey],
                    family_id=fam.id,
                    profession=t["profession"],
                    grade=TestGrade(t["grade"]),
                    title=t["title"],
                    period_days=14,
                )
                await tasks.publish(s, task, now=self.sd.now - timedelta(days=2))
                self.stats["demo2_tasks"] += 1
                for who, verdict in t["answers"].items():
                    uid = await self._uid(who)
                    item = build_item(family_of(fam), tasks._seed(uid, task), None)
                    answer = str(item.key) if verdict == "correct" else "0"
                    await tasks.submit(s, task, uid, answer)
                    self.stats["demo2_task_answers"] += 1

    # ------------------------------------------------------------------ шорт-листы
    async def shortlists(self) -> None:
        """Шорт-лист демо-работодателей не пуст: 3–5 видимых кандидатов у каждого.

        Берём кандидатов с грейдом и согласием на публикацию по кругу со сдвигом на работодателя,
        чтобы наборы различались. Идемпотентно: потребность помечена текстом.
        """
        async with session_scope(self.factory) as s:
            rows = (await s.execute(select(Candidate.user_id, Candidate.pseudo_id))).all()
            visible = await matching.visible_ids(s, [uid for uid, _ in rows])
            pool = sorted(((pid, uid) for uid, pid in rows if uid in visible))
            grades = await assessment_service.get_grades_many(s, [uid for _, uid in pool])
        pool = [(pid, uid) for pid, uid in pool if grades.get(uid)]
        if len(pool) < 3:
            return
        for i, name in enumerate(SHORTLIST_EMAILS):
            email = f"{name}@demo.fsp.test"
            async with session_scope(self.factory) as s:
                user = await self.sd._user_by_email(s, email)
                if user is None:
                    continue
                m = await companies.membership(s, user.id)
                if m is None:
                    continue
                exists = await s.scalar(
                    select(Need.id).where(
                        Need.company_id == m.company_id, Need.text == SHORTLIST_NEED_TEXT
                    )
                )
                if exists is not None:
                    continue
                size = 3 + i % 3
                start = (i * 4) % len(pool)
                picked = [pool[(start + k) % len(pool)] for k in range(min(size, len(pool)))]
                profession = grades[picked[0][1]][0].profession
                need = await needs_service.create(
                    s,
                    m.company_id,
                    SHORTLIST_NEED_TEXT,
                    SearchFilters(professions=[profession]),
                    needs_cfg.NeedsConfig.load(),
                )
                need.shortlist = [pid for pid, _ in picked]
                self.stats["demo2_shortlists"] += len(picked)


async def seed_demo_v2(seeder: Seeder) -> dict[str, int]:
    """Герои, компании, офферы и задания v2 поверх `make seed` (после `grades`)."""
    return await DemoV2(seeder).run()
