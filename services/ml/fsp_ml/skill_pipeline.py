"""Конвейер сопоставления навыков: модерация → «навык ли это» → кандидаты → судья.

Быстрый путь (синонимы, нечёткий поиск) — `TaxonomyIndex.resolve`. Сюда попадает то, что он не
нашёл. Ничего не создаёт: возвращает решение (`SkillResolveItem`), вершины и синонимы применяет
core.

Без LLM (`ML_FAKE=true` или `LLM_ENABLED=false`) работают правила: серая зона классификатора
остаётся на правилах, а судья — `rule_judge`. Правиловый судья уверенность выше 0.85 не ставит,
поэтому сам ничего не сливает автоматически: максимум `same_pending` в очередь админа.

Порядок, который нельзя менять: `skill_distinct` проверяется ДО слияния (Java ≠ JavaScript).
Кеш решений — в памяти процесса, ключ `(norm, версия справочника)`: решение зависит от графа.
Постоянный журнал `skill_mentions` ведёт core.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal, Protocol

import jinja2
import structlog
from fsp_contracts.ml import SkillMention, SkillRelationGuess, SkillResolveItem
from pydantic import BaseModel, Field, ValidationError
from rapidfuzz import fuzz, process

from fsp_ml.embedder import Embedder
from fsp_ml.llm import LlmClient, LlmError
from fsp_ml.normalize import normalize
from fsp_ml.skill_moderation import classify_kind, moderate
from fsp_ml.taxonomy import TaxonomyIndex

log = structlog.get_logger()
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
JUDGE_PROMPT_VERSION = "v1"
KIND_PROMPT_VERSION = "v1"

# Пороги конвейера навыков. Числа вынесены сюда как значения по умолчанию.
CANDIDATES_TOP = 10
RERANK_GATE = 0.3  # ниже — судью не зовём
AUTO_SYNONYM_CONF = 0.9
AUTO_SYNONYM_COS = 0.88
PENDING_CONF = 0.6
RELATION_CONF = 0.7
GRAY_LOW, GRAY_HIGH = 0.4, 0.7
JUDGE_CALLS_MAX = 3  # LLM-вызовов судьи на одно упоминание: GPU одна
CACHE_SIZE = 5000
TYPO_RATIO = 90.0  # однословная опечатка в названии: ниже порога быстрого пути (92), но почти точно
TYPO_MIN_LEN = 5

Relation = Literal["same", "narrower", "broader", "related", "different"]


class Judgement(BaseModel):
    """Схема ответа судьи (LLM по JSON-схеме или правила)."""

    relation: Relation
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(default="", max_length=300)


class KindAnswer(BaseModel):
    kind: Literal["hard", "soft", "domain", "not_skill"]
    confidence: float = Field(ge=0, le=1)


class Reranker(Protocol):
    def score(self, mention: str, candidate_texts: list[str]) -> float:
        """Оценка пары 0..1 (bge-reranker-v2-m3 или лексическая замена)."""
        ...


class LexicalReranker:
    """Замена reranker без модели: лучшая лексическая близость к названию или синониму."""

    def score(self, mention: str, candidate_texts: list[str]) -> float:
        best = 0.0
        for t in candidate_texts:
            s = max(fuzz.ratio(mention, t), 0.85 * fuzz.token_set_ratio(mention, t)) / 100
            best = max(best, s)
        return best


@dataclass(frozen=True)
class Candidate:
    slug: str
    texts: list[str]  # название и синонимы в нижнем регистре
    sim: float  # близость для отбора: косинус эмбеддингов или лексика
    cos: float  # используется в пороге автосинонима
    blocked_same: bool = False  # пара «точно разные»: слияние запрещено


# --- шаблоны промптов ---


@cache
def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(PROMPTS_DIR), autoescape=False, keep_trailing_newline=False
    )


def _messages(name: str, version: str, **ctx: Any) -> list[dict[str, Any]]:
    t = _env().get_template(f"{name}/{version}.j2")
    return [
        {"role": "system", "content": t.render(part="system", **ctx).strip()},
        {"role": "user", "content": t.render(part="user", **ctx).strip()},
    ]


# --- правиловый судья ---

_TOKEN = re.compile(r"[a-zа-я0-9+#]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().replace("ё", "е"))


def rule_judge(norm: str, cand: Candidate) -> Judgement:
    """Судья без LLM. Уверенность ≤ 0.85: автослияния не бывает, только `same_pending`."""
    m = set(_tokens(norm))
    best: Judgement | None = None
    for text in cand.texts:
        c = set(_tokens(text))
        if not m or not c:
            continue
        if m == c:
            j = Judgement(relation="same", confidence=0.8, reason="те же слова в другом порядке")
        elif c < m and len(text) >= 3:
            j = Judgement(relation="narrower", confidence=0.75, reason="содержит название навыка")
        elif m < c and len(norm) >= 3:
            j = Judgement(relation="broader", confidence=0.72, reason="входит в название навыка")
        else:
            continue
        if best is None or j.confidence > best.confidence:
            best = j
    if best:
        return best
    if cand.sim >= 0.75:
        return Judgement(relation="related", confidence=0.7, reason="близкое написание")
    return Judgement(relation="different", confidence=0.6, reason="нет общих признаков")


# --- вспомогательное ---

_TRANSLIT = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
        [
            "a",
            "b",
            "v",
            "g",
            "d",
            "e",
            "e",
            "zh",
            "z",
            "i",
            "y",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "h",
            "c",
            "ch",
            "sh",
            "sch",
            "",
            "y",
            "",
            "e",
            "yu",
            "ya",
        ],
        strict=True,
    )
)


def make_slug(norm: str, index: TaxonomyIndex) -> str:
    """Slug новой вершины: латиница, цифры, дефис. При коллизии с другим навыком — суффикс-хеш."""
    low = norm.lower().replace("++", "pp").replace("#", "sharp")
    s = "".join(_TRANSLIT.get(ch, ch) for ch in low)
    slug = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48].strip("-")
    digest = hashlib.sha1(norm.encode()).hexdigest()[:6]
    if not slug:
        return f"skill-{digest}"
    return f"{slug}-{digest}" if slug in index.kinds else slug


def _cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb) if na and nb else 0.0


class SkillPipeline:
    def __init__(
        self,
        *,
        llm: LlmClient | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
        llm_model: str = "",
    ) -> None:
        self.llm = llm
        self.embedder = embedder
        self.reranker: Reranker = reranker or LexicalReranker()
        self.llm_model = llm_model
        self._cache: OrderedDict[tuple[str, int], SkillResolveItem] = OrderedDict()
        self._vecs: dict[tuple[int, str], list[float]] = {}
        self.cache_hits = 0

    # --- кеш ---

    def _get(self, key: tuple[str, int], m: SkillMention) -> SkillResolveItem | None:
        hit = self._cache.get(key)
        if hit is None:
            return None
        self._cache.move_to_end(key)
        self.cache_hits += 1
        return hit.model_copy(update={"raw": m.raw})

    def _put(self, key: tuple[str, int], item: SkillResolveItem) -> SkillResolveItem:
        self._cache[key] = item
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return item

    # --- публичный вход ---

    async def resolve(
        self, mentions: list[SkillMention], index: TaxonomyIndex
    ) -> list[SkillResolveItem]:
        return [await self.resolve_one(m, index) for m in mentions]

    async def resolve_one(self, m: SkillMention, index: TaxonomyIndex) -> SkillResolveItem:
        norm = normalize(m.raw)
        mod = moderate(m.raw)
        if mod.hide_text:  # ПДн и инъекции: текст не кешируем и не возвращаем
            return SkillResolveItem(
                raw="[скрыто]",
                norm="[скрыто]",
                decision="rejected",
                kind="not_skill",
                reason=mod.reason,
            )
        key = (norm, index.version)
        if (cached := self._get(key, m)) is not None:
            return cached

        fast = index.resolve(m)
        if fast is not None:
            return self._put(key, fast)
        if not mod.ok:
            return self._put(key, _rejected(m.raw, norm, mod.reason or "moderation"))

        kind, conf = classify_kind(norm)
        if GRAY_LOW <= conf < GRAY_HIGH:
            kind = await self._llm_kind(m, kind)
        if kind == "not_skill":
            return self._put(key, _rejected(m.raw, norm, "not_a_skill"))

        item = await self._match_existing(m, norm, kind, index)
        return self._put(key, item)

    # --- «навык ли это» в серой зоне ---

    async def _llm_kind(self, m: SkillMention, rule_kind: str) -> str:
        if self.llm is None:
            return rule_kind
        try:
            data = await self.llm.complete_json(
                _messages("skill_kind", KIND_PROMPT_VERSION, mention=m.raw, context=m.context),
                KindAnswer.model_json_schema(),
                schema_name="skill_kind",
            )
            ans = KindAnswer.model_validate(data)
        except (LlmError, ValidationError) as e:
            log.warning("skill_kind_llm_failed", error=type(e).__name__)
            return rule_kind
        # слабый ответ LLM не переворачивает правила: not_skill только при уверенности ≥ 0.7
        if ans.kind == "not_skill" and ans.confidence < GRAY_HIGH:
            return rule_kind
        return ans.kind

    # --- кандидаты ---

    def _texts(self, slug: str, index: TaxonomyIndex) -> list[str]:
        names = [index.names.get(slug, slug), slug, *index.aliases.get(slug, [])]
        return list(dict.fromkeys(normalize(n) for n in names if n))

    async def _embed(self, texts: list[str], index: TaxonomyIndex) -> list[list[float]]:
        assert self.embedder is not None
        need = [t for t in dict.fromkeys(texts) if (index.version, t) not in self._vecs]
        if need:
            vecs = await asyncio.to_thread(self.embedder.encode, need)
            for t, v in zip(need, vecs, strict=True):
                self._vecs[(index.version, t)] = v
        return [self._vecs[(index.version, t)] for t in texts]

    async def _candidates(self, norm: str, index: TaxonomyIndex) -> list[Candidate]:
        hits = process.extract(
            norm,
            index._fuzzy_keys,
            scorer=fuzz.token_set_ratio,
            limit=CANDIDATES_TOP * 4,
            score_cutoff=30,
        )
        slugs = list(dict.fromkeys(index.exact[k] for k, _, _ in hits))
        sims: dict[str, tuple[float, float]] = {}
        all_slugs = set(slugs)
        for s in slugs:  # партнёры «точно разные» нужны для проверки, даже если не вошли в топ
            for pair in index.distinct:
                if s in pair:
                    all_slugs |= pair
        for s in all_slugs:
            if s not in index.kinds:
                continue
            texts = self._texts(s, index)
            lex = self.reranker.score(norm, texts)
            sims[s] = (lex, lex)
        if self.embedder is not None and getattr(self.embedder, "ready", True) and sims:
            order = sorted(sims)
            docs = [" ".join(self._texts(s, index)) for s in order]
            vecs = await self._embed([norm, *docs], index)
            for s, v in zip(order, vecs[1:], strict=True):
                cos = max(0.0, _cosine(vecs[0], v))
                sims[s] = (cos, cos)
        ranked = sorted(sims, key=lambda s: -sims[s][0])
        out: list[Candidate] = []
        for s in ranked[:CANDIDATES_TOP]:
            sim, cos = sims[s]
            # skill_distinct ДО судьи: слияние запрещено, если упоминание не дальше от
            # «точно отличного» навыка, чем от этого
            blocked = any(
                frozenset((s, d)) in index.distinct and sims.get(d, (0.0, 0.0))[0] >= sim
                for d in sims
                if d != s
            )
            out.append(Candidate(s, self._texts(s, index), sim, cos, blocked))
        return out

    # --- судья ---

    async def _judge(
        self, m: SkillMention, norm: str, c: Candidate, index: TaxonomyIndex
    ) -> Judgement:
        if self.llm is None:
            return rule_judge(norm, c)
        try:
            data = await self.llm.complete_json(
                _messages(
                    "skill_judge",
                    JUDGE_PROMPT_VERSION,
                    mention=m.raw,
                    context=m.context,
                    cand_name=index.names.get(c.slug, c.slug),
                    cand_aliases=index.aliases.get(c.slug, [])[:8],
                    cand_description=None,
                ),
                Judgement.model_json_schema(),
                schema_name="skill_judge",
            )
            return Judgement.model_validate(data)
        except (LlmError, ValidationError) as e:
            log.warning("skill_judge_llm_failed", error=type(e).__name__)
            return rule_judge(norm, c)

    @staticmethod
    def _typo(norm: str, cands: list[Candidate]) -> Candidate | None:
        """Опечатка: однословное упоминание почти совпадает с единственным навыком."""
        if len(norm) < TYPO_MIN_LEN or " " in norm or not cands:
            return None
        top = cands[0]
        if top.blocked_same:
            return None
        ratio = max(fuzz.ratio(norm, t) for t in top.texts)
        if ratio < TYPO_RATIO:
            return None
        if len(cands) > 1 and max(fuzz.ratio(norm, t) for t in cands[1].texts) >= TYPO_RATIO - 5:
            return None  # неоднозначно
        return top

    async def _match_existing(
        self, m: SkillMention, norm: str, kind: str, index: TaxonomyIndex
    ) -> SkillResolveItem:
        all_cands = await self._candidates(norm, index)
        if typo := self._typo(norm, all_cands):
            return SkillResolveItem(
                raw=m.raw,
                norm=norm,
                decision="fuzzy",
                skill_slug=typo.slug,
                kind=index.kinds[typo.slug],
            )  # type: ignore[arg-type]
        cands = [c for c in all_cands if c.sim > RERANK_GATE]
        found: list[tuple[Candidate, Judgement]] = []
        llm_calls = 0
        for c in cands:
            if self.llm is not None:
                if llm_calls >= JUDGE_CALLS_MAX:
                    break
                llm_calls += 1
            j = await self._judge(m, norm, c, index)
            if j.relation != "different":
                found.append((c, j))
        slug = make_slug(norm, index)
        decision = _decide(m.raw, norm, kind, slug, found)
        return decision


def _rejected(raw: str, norm: str, reason: str) -> SkillResolveItem:
    return SkillResolveItem(
        raw=raw, norm=norm, decision="rejected", kind="not_skill", reason=reason
    )


def _decide(
    raw: str,
    norm: str,
    kind: str,
    new_slug: str,
    found: list[tuple[Candidate, Judgement]],
) -> SkillResolveItem:
    """Таблица решений судьи по типу связи."""
    base: dict[str, Any] = {"raw": raw, "norm": norm, "kind": kind}

    def new(rel: SkillRelationGuess | None = None, reason: str | None = None) -> SkillResolveItem:
        return SkillResolveItem(
            **base, decision="new", skill_slug=new_slug, relation=rel, reason=reason
        )

    # 1. same: не заблокирован skill_distinct
    sames = [(c, j) for c, j in found if j.relation == "same" and not c.blocked_same]
    if sames:
        c, j = max(sames, key=lambda x: x[1].confidence)
        if j.confidence >= AUTO_SYNONYM_CONF and c.cos >= AUTO_SYNONYM_COS:
            return SkillResolveItem(
                **base,
                decision="alias",
                skill_slug=c.slug,
                reason="new_synonym",
            )
        if j.confidence >= PENDING_CONF:
            return SkillResolveItem(
                **base,
                decision="same_pending",
                skill_slug=new_slug,
                relation=SkillRelationGuess(type="same", to_slug=c.slug, confidence=j.confidence),
            )
    # 2. narrower / broader / related ≥ 0.7; «same» заблокированный distinct — не выше related
    for c, j in found:
        rel = "related" if j.relation == "same" else j.relation
        if rel in ("narrower", "broader", "related") and j.confidence >= RELATION_CONF:
            return new(SkillRelationGuess(type=rel, to_slug=c.slug, confidence=j.confidence))  # type: ignore[arg-type]
    # 3. другое или низкая уверенность: вершина без связей (рёбра нарастут по встречаемости)
    return new()
