"""План демо-витрины (evaluation.md §4): чистая детерминированная функция от SEED.

Здесь нет ни БД, ни сети: `build_plan()` возвращает JSON-совместимый словарь, из которого
`fspdata.py` собирает данные fsp-mock, а `loader.py` наполняет core через его сервисные слои.
Один seed — одни и те же кандидаты, участники ФСП, компании, вакансии и план офферов; участники
мока и кандидаты порождаются вместе, поэтому результаты ФСП кандидата лежат и в мок-данных,
и в событиях, которые получает core.

Основа кандидатов и вакансий — `tools/synth` (латентная модель рынка, независимая от скоринга);
сидер добавляет то, чего синтетике не нужно: имена, города, компании, ФСП-календарь, команды.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
SEED_NS = uuid.UUID("5e3d2a10-9c41-4b7e-8d2f-0a1b2c3d4e5f")

TEAM_DISCIPLINES = {"product"}
DISCIPLINE_TITLES = {
    "algorithmic": "алгоритмическому программированию",
    "product": "продуктовому программированию",
    "security": "информационной безопасности",
    "uav": "программированию беспилотных систем",
    "robotics": "программированию робототехники",
}
DISCIPLINE_WEIGHTS = {
    "algorithmic": 0.35,
    "product": 0.28,
    "security": 0.15,
    "uav": 0.12,
    "robotics": 0.10,
}
LEVEL_TITLES = {
    "regional": "региональный этап",
    "interregional": "межрегиональный этап",
    "national": "всероссийский этап",
    "international": "международный этап",
}
LEVEL_WEIGHTS = {"regional": 0.4, "interregional": 0.3, "national": 0.22, "international": 0.08}
LEVEL_RANK_ORDER = {"regional": 0, "interregional": 1, "national": 2, "international": 3}


def load_config(path: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or HERE / "config.yaml").read_text(encoding="utf-8"))


def load_heroes() -> dict[str, dict[str, Any]]:
    out = {}
    for f in sorted((HERE / "heroes").glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        out[data["key"]] = data
    return out


def _load_synth() -> Any:
    name = "synth"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools/synth/synth.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses ищут модуль по имени
    spec.loader.exec_module(mod)
    return mod


@functools.lru_cache(maxsize=1)
def skill_names() -> dict[str, tuple[str, str]]:
    """slug → (название, kind) из data/taxonomy/skills.yaml."""
    data = yaml.safe_load((ROOT / "data/taxonomy/skills.yaml").read_text(encoding="utf-8"))
    return {s["slug"]: (s["name"], s["kind"]) for s in data["skills"]}


def stable_id(*parts: object) -> uuid.UUID:
    """Детерминированный UUID факта: повторный запуск сидера даёт те же ключи."""
    return uuid.uuid5(SEED_NS, "|".join(str(p) for p in parts))


def _weighted(rng: random.Random, weights: dict[str, float]) -> str:
    keys = sorted(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


def _round_k(value: float, step: int = 5000) -> int:
    return max(step, int(round(value / step)) * step)


# ---------------------------------------------------------------------------------- ФСП
def _competitions(
    cfg: dict[str, Any], heroes: dict[str, Any], rng: random.Random, anchor: date
) -> list[dict[str, Any]]:
    fixed: dict[str, dict[str, Any]] = {}
    for h in heroes.values():
        for c in (h.get("fsp") or {}).get("competitions", []):
            end = anchor - timedelta(days=int(c["end_days_ago"]))
            fixed[c["id"]] = {
                "id": c["id"],
                "title": c["title"],
                "discipline": c["discipline"],
                "level": c["level"],
                "format": c["format"],
                "region": c.get("region"),
                "start_date": (end - timedelta(days=2)).isoformat(),
                "end_date": end.isoformat(),
                "status": c.get("status", "finished"),
                "tracks": list(c.get("tracks", [])),
                "registration_url": None,
            }
    n_past = int(cfg["counts"]["fsp_past_competitions"])
    cities = list(cfg["cities"])
    out: list[dict[str, Any]] = []
    for i in range(1, n_past + 1):
        cid = f"c-{i:03d}"
        if cid in fixed:
            out.append(fixed[cid])
            continue
        disc = _weighted(rng, DISCIPLINE_WEIGHTS)
        level = _weighted(rng, LEVEL_WEIGHTS)
        end = anchor - timedelta(days=rng.randint(21, 1095))
        year = end.year
        out.append(
            {
                "id": cid,
                "title": f"{LEVEL_TITLES[level].capitalize()} по {DISCIPLINE_TITLES[disc]}, "
                f"{year}, №{i} (вымышленный)",
                "discipline": disc,
                "level": level,
                "format": rng.choice(["online", "offline"]),
                "region": rng.choice(cities) if rng.random() < 0.6 else None,
                "start_date": (end - timedelta(days=rng.randint(1, 3))).isoformat(),
                "end_date": end.isoformat(),
                "status": "finished",
                "tracks": ["web", "ml"] if disc == "product" else [],
                "registration_url": None,
            }
        )
    for j in range(int(cfg["counts"]["fsp_upcoming"])):
        disc = _weighted(rng, DISCIPLINE_WEIGHTS)
        start = anchor + timedelta(days=rng.randint(10, 150))
        cid = f"c-{101 + j}"
        out.append(
            {
                "id": cid,
                "title": f"Предстоящий этап по {DISCIPLINE_TITLES[disc]}, №{j + 1} (вымышленный)",
                "discipline": disc,
                "level": _weighted(rng, LEVEL_WEIGHTS),
                "format": rng.choice(["online", "offline"]),
                "region": rng.choice(cities),
                "start_date": start.isoformat(),
                "end_date": (start + timedelta(days=2)).isoformat(),
                "status": "registration" if j % 2 == 0 else "announced",
                "tracks": ["web", "ml"] if disc == "product" else [],
                "registration_url": f"https://fsp.example.test/events/{cid}",
            }
        )
    return out


class _Fsp:
    """Сборка участников, команд и результатов мока одним rng."""

    def __init__(self, cfg: dict[str, Any], rng: random.Random, comps: list[dict[str, Any]]):
        self.cfg, self.rng = cfg, rng
        self.comps = {c["id"]: c for c in comps}
        self.past = [c for c in comps if c["status"] == "finished"]
        self.participants: dict[str, dict[str, Any]] = {}
        self.results: dict[str, list[dict[str, Any]]] = {}
        self.teams: dict[str, dict[str, Any]] = {}
        self._pool: list[str] = []  # участники без аккаунта на платформе (наполнители команд)
        self._busy: set[tuple[str, str]] = set()  # (participant, competition) уже занято
        self._team_seq = 0

    def person(self, pid: str, n: int, *, linked: bool) -> dict[str, Any]:
        rng, cfg = self.rng, self.cfg
        female = rng.random() < 0.38
        last = rng.choice(cfg["last_names_m"]) + ("а" if female else "")
        first = rng.choice(cfg["first_names_f" if female else "first_names_m"])
        city = rng.choice(cfg["cities"])
        p = {
            "id": pid,
            "last_name": last,
            "first_name": first,
            "middle_name": None,
            "birth_year": rng.randint(1986, 2007),
            "region": cfg["regions"][city],
            "email": cfg["demo"]["participant_email"].format(n=n),
            "phone": f"+7900{rng.randint(1000000, 9999999)}",
            "ranks": [],
        }
        self.participants[pid] = p
        self.results.setdefault(pid, [])
        if not linked:
            self._pool.append(pid)
        return p

    def add_result(self, pid: str, comp_id: str, **kw: Any) -> bool:
        if (pid, comp_id) in self._busy:
            return False
        self._busy.add((pid, comp_id))
        c = self.comps[comp_id]
        row = {
            "competition_id": comp_id,
            "discipline": c["discipline"],
            "stage": "final",
            "team_id": None,
            "team_role": "individual",
            "place": None,
            "participants_total": None,
            "score": None,
            "track": None,
            "date": c["end_date"],
        }
        row.update(kw)
        self.results[pid].append(row)
        return True

    def filler(self, comp_id: str) -> str | None:
        for _ in range(30):
            pid = self.rng.choice(self._pool)
            if (pid, comp_id) not in self._busy:
                return pid
        return None

    def new_team(self, comp_id: str, members: list[tuple[str, str]], **res: Any) -> str:
        self._team_seq += 1
        tid = f"t-{self._team_seq:04d}"
        names = [
            "Северный ветер",
            "Кодовый замок",
            "Тихий омут",
            "Белая сова",
            "Горный ручей",
            "Рыжий лис",
            "Каменный цветок",
            "Бегущий по волнам",
            "Железный бор",
            "Синий кит",
        ]
        self.teams[tid] = {
            "id": tid,
            "name": f"{self.rng.choice(names)} {self._team_seq}",
            "competition_id": comp_id,
            "members": [{"participant_id": p, "role": r} for p, r in members],
        }
        for pid, role in members:
            self.add_result(pid, comp_id, team_id=tid, team_role=role, **res)
        return tid


def _best_rank(entries: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Разряд по лучшему месту в процентилях (правила ФСП — предположение до ответа)."""
    best = None
    for e in entries:
        if e["place"] is None or not e["participants_total"]:
            continue
        pct = e["place"] / e["participants_total"]
        lvl = LEVEL_RANK_ORDER[e["level"]]
        score = lvl * 2 + (2 if pct <= 0.1 else 1 if pct <= 0.3 else 0)
        if best is None or score > best[0]:
            best = (score, e)
    if best is None or best[0] < 3:
        return None
    s, e = best
    rank = "cms" if s >= 8 else "rank_1" if s >= 6 else "rank_2" if s >= 5 else "rank_3"
    return e["discipline"], rank + "|" + e["date"]


# ------------------------------------------------------------------------------ главная функция
def build_plan(
    seed: int | None = None,
    anchor: date | None = None,
    counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    if counts:
        cfg["counts"].update(counts)
    seed = int(cfg["seed"] if seed is None else seed)
    anchor = anchor or date.today()
    rng = random.Random(seed)
    heroes = load_heroes()
    names = skill_names()
    n_c = int(cfg["counts"]["candidates"])
    n_v = int(cfg["counts"]["vacancies"])
    n_co = int(cfg["counts"]["companies"])

    synth = _load_synth()
    market = synth.generate_market(seed=seed, n_candidates=n_c, n_vacancies=max(n_v, 1) + 10)

    comps = _competitions(cfg, heroes, rng, anchor)
    fsp = _Fsp(cfg, rng, comps)
    past_by_dl: dict[tuple[str, str], list[str]] = {}
    past_by_d: dict[str, list[str]] = {}
    for c in fsp.past:
        past_by_dl.setdefault((c["discipline"], c["level"]), []).append(c["id"])
        past_by_d.setdefault(c["discipline"], []).append(c["id"])

    # --- герои ФСП: участники, команда, результаты (фикстуры вручную)
    for h in heroes.values():
        f = h.get("fsp")
        if not f:
            continue
        p = dict(f["participant"])
        p.setdefault("middle_name", None)
        p["ranks"] = [
            {
                "discipline": r["discipline"],
                "rank": r["rank"],
                "assigned_at": (anchor - timedelta(days=int(r["days_ago"]))).isoformat(),
            }
            for r in p.get("ranks", [])
        ]
        fsp.participants[p["id"]] = p
        fsp.results[p["id"]] = []
        for t in f.get("teammates", []):
            fsp.participants[t["id"]] = {
                "middle_name": None,
                "phone": "+79001112233",
                "ranks": [],
                **t,
            }
            fsp.results[t["id"]] = []
        if "team" in f:
            fsp.teams[f["team"]["id"]] = {**f["team"]}
    for h in heroes.values():
        f = h.get("fsp")
        if not f:
            continue
        for r in f.get("results", []):
            fsp.add_result(
                f["participant"]["id"],
                r["competition_id"],
                **{k: v for k, v in r.items() if k != "competition_id"},
            )
        for r in f.get("teammate_results", []):
            for m in fsp_team_mates(f):
                fsp.add_result(
                    m,
                    r["competition_id"],
                    team_role="member",
                    **{k: v for k, v in r.items() if k != "competition_id"},
                )

    # --- кандидаты из синтетического рынка
    cand_rows: list[dict[str, Any]] = []
    linked_ix: list[int] = []
    for i, sc in enumerate(market.candidates[:n_c]):
        obs = sc["observed"]
        n = i + 1
        linked = bool(obs.get("fsp"))
        cand_rows.append(
            {
                "key": f"cand-{n:04d}",
                "n": n,
                "email": cfg["demo"]["candidate_email"].format(n=n),
                "hero": None,
                "obs": obs,
                "linked": linked,
            }
        )
        if linked:
            linked_ix.append(i)

    # участники для привязанных кандидатов
    hero_count = len(fsp.participants)
    target = int(cfg["counts"]["fsp_participants"])
    # сначала наполнители (чтобы было кого класть в команды), потом привязанные
    n_fillers = max(target - hero_count - len(linked_ix), 20)
    for k in range(1, n_fillers + 1):
        fsp.person(f"p-f{k:04d}", 1000 + k, linked=False)
    for i in linked_ix:
        row = cand_rows[i]
        row["participant_id"] = f"p-{row['n']:04d}"
        fsp.person(row["participant_id"], row["n"], linked=True)

    for i in linked_ix:
        row = cand_rows[i]
        pid = row["participant_id"]
        entries = []
        for e in row["obs"]["fsp"]:
            pool = past_by_dl.get((e["discipline"], e["level"])) or past_by_d.get(e["discipline"])
            if not pool:
                continue
            cid = rng.choice(pool)
            total = max(int(e["participants"]), 2)
            place = max(1, min(int(e["place"]), total))
            stage = "qualifier" if rng.random() < 0.2 else "final"
            res = {
                "place": place,
                "participants_total": total,
                "score": round(rng.uniform(20, 100), 1),
                "track": rng.choice(["web", "ml"]) if e["discipline"] == "product" else None,
                "stage": stage,
            }
            comp = fsp.comps[cid]
            if e["discipline"] in TEAM_DISCIPLINES:
                f1, f2 = fsp.filler(cid), fsp.filler(cid)
                if f1 is None or f2 is None or (pid, cid) in fsp._busy or f1 == f2:
                    continue
                role = "captain" if e.get("captain") else "member"
                mates = [
                    (pid, role),
                    (f1, "member" if role == "captain" else "captain"),
                    (f2, "member"),
                ]
                tid = fsp.new_team(cid, mates, **res)
                entry_team = tid
            else:
                if not fsp.add_result(pid, cid, team_role="individual", **res):
                    continue
                entry_team = None
            entries.append(
                {
                    "competition_id": cid,
                    "discipline": e["discipline"],
                    "level": comp["level"],
                    "date": comp["end_date"],
                    "place": place,
                    "participants_total": total,
                    "team_id": entry_team,
                }
            )
        rk = _best_rank(entries)
        if rk is not None:
            disc, packed = rk
            rank, dt = packed.split("|")
            fsp.participants[pid]["ranks"].append(
                {"discipline": disc, "rank": rank, "assigned_at": dt}
            )

    # остальные участники: 1–3 результата, команды по тройкам в командных дисциплинах
    fillers = [p for p in fsp.participants if p.startswith("p-f")]
    rng.shuffle(fillers)
    for pid in fillers:
        for _ in range(rng.randint(1, 3)):
            c = rng.choice(fsp.past)
            if c["discipline"] in TEAM_DISCIPLINES:
                continue  # командные результаты наполнителей — только через команды выше
            total = rng.choice([40, 60, 80, 120, 160])
            fsp.add_result(
                pid,
                c["id"],
                team_role="individual",
                place=rng.randint(1, total),
                participants_total=total,
                score=round(rng.uniform(1, 100), 1),
            )
    for c in fsp.past:
        if c["discipline"] not in TEAM_DISCIPLINES:
            continue
        free = [p for p in fillers if (p, c["id"]) not in fsp._busy]
        rng.shuffle(free)
        for k in range(0, min(len(free) // 3, 5) * 3, 3):
            trio = free[k : k + 3]
            total = rng.choice([30, 40, 60])
            fsp.new_team(
                c["id"],
                [(trio[0], "captain"), (trio[1], "member"), (trio[2], "member")],
                place=rng.randint(1, total),
                participants_total=total,
                score=round(rng.uniform(10, 95), 1),
                track=rng.choice(["web", "ml"]),
            )

    # --- кандидаты: резюме, доказательства, анкета
    candidates: list[dict[str, Any]] = []
    for row in cand_rows:
        candidates.append(_candidate(cfg, rng, names, anchor, row))
    # герои-кандидаты идут первыми
    hero_candidates = [
        _hero_candidate(cfg, anchor, h) for h in heroes.values() if h["role"] == "candidate"
    ]
    candidates = hero_candidates + candidates

    # --- компании и вакансии
    companies, vacancies = _market_side(cfg, rng, anchor, heroes, market, n_co, n_v)

    # --- план офферов и аналитики
    offers = _offer_plan(cfg, rng, int(cfg["counts"]["offers"]))
    analytics = _analytics_plan(cfg, rng, candidates, companies)

    plan = {
        "seed": seed,
        "anchor": anchor.isoformat(),
        "candidates": candidates,
        "companies": companies,
        "vacancies": vacancies,
        "offers": offers,
        "analytics": analytics,
        "provisional_skills": [list(x) for x in cfg["provisional_skills"]],
        "fsp": {
            "competitions": sorted(comps, key=lambda c: c["id"]),
            "participants": [fsp.participants[k] for k in sorted(fsp.participants)],
            "teams": [fsp.teams[k] for k in sorted(fsp.teams)],
            "results": {k: fsp.results[k] for k in sorted(fsp.results)},
        },
    }
    plan["hash"] = plan_hash(plan)
    return plan


def fsp_team_mates(f: dict[str, Any]) -> list[str]:
    return [m["participant_id"] for m in f["team"]["members"] if m["role"] != "captain"]


def plan_hash(plan: dict[str, Any]) -> str:
    body = {k: v for k, v in plan.items() if k != "hash"}
    blob = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# --------------------------------------------------------------------------- кандидаты
def _month(anchor: date, months_ago: int) -> str:
    y, m = anchor.year, anchor.month - months_ago
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _candidate(
    cfg: dict[str, Any],
    rng: random.Random,
    names: dict[str, tuple[str, str]],
    anchor: date,
    row: dict[str, Any],
) -> dict[str, Any]:
    obs = row["obs"]
    key = row["key"]
    city = rng.choice(cfg["cities"])
    wf = obs.get("work_format") or "hybrid"
    formats = sorted({wf, *(["remote"] if rng.random() < 0.3 else [])})
    skills = [s for s in obs["resume"]["skills"] if s in names]
    months = int(obs["resume"].get("experience_months") or 0)

    experience: list[dict[str, Any]] = []
    if months >= 3 and skills:
        n_jobs = 1 if months < 18 else rng.randint(1, 3)
        cuts = sorted(rng.sample(range(1, months), n_jobs - 1)) if n_jobs > 1 else []
        bounds = [0, *cuts, months]
        firms = [c["name"] for c in cfg["companies"]]
        for j in range(n_jobs):
            start_ago = months - bounds[j]
            end_ago = months - bounds[j + 1]
            job_skills = sorted(rng.sample(skills, min(len(skills), rng.randint(2, 6))))
            experience.append(
                {
                    "company": rng.choice(firms),
                    "title": cfg["role_titles"].get(obs["role"], "Разработчик"),
                    "start": _month(anchor, start_ago),
                    "end": None
                    if (j == n_jobs - 1 and rng.random() < 0.7)
                    else _month(anchor, end_ago),
                    "description": "Разработка и поддержка сервисов команды.",
                    "skills": job_skills,
                    "is_commercial": True,
                }
            )
    evidence: list[dict[str, Any]] = []
    # GitHub (синтетический анализ): 0.6 · авторство · зрелость · объём, ×0.5 при признаках подделки
    best: dict[str, dict[str, Any]] = {}
    for r in obs.get("github") or []:
        loc = rng.randint(300, 6000)
        maturity = round(rng.uniform(0.6, 1.0), 2)
        volume = min(1.0, loc / 2000) ** 0.5
        base = 0.6 * float(r["authorship_share"]) * maturity * volume * (0.5 if r["fake"] else 1.0)
        for t in r["technologies"]:
            if t not in names or names[t][1] != "hard":
                continue
            s = round(min(base, 0.6), 3)
            if s >= 0.05 and (t not in best or s > best[t]["strength"]):
                best[t] = {
                    "skill": t,
                    "source": "github",
                    "strength": s,
                    "days_ago": rng.randint(20, 500),
                    "fact": f"{key}/{r['repo']}",
                    "details": {"demo": True, "red_flag": bool(r["fake"])},
                }
    evidence += [best[k] for k in sorted(best)]
    for t in obs.get("tests") or []:
        if t["skill"] not in names or names[t["skill"]][1] != "hard" or not t["answers"]:
            continue
        frac = sum(1 for a in t["answers"] if a["correct"]) / len(t["answers"])
        strength = round(min(0.8, max(0.3, 0.45 + 0.12 * 3 * frac)), 3)
        evidence.append(
            {
                "skill": t["skill"],
                "source": "test",
                "strength": strength,
                "days_ago": rng.randint(10, 300),
                "fact": f"{key}/test-{t['skill']}",
                "details": {"demo": True, "correct_share": round(frac, 2)},
            }
        )

    status = _weighted(rng, {"active": 0.25, "open": 0.6, "dnd": 0.15})
    consents = ["pd_processing", "profile_publication"]
    if row["linked"]:
        consents.append("fsp_data")
    if best:
        consents.append("code_analysis")
    fsp_block = None
    if row["linked"]:
        fsp_block = {"participant_id": row["participant_id"]}
    return {
        "key": key,
        "hero": None,
        "email": row["email"],
        "profile": {
            "city": city,
            "relocation": rng.random() < 0.15,
            "salary_min": _round_k(float(obs.get("salary_expectation") or 100000), 5000),
            "formats": formats,
            "employment_types": ["full"] + (["part"] if rng.random() < 0.1 else []),
            "search_status": status,
        },
        "consents": consents,
        "resume": {
            "summary": (
                f"{cfg['role_titles'].get(obs['role'], 'Разработчик')}, {months // 12} г. опыта."
            ),
            "skills": skills,
            "experience": experience,
            "education": [
                {
                    "institution": "Технический университет (вымышленный)",
                    "degree": "bachelor",
                    "field": "Информатика",
                    "year_end": anchor.year - max(0, months // 12) - rng.randint(0, 2),
                }
            ]
            if months >= 12
            else [],
            "total_months": months,
        },
        "evidence": evidence,
        "fsp": fsp_block,
        "role": obs["role"],
    }


def _hero_candidate(cfg: dict[str, Any], anchor: date, h: dict[str, Any]) -> dict[str, Any]:
    r = h["resume"]
    experience = []
    total = 0
    for e in r.get("experience", []):
        total += int(e["start_months_ago"]) - int(e["end_months_ago"] or 0)
        experience.append(
            {
                "company": e["company"],
                "title": e["title"],
                "start": _month(anchor, int(e["start_months_ago"])),
                "end": None
                if e["end_months_ago"] is None
                else _month(anchor, int(e["end_months_ago"])),
                "description": e.get("description"),
                "skills": list(e["skills"]),
                "is_commercial": True,
            }
        )
    evidence = [
        {
            "skill": e["skill"],
            "source": e["source"],
            "strength": e["strength"],
            "days_ago": e["days_ago"],
            "fact": f"{h['key']}/{e['fact']}",
            "details": {"demo": True},
        }
        for e in h.get("evidence", [])
    ]
    return {
        "key": f"hero-{h['key']}",
        "hero": h["key"],
        "email": h["email"],
        "profile": dict(h["profile"]),
        "consents": list(h["consents"]),
        "resume": {
            "summary": r.get("summary"),
            "skills": list(r["skills"]),
            "experience": experience,
            "education": list(r.get("education", [])),
            "total_months": total,
        },
        "evidence": evidence,
        "fsp": None,  # герои привязываются к ФСП в ходе демо
        "role": "backend",
    }


# ------------------------------------------------------------------- компании и вакансии
def _market_side(
    cfg: dict[str, Any],
    rng: random.Random,
    anchor: date,
    heroes: dict[str, Any],
    market: Any,
    n_co: int,
    n_v: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pending = int(cfg["counts"]["companies_pending"])
    templates = cfg["companies"]
    companies = []
    for i in range(n_co):
        t = templates[i % len(templates)]
        name = t["name"] if i < len(templates) else f"{t['name']} {i}"
        is_pending = i >= n_co - pending
        companies.append(
            {
                "idx": i,
                "name": name,
                "site": t["site"],
                "about": t["about"],
                "inn": f"77{rng.randint(10**7, 10**8 - 1)}",
                "email": cfg["demo"]["employer_email"].format(n=i + 1),
                "status": "pending" if is_pending else "verified",
                "responsibility_score": None if is_pending else round(rng.uniform(3.2, 4.9), 1),
            }
        )
    olga = heroes.get("olga")
    if olga:
        companies[0]["email"] = olga["email"]
        companies[0]["responsibility_score"] = olga["responsibility_score"]
        companies[0]["hero"] = "olga"
    verified = [c["idx"] for c in companies if c["status"] == "verified"]

    vacancies: list[dict[str, Any]] = []
    if olga:
        v = olga["vacancy"]
        vacancies.append(
            {
                "company_idx": 0,
                "hero": True,
                "title": v["title"],
                "role": v["role"],
                "grade_min": v["grade_min"],
                "grade_max": v["grade_max"],
                "formats": list(v["formats"]),
                "employment_type": v["employment_type"],
                "city": v["city"],
                "salary_from": v["salary_from"],
                "salary_to": v["salary_to"],
                "description": v["description"],
                "required": list(v["skills"]["required"]),
                "nice": list(v["skills"]["nice"]),
                "status": "published",
                "flavor": "normal",
            }
        )
    names = skill_names()
    n_gen = n_v - len(vacancies)
    closed = int(cfg["counts"]["vacancies_closed"])
    for k, sv in enumerate(market.vacancies[:n_gen]):
        cidx = verified[(k + 1) % len(verified)]
        lo, hi = _round_k(sv["salary_min"]), _round_k(sv["salary_max"])
        flavor = "normal"
        if k % 20 == 3:  # намеренно широкая вилка (подсказка «сузить»)
            hi, flavor = _round_k(lo * 2.0), "wide"
        elif k % 20 == 11:  # вилка ниже рынка (подсказка «поднять»)
            lo, hi, flavor = _round_k(lo * 0.5), _round_k(hi * 0.55), "below_market"
        hi = max(hi, lo)
        gmin, gmax = sv["grade_min"], sv["grade_max"]
        rt = cfg["role_titles"].get(sv["role"], "Разработчик")
        gt = cfg["grade_titles"]
        title = f"{rt} ({gt[gmin]}" + (f"–{gt[gmax]})" if gmax != gmin else ")")
        fmt = sv["work_format"]
        required = [s for s in sv["must_skills"] if s in names]
        nice = [s for s in sv["nice_skills"] if s in names and s not in required]
        vacancies.append(
            {
                "company_idx": cidx,
                "hero": False,
                "title": title,
                "role": sv["role"],
                "grade_min": gmin,
                "grade_max": gmax,
                "formats": [fmt],
                "employment_type": "full",
                "city": None if fmt == "remote" else rng.choice(cfg["cities"]),
                "salary_from": lo,
                "salary_to": hi,
                "description": f"{title}: команда {companies[cidx]['name']}, "
                f"задачи по направлению «{rt}».",
                "required": required[: 2 + k % 2],
                "nice": nice[:4],
                "min_level": 2 if k % 5 == 0 else 1,
                "status": "closed" if k >= n_gen - closed else "published",
                "flavor": flavor,
            }
        )
    return companies, vacancies


# ---------------------------------------------------------------------- офферы и аналитика
def _offer_plan(cfg: dict[str, Any], rng: random.Random, n: int) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        outcome = _weighted(rng, cfg["offer_outcomes"])
        fresh = outcome in ("viewed", "sent")
        days_ago = rng.randint(0, 5) if fresh else rng.randint(2 if outcome != "expired" else 9, 85)
        if outcome in ("sent", "viewed"):
            respond = None
        elif outcome == "expired":
            respond = None
        else:
            respond = rng.randint(1, 120)  # часов до ответа, меньше срока действия (7 суток)
        # accepted/interview/... требуют ответа до «сейчас»
        if respond is not None:
            days_ago = max(days_ago, respond // 24 + 1)
        out.append(
            {
                "i": i,
                "outcome": outcome,
                "decline_reason": _weighted(rng, cfg["decline_reasons"])
                if outcome == "declined"
                else None,
                "days_ago": days_ago,
                "hour": rng.randint(8, 19),
                "respond_hours": respond,
            }
        )
    return out


def _analytics_plan(
    cfg: dict[str, Any],
    rng: random.Random,
    candidates: list[dict[str, Any]],
    companies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Бэкфилл событий за N дней (metrics.md §2): регистрации, резюме, привязки ФСП."""
    days = int(cfg["counts"]["analytics_days"])
    out = []
    pool = [c for c in candidates if not c["hero"]]
    for c in pool:
        d = rng.randint(0, days - 1)
        out.append(
            {
                "event": "signup_completed",
                "subject": c["key"],
                "role": "candidate",
                "days_ago": d,
                "hour": rng.randint(7, 23),
                "props": {
                    "channel": rng.choice(["web", "tg"]),
                    "method": rng.choice(["email", "tg"]),
                },
            }
        )
        if c["resume"]["skills"]:
            out.append(
                {
                    "event": "resume_confirmed",
                    "subject": c["key"],
                    "role": "candidate",
                    "days_ago": d,
                    "hour": rng.randint(7, 23),
                    "props": {},
                }
            )
        if c["fsp"]:
            out.append(
                {
                    "event": "fsp_link_completed",
                    "subject": c["key"],
                    "role": "candidate",
                    "days_ago": d,
                    "hour": rng.randint(7, 23),
                    "props": {"method": rng.choice(["oauth", "code"]), "verified": True},
                }
            )
    return out
