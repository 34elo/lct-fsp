"""Офлайн-конвейер LLM-заданий (E26-4, ADR-024, assessment.md §7): генератор → решатель → черновик
ключа → автопроверки → `draft` в очереди допуска; прогон нашей LLM как кандидата → `ai_solvable`.

В LLM core напрямую не ходит: только ml-api (`/v1/families/generate`, `/solve`, `/key-draft`), по
одному запросу за раз (одна GPU). `LLM_ENABLED=false` или пустой `ML_API_URL` — конвейер ничего не
предлагает и `ai_solvable` не трогает: банк растёт процедурными генераторами, майнингом и
конструктором. При `ML_FAKE=true` на стороне ml работают детерминированные заглушки.

Путь предложения: форма генератора → `FamilySpec` (схема конструктора) → навык есть в справочнике
→ ключ (генератора или черновик ml-api) → автопроверка конструктора на 200 сидах → строка
`families` (`source = llm`, `status = draft`, `key_status = draft`). Второе мнение — черновик ключа
и решатель на тех же вариантах — не отбраковывает, а пишется флагами в `spec.llm.flags` для админа.
Дальше всё как у конструктора: админ утверждает ключ (`POST /admin/families/{id}/key`) и переводит в
пилот (`POST /admin/families/{id}/pilot`), в `active` — только по статистике пилота (E22-9).

`ai_solvable` = средний балл LLM-«кандидата» на `k` вариантах семейства (свои сиды, не боевые),
считается своим же `score` семейства. Повторный прогон перезаписывает значение — идемпотентно.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
import structlog
from fsp_contracts.ml import (
    FamilyGenerateRequest,
    FamilyGenerateResponse,
    FamilyKeyDraft,
    FamilyKind,
    FamilySolveAnswer,
    FamilySolveRequest,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import constructor, key_draft
from app.assessment.attempts import family_of
from app.assessment.config import AssessmentConfig
from app.assessment.families import check
from app.assessment.families.base import Family, Kind
from app.assessment.families.spec import FamilySpec, SpecError, SpecFamily
from app.assessment.models import FamilyRow
from app.config import Settings
from app.taxonomy import service as taxonomy

log = structlog.get_logger()
NAMESPACE = uuid.UUID("0c4f9a62-26e4-4b7e-9d1a-6c6c6d62616e")
SOURCE = "llm"
SOLVE_K = 5
KINDS = [k.value for k in Kind]
REPORT_TOP = 10


def solve_seeds(k: int) -> list[int]:
    """Сиды прогона LLM-«кандидата»: не совпадают с `check.seeds` и не зависят от кандидатов."""
    return [(i * 6_364_136_223_846_793_005 + 1_442_695_040_888_963_407) % 2**63 for i in range(k)]


# --- клиент ml-api ----------------------------------------------------------------------------


class Bank(Protocol):
    """Источник LLM-ответов. `None` — модель недоступна (конвейер это переживает)."""

    async def generate(self, req: FamilyGenerateRequest) -> FamilyGenerateResponse | None: ...

    async def solve(self, req: FamilySolveRequest) -> FamilySolveAnswer | None: ...

    async def key_draft(self, spec: FamilySpec) -> FamilyKeyDraft | None: ...


class HttpBank:
    """ml-api по HTTP, последовательно. Ошибка ml-api → `None` и предупреждение в лог."""

    def __init__(
        self,
        settings: Settings,
        *,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.available = bool(settings.llm_enabled and settings.ml_api_url)
        self._client = httpx.AsyncClient(
            base_url=settings.ml_api_url or "http://ml-api.invalid",
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any] | None:
        if not self.available:
            return None
        try:
            resp = await self._client.post(path, json=body)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("llm_bank_ml_unavailable", path=path, error=type(e).__name__)
            return None

    async def generate(self, req: FamilyGenerateRequest) -> FamilyGenerateResponse | None:
        data = await self._post("/v1/families/generate", req.model_dump(mode="json"))
        return _parse(FamilyGenerateResponse, data)

    async def solve(self, req: FamilySolveRequest) -> FamilySolveAnswer | None:
        data = await self._post("/v1/families/solve", req.model_dump(mode="json"))
        return _parse(FamilySolveAnswer, data)

    async def key_draft(self, spec: FamilySpec) -> FamilyKeyDraft | None:
        try:
            body = key_draft.example_request(spec)
        except SpecError:
            return None
        d = _parse(FamilyKeyDraft, await self._post("/v1/families/key-draft", body.model_dump()))
        return d if d is not None and key_draft.fits(spec, d) else None


def _parse(model, data):  # noqa: ANN001, ANN202 — маленький помощник для трёх DTO
    if data is None:
        return None
    try:
        return model.model_validate(data)
    except ValidationError:
        log.warning("llm_bank_bad_response", model=model.__name__)
        return None


# --- проверки (чистые функции) ----------------------------------------------------------------


def digest(spec: FamilySpec) -> str:
    """Отпечаток формы без названия: одинаковые предложения генератора не дублируются."""
    body = spec.model_dump(mode="json", exclude={"title"})
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _ranks(xs: Sequence[float]) -> list[int]:
    return sorted(range(len(xs)), key=lambda i: -xs[i])


def key_agrees(spec: FamilySpec, fam: SpecFamily, draft: FamilyKeyDraft | None) -> bool | None:
    """Совпадает ли ключ генератора с независимым черновиком ключа. `None` — сравнить нечем."""
    if draft is None or spec.missing_key():
        return None
    match spec.kind:
        case Kind.choice:
            return draft.correct == spec.correct
        case Kind.find_bug:
            return set(draft.bug_lines or []) == set(spec.bug_lines or [])
        case Kind.sjt:
            mine = [a.score or 0.0 for a in spec.actions or []]
            return draft.scores is not None and _ranks(draft.scores) == _ranks(mine)
        case Kind.exact | Kind.estimate:
            if draft.answer is None:
                return None
            item = check.build(fam, key_draft.EXAMPLE_SEED)  # тот же вариант, что видел черновик
            return fam.score(item, draft.answer) >= 1.0
    return None


async def solver_score(bank: Bank, fam: Family, k: int) -> float | None:
    """Средний балл LLM-«кандидата» на `k` вариантах; `None` — модель не ответила."""
    if fam.kind == Kind.open:
        return None
    scores: list[float] = []
    for seed in solve_seeds(k):
        item = check.build(fam, seed)
        pub = item.public()
        ans = await bank.solve(
            FamilySolveRequest(kind=pub["kind"], stem=pub["stem"], options=pub["options"] or [])
        )
        if ans is None:
            return None
        scores.append(fam.score(item, ans.answer))
    return round(sum(scores) / len(scores), 3) if scores else None


# --- конвейер ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    skill: str
    kind: FamilyKind
    level: int
    n: int = 1
    domain: str | None = None


@dataclass
class Report:
    llm_available: bool = True
    proposed: int = 0
    passed: int = 0
    rejected: Counter = field(default_factory=Counter)
    flags: Counter = field(default_factory=Counter)
    created: list[str] = field(default_factory=list)
    in_pilot: int = 0  # семейства `source = llm` в pilot или active (всего в банке)
    in_draft: int = 0
    ai_measured: int = 0
    ai_skipped: int = 0
    ai_mean: float | None = None
    ai_top: list[dict[str, Any]] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["rejected"], d["flags"] = dict(self.rejected), dict(self.flags)
        return d

    def markdown(self) -> str:
        lines = [
            "# Офлайн-конвейер LLM-заданий (E26-4)",
            "",
            f"LLM доступна: {'да' if self.llm_available else 'нет (LLM_ENABLED=false/ML_API_URL)'}",
            "",
            f"**{self.proposed} предложено → {self.passed} прошло автопроверки → "
            f"{self.in_pilot} в пилоте** (в черновиках `source = llm`: {self.in_draft})",
            "",
        ]
        if self.rejected:
            lines += ["Отбраковано:", ""]
            lines += [f"- `{k}`: {v}" for k, v in sorted(self.rejected.items())]
            lines.append("")
        if self.flags:
            lines += ["Флаги для админа (не отбраковка):", ""]
            lines += [f"- `{k}`: {v}" for k, v in sorted(self.flags.items())]
            lines.append("")
        mean = "—" if self.ai_mean is None else f"{self.ai_mean:.3f}"
        lines += [
            f"`ai_solvable`: измерено {self.ai_measured}, пропущено {self.ai_skipped}, "
            f"среднее {mean}",
        ]
        if self.ai_top:
            lines += ["", "| семейство | статус | kind | ai_solvable |", "|---|---|---|---|"]
            lines += [
                f"| `{t['slug']}` | {t['status']} | {t['kind']} | {t['ai_solvable']:.2f} |"
                for t in self.ai_top
            ]
        return "\n".join(lines) + "\n"


def _reject(report: Report, reason: str, target: Target, detail: str = "") -> None:
    report.rejected[reason] += 1
    log.info("llm_bank_rejected", reason=reason, skill=target.skill, kind=target.kind, d=detail)


async def propose(
    session: AsyncSession,
    bank: Bank,
    cfg: AssessmentConfig,
    targets: Iterable[Target],
    *,
    k: int = SOLVE_K,
    report: Report | None = None,
) -> Report:
    """Генератор → проверки → `draft`. Не делает `commit`."""
    report = report or Report()
    for t in targets:
        gen = await bank.generate(
            FamilyGenerateRequest(
                skill=t.skill,
                kind=t.kind,
                level=t.level,
                n=t.n,
                domain=t.domain,
                skill_type=(await _skill_type(session, t.skill)) or "",
            )
        )
        if gen is None:
            report.llm_available = False
            continue
        for raw in gen.specs:
            report.proposed += 1
            await _one(session, bank, cfg, t, raw, gen.model, k, report)
    await session.flush()
    return report


async def _skill_type(session: AsyncSession, skill: str) -> str | None:
    types = await taxonomy.skill_types_of(session, [skill])
    return types[skill].value if skill in types else None


async def _one(
    session: AsyncSession,
    bank: Bank,
    cfg: AssessmentConfig,
    t: Target,
    raw: dict[str, Any],
    model: str,
    k: int,
    report: Report,
) -> None:
    raw = {**raw, "skill": t.skill, "level": t.level}  # навык и уровень задаёт заказ, не генератор
    if raw.get("kind") != t.kind:
        return _reject(report, "kind_mismatch", t)
    try:
        spec = FamilySpec.model_validate(raw)
    except ValidationError as e:
        return _reject(report, "schema", t, str(e.errors()[:1]))
    skill_type = await _skill_type(session, t.skill)
    if skill_type is None:
        return _reject(report, "unknown_skill", t)
    d = digest(spec)
    slug = f"llm-{d[:12]}"
    if await session.scalar(select(FamilyRow.id).where(FamilyRow.slug == slug)):
        return _reject(report, "duplicate", t)

    draft = await bank.key_draft(spec) if spec.kind != Kind.order else None
    form = spec
    if spec.missing_key():
        if draft is None:
            return _reject(report, "no_key", t)
        form = key_draft.apply(spec, draft)
    fam = SpecFamily(form, slug=slug, skill_type=skill_type)
    errs = constructor.autocheck(fam)
    if errs:
        return _reject(report, "autocheck", t, errs[0])

    flags: list[str] = []
    agree = key_agrees(spec, fam, draft)
    if agree is False:
        flags.append("key_draft_disagrees")
    if spec.missing_key():
        flags.append("key_from_draft")
    solved = await solver_score(bank, fam, k)
    if solved is not None and solved == 0.0 and agree is False:
        flags.append("key_doubtful")  # и черновик, и решатель против ключа генератора
    for f in flags:
        report.flags[f] += 1

    row = FamilyRow(
        id=uuid.uuid5(NAMESPACE, slug),
        slug=slug,
        kind=spec.kind.value,
        source=SOURCE,
        skill_id=taxonomy.skill_id(t.skill),
        skill_type=skill_type,
        level=spec.level,
        b=cfg.prior_b(spec.level),
        status="draft",
        spec={
            "form": form.model_dump(mode="json"),
            "author": spec.model_dump(mode="json"),
            "key_draft": draft.model_dump(mode="json") if draft else None,
            "autocheck": {"ok": True, "seeds": constructor.CHECK_SEEDS},
            "llm": {
                "model": model,
                "digest": d,
                "domain": t.domain,
                "flags": flags,
                "solver": {"score": solved, "k": k},
            },
        },
        key_status="draft",
        ai_solvable=solved or 0.0,
        stats={},
    )
    session.add(row)
    report.passed += 1
    report.created.append(slug)
    return None


async def measure_ai_solvable(
    session: AsyncSession,
    bank: Bank,
    *,
    statuses: Sequence[str] = ("draft", "pilot", "active"),
    k: int = SOLVE_K,
    report: Report | None = None,
) -> Report:
    """Прогон LLM как кандидата по банку → `families.ai_solvable`. Не делает `commit`."""
    report = report or Report()
    rows = list(
        await session.scalars(
            select(FamilyRow)
            .where(FamilyRow.status.in_(statuses), FamilyRow.kind != Kind.open.value)
            .order_by(FamilyRow.slug)
        )
    )
    measured: list[FamilyRow] = []
    for row in rows:
        fam = family_of(row)
        if fam is None:
            report.ai_skipped += 1
            continue
        try:
            score = await solver_score(bank, fam, k)
        except Exception as e:  # noqa: BLE001 — испорченное семейство не валит прогон
            log.warning("llm_bank_solve_failed", slug=row.slug, error=type(e).__name__)
            score = None
        if score is None:
            report.ai_skipped += 1
            continue
        row.ai_solvable = score
        measured.append(row)
    await session.flush()
    report.ai_measured = len(measured)
    if measured:
        report.ai_mean = round(sum(r.ai_solvable for r in measured) / len(measured), 3)
        top = sorted(measured, key=lambda r: (-r.ai_solvable, r.slug))[:REPORT_TOP]
        report.ai_top = [
            {"slug": r.slug, "status": r.status, "kind": r.kind, "ai_solvable": r.ai_solvable}
            for r in top
        ]
    return report


async def bank_counts(session: AsyncSession, report: Report) -> Report:
    """K в пилоте: семейства `source = llm`, дошедшие до `pilot` или `active` (решение админа)."""
    rows = await session.execute(
        select(FamilyRow.status, func.count())
        .where(FamilyRow.source == SOURCE)
        .group_by(FamilyRow.status)
    )
    by: dict[str, int] = {st: c for st, c in rows.all()}
    report.in_pilot = by.get("pilot", 0) + by.get("active", 0)
    report.in_draft = by.get("draft", 0)
    return report


def targets_of(
    skills: Sequence[str],
    kinds: Sequence[str],
    levels: Sequence[int],
    n: int,
    domain: str | None = None,
) -> list[Target]:
    return [Target(s, kd, lv, n, domain) for s in skills for kd in kinds for lv in levels]  # type: ignore[arg-type]


def write_report(report: Report, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = {**report.as_json(), "generated_at": datetime.now(UTC).isoformat()}
    (out / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    (out / "report.md").write_text(report.markdown(), "utf-8")


# --- CLI --------------------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> Report:
    from fsp_platform.db import make_engine, make_session_factory, session_scope

    from app.assessment.config import load_config

    settings = Settings()
    cfg = load_config(settings.scoring_config_path or None)
    bank = HttpBank(settings, timeout=args.timeout)
    report = Report(llm_available=bank.available)
    engine = make_engine(settings.database_url)
    try:
        async with session_scope(make_session_factory(engine)) as session:
            if not args.skip_propose:
                targets = targets_of(args.skills, args.kinds, args.levels, args.n, args.domain)
                await propose(session, bank, cfg, targets, k=args.k, report=report)
            if not args.skip_solve:
                await measure_ai_solvable(session, bank, k=args.k, report=report)
            await bank_counts(session, report)
    finally:
        await bank.aclose()
        await engine.dispose()
    return report


def _csv(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Офлайн-конвейер LLM-заданий и ai_solvable (E26-4)")
    p.add_argument("--skills", type=_csv, default=["python", "sql"])
    p.add_argument("--kinds", type=_csv, default=["exact", "choice", "find_bug", "order", "sjt"])
    p.add_argument("--levels", type=lambda v: [int(x) for x in _csv(v)], default=[2, 3])
    p.add_argument("--n", type=int, default=1, help="предложений на заказ (1–5)")
    p.add_argument("--domain", default=None)
    p.add_argument("--k", type=int, default=SOLVE_K, help="вариантов на прогон LLM-кандидата")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--skip-propose", action="store_true", help="только ai_solvable")
    p.add_argument("--skip-solve", action="store_true", help="только предложения")
    p.add_argument("--out", type=Path, default=Path("reports/llm-bank"))
    args = p.parse_args(argv)
    bad = set(args.kinds) - set(KINDS)
    if bad:
        p.error(f"неизвестные kind: {', '.join(sorted(bad))}")
    report = asyncio.run(run(args))
    write_report(report, args.out)
    print(report.markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
