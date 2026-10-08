"""Наполнение core по плану через его сервисные слои (не прямыми INSERT-ами в доменные таблицы).

Что проходит через сервисы core: регистрация (`identity`), анкета (`candidates`), согласия
(`consents`), резюме (`resumes.confirm` → доказательства `resume`/`self`), события ФСП
(`graph.fsp_ingest.on_*` — те же функции, что у core-worker), доказательства GitHub и тестов
(`graph.service.upsert_evidence`), пересчёт доверия, категории и грейда (`recompute_profile`),
компании и вакансии (`companies`, `vacancies`), seed-грейды (`grades.seed_grades`),
подбор (`matching.match_vacancy`), офферы и смена
их статусов (`offers.create/transition`). Прямые записи остаются там, где сервиса пока нет:
роль админа демо, `responsibility_score` компаний, provisional-навыки.

Идемпотентность: кандидат/компания/админ, которые уже есть (по email), пропускаются; офферы —
по `Idempotency-Key`; вакансии компании добираются до плана. Повторный запуск ничего не дублирует.
"""

from __future__ import annotations

import hashlib
import random
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import structlog
from app.analytics import service as analytics
from app.analytics.models import AnalyticsEventRow
from app.candidates import service as candidates
from app.candidates.models import Candidate
from app.companies import service as companies
from app.companies.models import Company
from app.consents import service as consents
from app.graph import fsp_ingest
from app.graph import service as graph
from app.graph.recompute import recompute_profile
from app.graph.service import EvidenceIn
from app.graph.trust import TrustConfig
from app.identity import service as identity
from app.identity.models import User
from app.matching import service as matching
from app.matching.models import Match
from app.matching.scoring import MatchConfig
from app.offers import service as offers
from app.offers.models import Offer
from app.offers.service import OfferLimits
from app.resumes import service as resumes
from app.resumes.models import Resume
from app.taxonomy.models import Skill
from app.taxonomy.service import SkillGraphCache
from app.vacancies import service as vacancies
from app.vacancies.models import Vacancy
from app.vacancies.service import SkillReq
from fsp_contracts.analytics import AnalyticsEvent
from fsp_contracts.enums import ConsentType, DeclineReason, EvidenceSource, OfferStatus
from fsp_contracts.events import FspCompetitionsUpdated, FspLinked, FspResultsImported
from fsp_contracts.fsp import FspCompetition, FspRank, FspResult, FspTeam
from fsp_contracts.ml import ParsedResume, ResumeSkill
from fsp_platform.app import ProblemError
from fsp_platform.db import session_scope
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .plan import skill_names, stable_id

log = structlog.get_logger()

Factory = async_sessionmaker[AsyncSession]


class SeedError(RuntimeError):
    pass


def _ref_now(anchor: date) -> datetime:
    """«Сейчас» витрины: реальное время, если anchor — сегодня, иначе вечер anchor."""
    if anchor >= date.today():
        return datetime.now(UTC)
    return datetime.combine(anchor, time(18, 0), tzinfo=UTC)


class Seeder:
    def __init__(
        self,
        plan: dict[str, Any],
        factory: Factory,
        *,
        password: str,
        pseudo_secret: str,
        analytics_salt: str,
        trust: TrustConfig | None = None,
        match_cfg: MatchConfig | None = None,
        limits: OfferLimits | None = None,
    ) -> None:
        self.plan = plan
        self.factory = factory
        self.password = password
        self.pseudo_secret = pseudo_secret
        self.salt = analytics_salt
        self.trust = trust or TrustConfig.load()
        self.match_cfg = match_cfg or MatchConfig.load()
        self.limits = limits or OfferLimits.load()
        self.anchor = date.fromisoformat(plan["anchor"])
        self.now = _ref_now(self.anchor)
        self.graph_cache = SkillGraphCache()
        self.user_ids: dict[str, uuid.UUID] = {}  # ключ кандидата → user_id
        self.stats: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------ вспомогательное
    async def _user_by_email(self, s: AsyncSession, email: str) -> User | None:
        return await s.scalar(select(User).where(User.email == identity.normalize_email(email)))

    async def _skill_ids(self, s: AsyncSession, slugs: set[str]) -> dict[str, Skill]:
        rows = await s.scalars(select(Skill).where(Skill.slug.in_(slugs)))
        return {r.slug: r for r in rows}

    # ------------------------------------------------------------------------- запуск
    async def run(self) -> dict[str, int]:
        async with session_scope(self.factory) as s:
            n = await s.scalar(select(func.count()).select_from(Skill))
        if not n:
            raise SeedError("Справочник навыков пуст: сначала `make taxonomy-load`")
        await self.provisional_skills()
        await self.fsp_competitions()
        await self.admin()
        for c in self.plan["candidates"]:
            await self.candidate(c)
        await self.provisional_evidence()
        await self.companies_and_vacancies()
        await self.grades()  # до подбора: без грейда из теста кандидат не виден (E23-1)
        await self.match_all()
        await self.offer_history()
        await self.close_vacancies()
        await self.analytics_backfill()
        return dict(self.stats)

    # -------------------------------------------------------------------- граф навыков
    async def provisional_skills(self) -> None:
        async with session_scope(self.factory) as s:
            have = set(await s.scalars(select(Skill.slug)))
            for slug, name in self.plan["provisional_skills"]:
                if slug in have:
                    continue
                s.add(
                    Skill(
                        slug=slug,
                        name=name,
                        kind="hard",
                        status="provisional",
                        source="seed",
                        description="Демо: новый навык, ждёт подтверждения",
                    )
                )  # сервиса создания provisional-навыков в core пока нет (E16)
                self.stats["provisional_skills"] += 1

    async def provisional_evidence(self) -> None:
        """Несколько кандидатов заявили provisional-навыки (сила ≤ 0.25 по правилам доверия)."""
        rng = random.Random(f"{self.plan['seed']}|prov")
        keys = [
            c["key"] for c in self.plan["candidates"] if not c["hero"] and c["key"] in self.user_ids
        ]
        if not keys:
            return
        async with session_scope(self.factory) as s:
            for slug, _ in self.plan["provisional_skills"]:
                sk = await s.scalar(select(Skill).where(Skill.slug == slug))
                if sk is None or sk.status != "provisional":
                    continue
                chosen = rng.sample(keys, min(len(keys), rng.randint(2, 6)))
                for key in chosen:
                    uid = self.user_ids[key]
                    await graph.upsert_evidence(
                        s,
                        uid,
                        [
                            EvidenceIn(
                                skill_id=sk.id,
                                source=EvidenceSource.self_,
                                strength=0.15,
                                observed_at=self.anchor,
                                fact_type="resume",
                                fact_id=stable_id(key, "prov", slug),
                                details={"demo": True},
                                verified=False,
                            )
                        ],
                    )
                sk.support_candidates = len(chosen)

    # ------------------------------------------------------------------------- ФСП
    async def fsp_competitions(self) -> None:
        comps = [FspCompetition.model_validate(c) for c in self.plan["fsp"]["competitions"]]
        async with session_scope(self.factory) as s:
            await fsp_ingest.on_competitions(
                s, FspCompetitionsUpdated(competitions=comps), self.trust.fsp
            )

    async def _fsp_for(self, s: AsyncSession, uid: uuid.UUID, participant_id: str) -> None:
        fsp = self.plan["fsp"]
        part = next(p for p in fsp["participants"] if p["id"] == participant_id)
        results = [FspResult.model_validate(r) for r in fsp["results"][participant_id]]
        team_ids = {r.team_id for r in results if r.team_id}
        teams = [FspTeam.model_validate(t) for t in fsp["teams"] if t["id"] in team_ids]
        ranks = [FspRank.model_validate(r) for r in part["ranks"]]
        await fsp_ingest.on_linked(
            s,
            FspLinked(
                candidate_id=uid, participant_id=participant_id, verified=True, method="oauth"
            ),
            self.trust.fsp,
        )
        await fsp_ingest.on_results(
            s,
            FspResultsImported(
                candidate_id=uid,
                participant_id=participant_id,
                results=results,
                ranks=ranks,
                teams=teams,
                new=True,
            ),
            self.trust.fsp,
        )

    # --------------------------------------------------------------------- кандидаты
    async def admin(self) -> None:
        email = "admin@demo.fsp.test"
        async with session_scope(self.factory) as s:
            if await self._user_by_email(s, email):
                return
            user = await identity.register(s, email, self.password, "employer")
            user.role = (
                "fsp_admin"  # самостоятельно админом не зарегистрироваться (SELF_REGISTER_ROLES)
            )
            self.stats["admins"] += 1

    async def candidate(self, c: dict[str, Any]) -> None:
        names = skill_names()
        async with session_scope(self.factory) as s:
            existing = await self._user_by_email(s, c["email"])
            if existing is not None:
                self.user_ids[c["key"]] = existing.id
                return
            user = await identity.register(s, c["email"], self.password, "candidate")
            uid = user.id
            self.user_ids[c["key"]] = uid
            cand = await candidates.get_or_create(s, uid, self.pseudo_secret)
            await candidates.update_preferences(s, cand, c["profile"])
            await consents.set_consents(
                s, uid, [(ConsentType(t), True, None) for t in c["consents"]]
            )
            await self._resume(s, c, uid, names)
            await self._evidence(s, c, uid)
            if c["fsp"]:
                await self._fsp_for(s, uid, c["fsp"]["participant_id"])
            await recompute_profile(
                s, uid, None, self.trust, await self.graph_cache.get(s), now=self.now
            )
            self.stats["candidates"] += 1

    async def _resume(self, s: AsyncSession, c: dict[str, Any], uid: uuid.UUID, names) -> None:
        r = c["resume"]
        if not r["skills"]:
            return
        parsed = ParsedResume(
            parser_version="seed",
            summary=r.get("summary"),
            experience=[
                {
                    k: e.get(k)
                    for k in (
                        "company",
                        "title",
                        "start",
                        "end",
                        "description",
                        "skills",
                        "is_commercial",
                    )
                }
                for e in r["experience"]
            ],
            education=r["education"],
            skills=[
                ResumeSkill(
                    raw=names[slug][0],
                    slug=slug,
                    quote=names[slug][0],
                    method="alias",
                    confidence=0.9,
                )
                for slug in r["skills"]
                if slug in names
            ],
            total_experience_months=int(r.get("total_months") or 0),
        )
        row = Resume(
            id=stable_id(c["key"], "resume"),
            candidate_id=uid,
            file_key=f"seed/{c['key']}.json",
            sha256=hashlib.sha256(c["key"].encode()).hexdigest(),
            mime="application/pdf",
            status="parsed",
            parser_version="seed",
            parsed=parsed.model_dump(mode="json"),
        )
        s.add(row)
        await s.flush()
        await resumes.confirm(s, row, resumes.ParsedResumeEdits(), today=self.anchor)

    async def _evidence(self, s: AsyncSession, c: dict[str, Any], uid: uuid.UUID) -> None:
        if not c["evidence"]:
            return
        by = await self._skill_ids(s, {e["skill"] for e in c["evidence"]})
        items = []
        for e in c["evidence"]:
            sk = by.get(e["skill"])
            if sk is None or sk.kind != "hard":
                continue
            items.append(
                EvidenceIn(
                    skill_id=sk.id,
                    source=EvidenceSource(e["source"]),
                    strength=e["strength"],
                    observed_at=self.anchor - timedelta(days=int(e["days_ago"])),
                    fact_type=e["source"],
                    fact_id=stable_id(e["fact"], e["skill"]),
                    details=e.get("details") or {"demo": True},
                    verified=True,
                )
            )
        if items:
            await graph.upsert_evidence(s, uid, items)

    # --------------------------------------------------------------- компании, вакансии
    async def companies_and_vacancies(self) -> None:
        self.company_ids: dict[int, uuid.UUID] = {}
        self.owner_ids: dict[int, uuid.UUID] = {}
        for co in self.plan["companies"]:
            async with session_scope(self.factory) as s:
                user = await self._user_by_email(s, co["email"])
                if user is None:
                    user = await identity.register(s, co["email"], self.password, "employer")
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
                    if co["status"] == "verified":
                        await companies.verify(s, company.id)
                    company.responsibility_score = co[
                        "responsibility_score"
                    ]  # демо: считать пока нечем
                    self.stats["companies"] += 1
                else:
                    m = await companies.membership(s, user.id)
                    company = await s.get(Company, m.company_id)
                self.company_ids[co["idx"]] = company.id
                self.owner_ids[co["idx"]] = user.id
        by_company: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for v in self.plan["vacancies"]:
            by_company[v["company_idx"]].append(v)
        self.vacancy_ids: list[tuple[dict[str, Any], uuid.UUID]] = []
        for idx, planned in sorted(by_company.items()):
            async with session_scope(self.factory) as s:
                user = await s.get(User, self.owner_ids[idx])
                have = list(
                    await s.scalars(
                        select(Vacancy)
                        .where(Vacancy.company_id == self.company_ids[idx])
                        .order_by(Vacancy.created_at, Vacancy.id)
                    )
                )
                for pv, row in zip(planned, have, strict=False):
                    self.vacancy_ids.append((pv, row.id))
                for pv in planned[len(have) :]:
                    fields = {
                        k: pv[k]
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
                    skills = [
                        SkillReq(slug, True, pv.get("min_level", 2), 1.0) for slug in pv["required"]
                    ] + [SkillReq(slug, False, 1, 0.5) for slug in pv["nice"]]
                    v = await vacancies.create(s, user, fields, skills)
                    if pv["status"] in ("published", "closed") and (
                        self.plan_company(idx)["status"] == "verified"
                    ):
                        await vacancies.publish(s, user, v.id)
                    self.vacancy_ids.append((pv, v.id))
                    self.stats["vacancies"] += 1

    def plan_company(self, idx: int) -> dict[str, Any]:
        return self.plan["companies"][idx]

    async def grades(self) -> None:
        """Seed-грейды (`tools/seed/grades.py`, блок 1) — идемпотентно, как команда `grades`."""
        from .grades import seed_grades

        for k, v in (await seed_grades(self.factory, self.plan, self.user_ids)).items():
            self.stats[k] += v

    async def match_all(self) -> None:
        async with session_scope(self.factory) as s:
            ids = list(await s.scalars(select(Vacancy.id).where(Vacancy.status == "published")))
        for vid in sorted(ids, key=str):
            async with session_scope(self.factory) as s:
                await matching.match_vacancy(s, vid, self.match_cfg, self.trust, today=self.anchor)
                self.stats["matched_vacancies"] += 1

    # ------------------------------------------------------------------ история офферов
    async def offer_history(self) -> None:
        async with session_scope(self.factory) as s:
            done = await s.scalar(
                select(func.count())
                .select_from(Offer)
                .where(Offer.idempotency_key.like(f"seed-{self.plan['seed']}-%"))
            )
        if done:  # история уже посеяна: пары «вакансия — кандидат» зависят от подбора и плыли бы
            return
        hero_keys = {c["key"] for c in self.plan["candidates"] if c["hero"]}
        hero_uids = {self.user_ids[k] for k in hero_keys if k in self.user_ids}
        async with session_scope(self.factory) as s:
            pool: list[tuple[uuid.UUID, list[uuid.UUID]]] = []
            for pv, vid in self.vacancy_ids:
                if pv.get("hero") or pv["status"] == "draft":
                    continue
                rows = await s.execute(
                    select(Match.candidate_id)
                    .where(Match.vacancy_id == vid)
                    .order_by(Match.score.desc(), Match.candidate_id)
                )
                cands = [r for (r,) in rows if r not in hero_uids]
                if cands:
                    pool.append((vid, cands))
        if not pool:
            return
        # заранее раскладываем пары (вакансия, кандидат) по кругу
        cursor = [0] * len(pool)
        per_cand: dict[uuid.UUID, int] = defaultdict(int)
        pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
        n = len(self.plan["offers"])
        i = 0
        while len(pairs) < n and any(cursor[k] < len(pool[k][1]) for k in range(len(pool))):
            k = i % len(pool)
            i += 1
            vid, cands = pool[k]
            while cursor[k] < len(cands) and per_cand[cands[cursor[k]]] >= 3:
                cursor[k] += 1
            if cursor[k] >= len(cands):
                continue
            cand = cands[cursor[k]]
            cursor[k] += 1
            per_cand[cand] += 1
            pairs.append((vid, cand))
        planned = []
        for off, (vid, cid) in zip(self.plan["offers"], pairs, strict=False):
            created = self.now - timedelta(days=off["days_ago"], hours=1 + off["hour"] % 12)
            planned.append((created, off, vid, cid))
        planned.sort(key=lambda t: (t[0], t[1]["i"]))  # окно лимитов считает всё новее created
        for created, off, vid, cid in planned:
            try:
                async with session_scope(self.factory) as s:
                    fresh = await self._offer(s, created, off, vid, cid)
                if fresh:
                    self.stats["offers"] += 1
                    self.stats[f"offers_{off['outcome']}"] += 1
            except ProblemError as exc:
                self.stats[f"offers_skipped_{exc.code}"] += 1

    async def _offer(
        self,
        s: AsyncSession,
        created: datetime,
        off: dict[str, Any],
        vid: uuid.UUID,
        cid: uuid.UUID,
    ) -> bool:
        """True — оффер создан сейчас, False — это повтор (тот же Idempotency-Key)."""
        vac = await s.get(Vacancy, vid)
        company = await s.get(Company, vac.company_id)
        cand = await s.get(Candidate, cid)
        owner = next(u for k, u in self.owner_ids.items() if self.company_ids[k] == company.id)
        key = f"seed-{self.plan['seed']}-{off['i']}"
        offer, replay = await offers.create(
            s,
            company=company,
            user_id=owner,
            vacancy=vac,
            candidate=cand,
            salary_from=vac.salary_from,
            salary_to=vac.salary_to,
            message=f"Приглашаем вас на позицию «{vac.title}».",
            idempotency_key=key,
            limits=self.limits,
            now=created,
        )
        if replay:
            return False
        out = off["outcome"]
        t0 = created
        hrs = off["respond_hours"]
        when = t0 + timedelta(hours=hrs) if hrs else t0
        if out == "sent":
            return True
        if out == "viewed":
            await offers.mark_viewed(s, offer, t0 + timedelta(hours=2))
        elif out == "expired":
            await offers.transition(
                s,
                offer,
                OfferStatus.expired,
                actor="system",
                now=t0 + timedelta(days=self.limits.validity_days, minutes=5),
            )
        elif out == "declined":
            await offers.mark_viewed(s, offer, t0 + timedelta(minutes=30))
            await offers.decline(s, offer, DeclineReason(off["decline_reason"]), None, when)
        elif out == "withdrawn":
            await offers.withdraw(s, offer, when)
        else:  # accepted | interview | hired | not_hired
            await offers.mark_viewed(s, offer, t0 + timedelta(minutes=30))
            await offers.accept(s, offer, when)
            chain = {
                "accepted": [],
                "interview": ["interview"],
                "hired": ["interview", "hired"],
                "not_hired": ["interview", "not_hired"],
            }[out]
            for step in chain:
                when += timedelta(hours=6)
                await offers.set_status(s, offer, OfferStatus(step), when)
        return True

    async def close_vacancies(self) -> None:
        for pv, vid in self.vacancy_ids:
            if pv["status"] != "closed":
                continue
            async with session_scope(self.factory) as s:
                v = await s.get(Vacancy, vid)
                if v.status != "published":
                    continue
                owner = await s.get(User, self.owner_ids[pv["company_idx"]])
                await vacancies.close(s, owner, vid)
                self.stats["vacancies_closed"] += 1

    # --------------------------------------------------------------------- аналитика
    async def analytics_backfill(self) -> None:
        async with session_scope(self.factory) as s:
            done = await s.scalar(
                select(func.count())
                .select_from(AnalyticsEventRow)
                .where(AnalyticsEventRow.app_version == "demo-seed")
            )
        if done:  # бэкфилл уже сделан
            return
        events = []
        for e in self.plan["analytics"]:
            uid = self.user_ids.get(e["subject"])
            if uid is None:
                continue
            ts = self.now.replace(hour=e["hour"], minute=0, second=0, microsecond=0) - timedelta(
                days=e["days_ago"]
            )
            if ts > self.now:
                ts -= timedelta(days=1)
            events.append(
                AnalyticsEvent(
                    event=e["event"],
                    ts=ts,
                    actor=analytics.pseudonym(self.salt, uid),
                    role=e["role"],
                    channel=e["props"].get("channel", "web"),
                    app_version="demo-seed",
                    props=e["props"],
                )
            )
        for i in range(0, len(events), 500):
            async with session_scope(self.factory) as s:
                self.stats["analytics_events"] += await analytics.record(s, events[i : i + 500])
