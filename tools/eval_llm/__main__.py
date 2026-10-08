"""`python -m tools.eval_llm` (make eval-llm): замер LLM на задачах проекта (E32-3).

Ходит в OpenAI-совместимый сервер (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`), гоняет три набора
(разбор резюме, черновик ключа задания, объяснение ошибки) и пишет `<out>/<модель>.{json,md}`:
валидность JSON, прохождение схемы, F1 навыков с проверенной цитатой, доля «придуманных»
навыков, латентность p50/p95, токены/с, память (по желанию). Только стандартная библиотека.
Модели не скачиваются и не запускаются: сервер поднимает человек (ml.md §«Выбор LLM»).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import cases

ROOT = Path(__file__).resolve().parents[2]
ENV_KEYS = {"LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "ML_FAKE"}


class EvalError(RuntimeError):
    """Понятная пользователю причина, по которой замер невозможен."""


def load_env_file(path: Path) -> dict[str, str]:
    """Из env-файла берём только LLM_*/ML_FAKE, остальное (секреты) игнорируем."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Z_]+)\s*=\s*(.*?)\s*$", line)
        if m and m.group(1) in ENV_KEYS:
            out[m.group(1)] = m.group(2).strip("'\"")
    return out


# --- клиент ---


def chat(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any] | None,
    max_tokens: int,
    timeout: float,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": schema, "strict": True},
        }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise EvalError(f"сервер LLM ответил HTTP {e.code} на {base_url}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise EvalError(f"LLM недоступна по {base_url}: {e}") from e
    elapsed = time.perf_counter() - t0
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise EvalError("ответ сервера не похож на OpenAI chat/completions") from e
    usage = data.get("usage") or {}
    return {
        "content": content,
        "elapsed": elapsed,
        "completion_tokens": usage.get("completion_tokens"),
        "prompt_tokens": usage.get("prompt_tokens"),
    }


# --- проверки ---


def parse_json(content: str) -> Any | None:
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None


def _type_ok(value: Any, spec: dict[str, Any]) -> bool:
    types = spec.get("type")
    if types is None:
        return True
    names = types if isinstance(types, list) else [types]
    py = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    for n in names:
        if n == "integer" and isinstance(value, bool):
            continue
        if isinstance(value, py[n]):
            return True
    return False


def schema_errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Минимальная проверка JSON-схемы: type, required, properties, items."""
    if not _type_ok(value, schema):
        return [f"{path}: тип"]
    errs: list[str] = []
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}.{key}: нет поля")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errs += schema_errors(value[key], sub, f"{path}.{key}")
    elif isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errs += schema_errors(item, schema["items"], f"{path}[{i}]")
    return errs


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("ё", "е")).strip()


def skill_verified(skill: dict[str, Any], text: str) -> bool:
    """Навык принят, если цитата дословно в тексте и навык назван в ней (ml.md §2)."""
    name, quote = norm(str(skill.get("name", ""))), norm(str(skill.get("quote", "")))
    if not name or not quote or quote not in norm(text):
        return False
    return re.search(rf"(?<![\w+#]){re.escape(name)}(?![\w+#])", quote) is not None


def score_resume(case: dict[str, Any], obj: Any) -> dict[str, Any]:
    skills = obj.get("skills", []) if isinstance(obj, dict) else []
    skills = [s for s in skills if isinstance(s, dict)]
    verified = {norm(str(s["name"])) for s in skills if skill_verified(s, case["text"])}
    gold = {norm(g) for g in case["gold"]}
    trap = {norm(t) for t in case["trap"]}
    tp = len(verified & gold)
    fp = len(verified - gold)
    fn = len(gold - verified)
    named = {norm(str(s.get("name", ""))) for s in skills}
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "predicted": len(skills),
        "unverified": sum(1 for s in skills if not skill_verified(s, case["text"])),
        "trap_hits": len((named | verified) & trap),
    }


def score_key(case: dict[str, Any], obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    exp = case["expect"]
    if "correct" in exp:
        return obj.get("correct") == exp["correct"]
    return sorted(obj.get("bug_lines") or []) == sorted(exp["bug_lines"])


def score_explain(case: dict[str, Any], obj: Any) -> dict[str, bool]:
    text = str(obj.get("text", "")) if isinstance(obj, dict) else ""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    letters = [c for c in text if c.isalpha()]
    cyr = sum(1 for c in letters if "а" <= c.lower() <= "я" or c.lower() == "ё")
    return {
        "length_ok": 2 <= len(sentences) <= 4,
        "russian": bool(letters) and cyr / len(letters) >= 0.7,
        "no_leak": not any(f.lower() in text.lower() for f in case["forbidden"]),
    }


# --- прогон ---


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 3)


def run_task(
    name: str,
    items: list[dict[str, Any]],
    system: str,
    schema: dict[str, Any],
    scorer: Any,
    args: argparse.Namespace,
    cfg: dict[str, str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in items:
        user = item.get("text") and f'Резюме:\n"""\n{item["text"]}\n"""' or item["prompt"]
        for rep in range(args.repeats):
            r = chat(
                cfg["base_url"],
                cfg["api_key"],
                cfg["model"],
                system,
                user,
                None if args.no_grammar else schema,
                args.max_tokens,
                args.timeout,
            )
            obj = parse_json(r["content"])
            errs = schema_errors(obj, schema) if obj is not None else ["не JSON"]
            tps = None
            if r["completion_tokens"] and r["elapsed"] > 0:
                tps = round(r["completion_tokens"] / r["elapsed"], 2)
            rows.append(
                {
                    "case": item["id"],
                    "rep": rep,
                    "elapsed": round(r["elapsed"], 3),
                    "completion_tokens": r["completion_tokens"],
                    "tokens_per_s": tps,
                    "json_valid": obj is not None,
                    "schema_ok": not errs,
                    "schema_errors": errs[:5],
                    "score": scorer(item, obj) if not errs else None,
                }
            )
    return {"name": name, "rows": rows}


def summarize(task: dict[str, Any]) -> dict[str, Any]:
    rows = task["rows"]
    n = len(rows)
    lat = [r["elapsed"] for r in rows]
    tps = [r["tokens_per_s"] for r in rows if r["tokens_per_s"]]
    out: dict[str, Any] = {
        "requests": n,
        "json_valid": round(sum(r["json_valid"] for r in rows) / n, 3),
        "schema_ok": round(sum(r["schema_ok"] for r in rows) / n, 3),
        "latency_p50_s": percentile(lat, 0.5),
        "latency_p95_s": percentile(lat, 0.95),
        "tokens_per_s": round(statistics.median(tps), 2) if tps else None,
    }
    scores = [r["score"] for r in rows if r["score"] is not None]
    if task["name"] == "resume" and scores:
        tp, fp, fn = (sum(s[k] for s in scores) for k in ("tp", "fp", "fn"))
        pred = sum(s["predicted"] for s in scores)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out["skills_precision"] = round(prec, 3)
        out["skills_recall"] = round(rec, 3)
        out["skills_f1"] = round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0
        out["hallucinated_share"] = (
            round(sum(s["unverified"] for s in scores) / pred, 3) if pred else 0.0
        )
        out["trap_hits"] = sum(s["trap_hits"] for s in scores)
    if task["name"] == "key" and scores:
        out["key_accuracy"] = round(sum(scores) / len(scores), 3)
    if task["name"] == "explain" and scores:
        for k in ("length_ok", "russian", "no_leak"):
            out[k] = round(sum(s[k] for s in scores) / len(scores), 3)
    return out


def read_memory(args: argparse.Namespace) -> dict[str, Any]:
    """Память: RSS сервера (`--server-pid`) и VRAM amdgpu (`--vram-file`); без них None."""
    mem: dict[str, Any] = {"server_rss_mb": None, "vram_used_mb": None}
    if args.server_pid:
        try:
            for line in Path(f"/proc/{args.server_pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    mem["server_rss_mb"] = round(int(line.split()[1]) / 1024)
        except OSError:
            pass
    if args.vram_file:
        try:
            mem["vram_used_mb"] = round(int(Path(args.vram_file).read_text().strip()) / 2**20)
        except (OSError, ValueError):
            pass
    return mem


def resolve_config(args: argparse.Namespace, environ: dict[str, str]) -> dict[str, str]:
    env = dict(load_env_file(Path(args.env_file))) if args.env_file else {}
    env.update({k: v for k, v in environ.items() if k in ENV_KEYS})
    if env.get("ML_FAKE", "").lower() in ("1", "true", "yes"):
        raise EvalError(
            "ML_FAKE=true: LLM подменена заглушкой, замерять нечего. Запусти с ML_FAKE=false и "
            "реальным LLM_BASE_URL (llama-server на GPU-машине)."
        )
    base = args.base_url or env.get("LLM_BASE_URL", "")
    if not base:
        raise EvalError("не задан LLM_BASE_URL (или --base-url): адрес OpenAI-совместимого сервера")
    model = args.model or env.get("LLM_MODEL", "")
    if not model:
        raise EvalError("не задана модель: LLM_MODEL или --model")
    return {"base_url": base, "api_key": env.get("LLM_API_KEY", ""), "model": model}


def render_md(report: dict[str, Any]) -> str:
    lines = [
        f"# Замер LLM: {report['model']}",
        "",
        f"Дата: {report['date']} · сервер: {report['base_url']} · режим: {report['mode']} · "
        f"повторов: {report['repeats']}",
        "",
    ]
    mem = report["memory"]
    lines.append(
        f"Память: RSS сервера {mem['server_rss_mb']} МБ, VRAM {mem['vram_used_mb']} МБ "
        "(пусто — не передан `--server-pid` / `--vram-file`)."
    )
    for name, s in report["summary"].items():
        lines += ["", f"## {name}", "", "| Метрика | Значение |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in s.items()]
    return "\n".join(lines) + "\n"


def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("_") or "model"


def main(argv: list[str] | None = None, environ: dict[str, str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.eval_llm", description=__doc__)
    p.add_argument("--base-url", help="по умолчанию LLM_BASE_URL")
    p.add_argument("--model", help="по умолчанию LLM_MODEL")
    p.add_argument(
        "--env-file", help="читаются только LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, ML_FAKE"
    )
    p.add_argument("--out", default=str(ROOT / "reports" / "llm"))
    p.add_argument("--repeats", type=int, default=3, help="повторов каждого запроса (для p50/p95)")
    p.add_argument("--tasks", default="resume,key,explain")
    p.add_argument(
        "--no-grammar",
        action="store_true",
        help="без response_format: валидность JSON только по промпту",
    )
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--server-pid", type=int, help="PID llama-server: RSS из /proc")
    p.add_argument("--vram-file", help="например /sys/class/drm/card0/device/mem_info_vram_used")
    args = p.parse_args(argv)
    environ = dict(os.environ) if environ is None else environ
    try:
        cfg = resolve_config(args, environ)
        plan = {
            "resume": (cases.RESUMES, cases.RESUME_SYSTEM, cases.RESUME_SCHEMA, score_resume),
            "key": (cases.KEYS, cases.KEY_SYSTEM, cases.KEY_SCHEMA, score_key),
            "explain": (cases.EXPLAINS, cases.EXPLAIN_SYSTEM, cases.EXPLAIN_SCHEMA, score_explain),
        }
        wanted = [t for t in args.tasks.split(",") if t]
        unknown = [t for t in wanted if t not in plan]
        if unknown:
            raise EvalError(f"неизвестные наборы: {', '.join(unknown)}")
        tasks = [
            run_task(t, plan[t][0], plan[t][1], plan[t][2], plan[t][3], args, cfg) for t in wanted
        ]
    except EvalError as e:
        print(f"eval-llm: {e}", file=sys.stderr)
        return 2
    report = {
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "mode": "prompt-only" if args.no_grammar else "json_schema",
        "repeats": args.repeats,
        "memory": read_memory(args),
        "summary": {t["name"]: summarize(t) for t in tasks},
        "rows": {t["name"]: t["rows"] for t in tasks},
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = slug(cfg["model"]) + ("-nogrammar" if args.no_grammar else "")
    (out / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out / f"{stem}.md").write_text(render_md(report), encoding="utf-8")
    print(f"eval-llm: отчёт {out / (stem + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
