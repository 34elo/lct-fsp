"""Конструктор заданий (assessment.md §4, §7; E30-1, ADR-024): форма → семейство-спецификация.

Путь задания: форма → проверка схемы → ключ (автора или черновик LLM) → автопроверка на сидах →
строка `families` (`source = spec`, `draft`) → дальше жизненный цикл E22-9 (`lifecycle.py`):
- задание админа (без компании) после автопроверки сразу идёт в `pilot`;
- задание компании остаётся `draft` и работает только в её регулярных заданиях (E25-1); в общий
  банк (`pilot`) его переводит админ (`POST /admin/families/{id}/pilot`);
- `open` в θ не идёт и в банк не попадает никогда — только регулярные задания.

Ключ от LLM (`key_status = draft`) в оценку не идёт: `pilot → active` требует утверждённого
ключа (`lifecycle.approve`), утверждает его админ (`approve_key`). Функции не делают `commit`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from random import Random
from typing import Any, Literal

from fsp_contracts.ml import FamilyKeyDraft
from fsp_platform.app import ProblemError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import key_draft, lifecycle
from app.assessment.config import AssessmentConfig
from app.assessment.families import check
from app.assessment.families.base import Kind
from app.assessment.families.spec import FamilySpec, SpecError, SpecFamily
from app.assessment.models import FamilyRow
from app.assessment.world import World
from app.taxonomy import service as taxonomy

CHECK_SEEDS = 200
EXAMPLES = 3
MAX_ERRORS = 5

Drafter = Callable[[FamilySpec], Awaitable[FamilyKeyDraft | None]]
KeySource = Literal["author", "llm", "custom"]
SPEC_SOURCES = ("spec", "llm")  # llm — офлайн-конвейер E26-4: та же форма, «автор» — генератор


# --- автопроверка (чистые функции) ------------------------------------------------------------


def _check_open(fam: SpecFamily, seed_list: list[int]) -> list[str]:
    errs: list[str] = []
    for seed in seed_list:
        try:
            item = check.build(fam, seed)
            if not item.stem.strip() or not item.key:
                errs.append(f"seed={seed}: пустое условие или рубрика")
            if check.build(fam, seed) != item:
                errs.append(f"seed={seed}: повторная генерация даёт другой вариант")
        except Exception as e:  # noqa: BLE001 — любая ошибка генерации — провал проверки
            errs.append(f"seed={seed}: {type(e).__name__}: {e}")
        if len(errs) >= MAX_ERRORS:
            break
    return errs


def autocheck(fam: SpecFamily, n: int = CHECK_SEEDS) -> list[str]:
    """Генерация без ошибок, ключ однозначен и даёт 1, неверные варианты ≠ ключу, детерминизм.

    Те же проверки, что у `make families-check` для кодовых семейств (`families/check.py`);
    код из спецификации не исполняется.
    """
    seed_list = check.seeds(n)
    if fam.kind == Kind.open:
        return _check_open(fam, seed_list)
    return check.check_family(fam, seed_list)[:MAX_ERRORS]


def examples(fam: SpecFamily, k: int = EXAMPLES) -> list[dict[str, Any]]:
    """Примеры вариантов с ключом — для автора и админа (кандидату ключ не уходит никогда)."""
    out = []
    for seed in check.seeds(k):
        item = fam.generate(Random(seed), World.from_seed(seed))
        out.append({**item.public(), "key": item.key})
    return out


# --- создание ---------------------------------------------------------------------------------


def _family(spec: FamilySpec, slug: str, skill_type: str) -> SpecFamily:
    return SpecFamily(spec, slug=slug, skill_type=skill_type)


def _autocheck_or_422(fam: SpecFamily) -> dict[str, Any]:
    errs = autocheck(fam)
    if errs:
        raise ProblemError(
            422,
            "autocheck_failed",
            "Задание не прошло автопроверку",
            errs[0],
            errors=[{"field": "spec", "message": e} for e in errs],
        )
    return {"ok": True, "seeds": CHECK_SEEDS}


async def create_family(
    session: AsyncSession,
    spec: FamilySpec,
    cfg: AssessmentConfig,
    *,
    author_id: uuid.UUID,
    company_id: uuid.UUID | None,
    drafter: Drafter | None,
) -> FamilyRow:
    types = await taxonomy.skill_types_of(session, [spec.skill])
    if spec.skill not in types:
        raise ProblemError(
            422,
            "unknown_skill",
            "Навык не найден или у него нет типа",
            errors=[{"field": "skill", "message": spec.skill}],
        )
    skill_type = types[spec.skill].value

    draft = await drafter(spec) if drafter is not None and spec.kind != Kind.order else None
    missing = spec.missing_key()
    form, key_status = spec, "approved"
    if missing:
        if draft is None:
            raise ProblemError(
                422,
                "key_required",
                "Укажите правильный ответ: черновик LLM недоступен",
                ", ".join(missing),
                errors=[{"field": m, "message": "required"} for m in missing],
            )
        form, key_status = key_draft.apply(spec, draft), "draft"

    fid = uuid.uuid4()
    slug = f"c-{fid.hex[:12]}"
    try:
        report = _autocheck_or_422(_family(form, slug, skill_type))
    except SpecError as e:  # pragma: no cover - autocheck ловит ошибки генерации сам
        raise ProblemError(422, "autocheck_failed", "Задание не прошло автопроверку", str(e)) from e

    row = FamilyRow(
        id=fid,
        slug=slug,
        kind=spec.kind.value,
        source="spec",
        skill_id=taxonomy.skill_id(spec.skill),
        skill_type=skill_type,
        level=spec.level,
        b=cfg.prior_b(spec.level),
        status="draft",
        spec={
            "form": form.model_dump(mode="json"),
            "author": spec.model_dump(mode="json"),
            "key_draft": draft.model_dump(mode="json") if draft else None,
            "autocheck": report,
        },
        key_status=key_status,
        author_id=author_id,
        company_id=company_id,
        stats={},
    )
    session.add(row)
    await session.flush()
    if company_id is None and spec.kind != Kind.open:
        await lifecycle.to_pilot(session, row, cfg)
    return row


# --- чтение и решения админа ------------------------------------------------------------------


async def get_visible(
    session: AsyncSession,
    family_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    company_id: uuid.UUID | None,
    admin: bool,
) -> FamilyRow:
    """Семейство конструктора: автор, его компания или админ; иначе 404 (чужой ресурс)."""
    row = await session.get(FamilyRow, family_id)
    if row is None or row.source != "spec":
        raise ProblemError(404, "not_found", "Задание не найдено")
    if admin or row.author_id == user_id or (company_id and row.company_id == company_id):
        return row
    raise ProblemError(404, "not_found", "Задание не найдено")


async def list_visible(
    session: AsyncSession, *, user_id: uuid.UUID, company_id: uuid.UUID | None, admin: bool
) -> list[FamilyRow]:
    q = select(FamilyRow).where(FamilyRow.source == "spec")
    if not admin:
        conds = [FamilyRow.author_id == user_id]
        if company_id is not None:
            conds.append(FamilyRow.company_id == company_id)
        q = q.where(or_(*conds))
    return list(await session.scalars(q.order_by(FamilyRow.created_at.desc())))


def _spec_row(row: FamilyRow | None) -> FamilyRow:
    if row is None:
        raise ProblemError(404, "not_found", "Семейство не найдено")
    if row.source not in SPEC_SOURCES:
        raise ProblemError(
            409, "not_constructor_family", "Ключ задаётся только у заданий конструктора"
        )
    return row


async def approve_key(
    session: AsyncSession,
    family_id: uuid.UUID,
    admin_id: uuid.UUID,
    source: KeySource,
    custom: FamilySpec | None = None,
) -> FamilyRow:
    """Админ утверждает ключ: автора, черновик LLM или свою правку спецификации."""
    row = _spec_row(await session.get(FamilyRow, family_id))
    data = dict(row.spec or {})
    author = FamilySpec.model_validate(data["author"])
    if source == "author":
        if author.missing_key():
            raise ProblemError(409, "no_author_key", "Автор не указал ключ")
        form = author
    elif source == "llm":
        if not data.get("key_draft"):
            raise ProblemError(409, "no_key_draft", "Черновика ключа нет")
        form = key_draft.apply(author, FamilyKeyDraft.model_validate(data["key_draft"]))
    else:
        if custom is None:
            raise ProblemError(422, "spec_required", "Нужна спецификация с ключом")
        if (custom.kind, custom.skill, custom.level) != (author.kind, author.skill, author.level):
            raise ProblemError(422, "spec_mismatch", "kind, skill и level менять нельзя")
        form = custom
    if form.missing_key():
        raise ProblemError(409, "no_key", "В спецификации нет ключа")
    report = _autocheck_or_422(_family(form, row.slug, row.skill_type))
    log = list(data.get("key_log", []))
    log.append({"source": source, "admin_id": str(admin_id)})
    row.spec = {**data, "form": form.model_dump(mode="json"), "autocheck": report, "key_log": log}
    row.key_status = "approved"
    row.version = (row.version or 1) + 1
    await session.flush()
    return row


async def to_bank(
    session: AsyncSession, family_id: uuid.UUID, admin_id: uuid.UUID, cfg: AssessmentConfig
) -> FamilyRow:
    """Задание компании → общий банк (`draft → pilot`) решением админа."""
    row = _spec_row(await session.get(FamilyRow, family_id))
    if row.kind == Kind.open.value:
        raise ProblemError(409, "open_not_in_bank", "Открытые задания не идут в тест")
    if not (row.spec or {}).get("autocheck", {}).get("ok"):
        raise ProblemError(409, "autocheck_failed", "Задание не прошло автопроверку")
    if row.status == "pilot":
        return row
    await lifecycle.set_status(session, row, "pilot", cfg, reason="admin", actor_id=admin_id)
    return row
