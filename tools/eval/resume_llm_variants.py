"""Сравнение вариантов вызова LLM для разбора резюме (E43-8) на `data/eval/resumes/hh/`.

Запуск на стенде с реальной моделью (адрес и ключ — в окружении, не в репозитории):
    LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=qwen3-vl-4b \
      uv run python tools/eval/resume_llm_variants.py [--variants base,t0,...] [--json out.json]
Проверка самого скрипта без модели: `--fake` (фейковый клиент, часть ответов пустая).
Только правиловая линия, без модели: `--rules-only`.

Для каждого варианта и каждого резюме: полнота навыков по эталону `gold.json` (только LLM и с
запасным путём E43-8), доля отброшенных проверкой цитат, время, число нулевых ответов.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
HH_DIR = ROOT / "data" / "eval" / "resumes" / "hh"
TAXONOMY = ROOT / "data" / "taxonomy" / "skills.yaml"
TODAY = date(2026, 10, 1)
for p in (ROOT / "services/ml", ROOT / "packages/contracts/src", ROOT / "packages/platform/src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fsp_ml import resume_parser as rp  # noqa: E402
from fsp_ml.llm import LlmError  # noqa: E402
from fsp_ml.resume_text import extract_text  # noqa: E402
from fsp_ml.taxonomy import TaxonomyIndex  # noqa: E402

FEWSHOT = (
    "Пример. Текст: «Пишу сервисы на Go, храню данные в ClickHouse.» Ответ: "
    '{"skills":[{"name":"Go","quote":"Пишу сервисы на Go, храню данные в ClickHouse."},'
    '{"name":"ClickHouse","quote":"Пишу сервисы на Go, храню данные в ClickHouse."}]}\n\n'
)

VARIANTS: dict[str, dict[str, Any]] = {
    "base": {"temperature": 0.1, "max_tokens": 4096, "think": False},
    "t0": {"temperature": 0.0, "max_tokens": 4096, "think": False},
    "t03": {"temperature": 0.3, "max_tokens": 4096, "think": False},
    "max8k": {"temperature": 0.1, "max_tokens": 8192, "think": False},
    "think": {"temperature": 0.1, "max_tokens": 8192, "think": True},
    "sections": {"temperature": 0.1, "max_tokens": 4096, "think": False, "sections": True},
    "simple": {"temperature": 0.1, "max_tokens": 2048, "think": False, "simple": True},
    "fewshot": {"temperature": 0.1, "max_tokens": 4096, "think": False, "fewshot": True},
}


class Client:
    """Минимальный OpenAI-совместимый клиент с параметрами варианта."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 120.0) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.model, self.timeout = model, timeout

    async def complete(self, messages: list, schema: dict, v: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": v["temperature"],
            "max_tokens": v["max_tokens"],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "resume", "schema": schema, "strict": True},
            },
            "chat_template_kwargs": {"enable_thinking": bool(v["think"])},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.post(self.url, json=body, headers=self.headers)
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


class FakeClient:
    """Для проверки скрипта: каждый второй ответ пустой по навыкам."""

    def __init__(self) -> None:
        self.n = 0

    async def complete(self, messages: list, schema: dict, v: dict[str, Any]) -> dict[str, Any]:
        self.n += 1
        if self.n % 2:
            return {"skills": []}
        text = messages[-1]["content"]
        line = next((ln.strip() for ln in text.splitlines() if "Python" in ln), "")
        return {"skills": [{"name": "Python", "quote": line[:200]}] if line else []}


class SimpleSkills(rp.BaseModel):
    skills: list[rp.LlmSkill] = rp.Field(default_factory=list, max_length=80)


def _chunks(text: str, size: int = 2500) -> list[str]:
    out: list[str] = []
    cur = ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > size:
            out.append(cur)
            cur = ""
        cur += para + "\n\n"
    return [*out, cur] if cur.strip() else out


async def run_variant(client: Any, v: dict[str, Any], text: str) -> rp.LlmResume:
    schema_cls = SimpleSkills if v.get("simple") else rp.LlmResume
    schema = schema_cls.model_json_schema()
    chunks = _chunks(text) if v.get("sections") else [text]
    merged = rp.LlmResume()
    for ch in chunks:
        messages = rp.build_messages(ch)
        if v.get("fewshot"):
            messages[-1]["content"] = FEWSHOT + messages[-1]["content"]
        part = schema_cls.model_validate(await client.complete(messages, schema, v))
        merged.skills += part.skills
        if isinstance(part, rp.LlmResume):
            merged.experience += part.experience
            merged.education += part.education
            merged.full_name = merged.full_name or part.full_name
            merged.city = merged.city or part.city
            merged.summary = merged.summary or part.summary
    return merged


def _recall(gold: set[str], got: set[str]) -> tuple[int, int]:
    return len(gold & got), len(gold)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--rules-only", action="store_true")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    import yaml

    skills = yaml.safe_load(TAXONOMY.read_text(encoding="utf-8"))["skills"]
    index = TaxonomyIndex.from_snapshot({"version": 1, "skills": skills})
    items = json.loads((HH_DIR / "gold.json").read_text(encoding="utf-8"))["resumes"]
    texts = {g["file"]: extract_text((HH_DIR / g["file"]).read_bytes()) for g in items}

    rows: list[dict[str, Any]] = []
    hit = tot = 0
    t0 = time.monotonic()
    for g in items:
        t = texts[g["file"]]
        parsed = rp.assemble(
            t, rp.extract_rules(t, index), index, version=rp.RULES_VERSION, today=TODAY
        )
        h, n = _recall(set(g["skills"]), {s.slug for s in parsed.skills})
        hit, tot = hit + h, tot + n
    rows.append(
        {
            "variant": "rules",
            "n": len(items),
            "recall": round(hit / tot, 3),
            "recall_fallback": round(hit / tot, 3),
            "dropped_share": 0.0,
            "zero": 0,
            "sec_avg": round((time.monotonic() - t0) / len(items), 3),
        }
    )
    if not args.rules_only:
        if args.fake:
            client: Any = FakeClient()
        else:
            url = os.environ.get("LLM_BASE_URL")
            if not url:
                sys.exit("LLM_BASE_URL не задан (или --fake / --rules-only)")
            client = Client(url, os.environ.get("LLM_API_KEY", ""), os.environ["LLM_MODEL"])
        for name in args.variants.split(","):
            v = VARIANTS[name]
            h1 = h2 = tot = zero = raw = dropped = errors = 0
            secs = 0.0
            for g in items:
                t = texts[g["file"]]
                s0 = time.monotonic()
                try:
                    out = await run_variant(client, v, t)
                except (LlmError, httpx.HTTPError, ValueError) as e:
                    errors += 1
                    print(f"{name} {g['file']}: {type(e).__name__}", file=sys.stderr)
                    continue
                secs += time.monotonic() - s0
                parsed = rp.assemble(t, out, index, version="eval", today=TODAY)
                zero += not out.skills
                raw += len(out.skills)
                dropped += sum(w.startswith(rp.DROP_WARNINGS) for w in parsed.warnings)
                gold = set(g["skills"])
                a, n = _recall(gold, {s.slug for s in parsed.skills})
                h1, tot = h1 + a, tot + n
                if rp.needs_rules_fallback(len(parsed.skills), len(t)):
                    parsed, _ = rp.merge_rules_fallback(parsed, t, index, TODAY)
                h2 += _recall(gold, {s.slug for s in parsed.skills})[0]
            done = len(items) - errors
            rows.append(
                {
                    "variant": name,
                    "n": done,
                    "recall": round(h1 / tot, 3) if tot else None,
                    "recall_fallback": round(h2 / tot, 3) if tot else None,
                    "dropped_share": round(dropped / raw, 3) if raw else None,
                    "zero": zero,
                    "errors": errors,
                    "sec_avg": round(secs / done, 2) if done else None,
                }
            )
    print("| вариант | n | полнота LLM | полнота с запасным путём | отброшено | нулевых | с |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['variant']} | {r['n']} | {r['recall']} | {r['recall_fallback']} | "
            f"{r['dropped_share']} | {r['zero']} | {r['sec_avg']} |"
        )
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
