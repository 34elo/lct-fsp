"""E27-4: документ сдачи Markdown → HTML → PDF (WeasyPrint, шрифт DejaVu, как в E20-6).

Сторонних Markdown-библиотек нет: минимальный конвертер покрывает то, что мы пишем в
`docs/submission.md` (заголовки, абзацы, списки, таблицы, код, цитаты, **жирный**, `код`, ссылки).
Запуск: `uv run python tools/submission/build_pdf.py [--src docs/submission.md] [--out reports/submission/submission.pdf]`.
"""

from __future__ import annotations

import argparse
import re
from html import escape
from pathlib import Path

# ruff: noqa: E501
CSS = """
@page { size: A4; margin: 18mm 15mm; @bottom-right { content: counter(page) " / " counter(pages);
  font-size: 8pt; color: #6b6b7b; } }
body { font-family: "DejaVu Sans", "Liberation Sans", sans-serif; font-size: 9.5pt; line-height: 1.4; color: #1b1b25; }
h1 { font-size: 20pt; color: #201880; margin: 0 0 8pt; }
h2 { font-size: 13pt; color: #402FFF; border-bottom: 1.5pt solid #A9A1FF; padding-bottom: 2pt; margin: 16pt 0 6pt; page-break-after: avoid; }
h3 { font-size: 10.5pt; color: #201880; margin: 10pt 0 4pt; page-break-after: avoid; }
blockquote { border-left: 3pt solid #A9A1FF; margin: 6pt 0; padding: 2pt 8pt; color: #4a4a5a; background: #f6f5ff; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0; font-size: 8.5pt; }
td, th { text-align: left; padding: 3pt 4pt; border-bottom: .5pt solid #e1e0f0; vertical-align: top; }
th { color: #201880; background: #eeecff; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; background: #f1f0fa; padding: 0 2pt; }
pre { font-family: "DejaVu Sans Mono", monospace; font-size: 7.5pt; background: #f1f0fa; padding: 6pt; white-space: pre-wrap; }
pre code { background: none; padding: 0; }
a { color: #402FFF; text-decoration: none; }
"""

_LIST_RE = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def inline(text: str) -> str:
    """Экранирует HTML и разворачивает `код`, **жирный**, *курсив*, [ссылка](url)."""
    codes: list[str] = []

    def stash(m: re.Match[str]) -> str:
        codes.append(f"<code>{escape(m.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    s = re.sub(r"`([^`]+)`", stash, text)
    s = escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"<em>\1</em>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], s)


def _cells(line: str) -> list[str]:
    parts = re.split(r"(?<!\\)\|", line.strip())
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return [p.strip().replace("\\|", "|") for p in parts]


def _is_sep(line: str) -> bool:
    return (
        bool(re.match(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$", line)) and "-" in line
    )


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    para: list[str] = []
    stack: list[str] = []  # открытые <ul>/<ol>

    def flush_para() -> None:
        if para:
            out.append("<p>" + inline(" ".join(para)) + "</p>")
            para.clear()

    def close_lists() -> None:
        while stack:
            out.append(f"</{stack.pop()}>")

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_para()
            close_lists()
            lang = line[3:].strip()
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            if lang == "mermaid":
                out.append(
                    "<blockquote>Схема (Mermaid) отрисовывается в Markdown-версии документа; "
                    "ниже её исходный текст.</blockquote>"
                )
            out.append("<pre><code>" + escape("\n".join(buf)) + "</code></pre>")
            continue
        if not line.strip():
            flush_para()
            close_lists()
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para()
            close_lists()
            n = len(m.group(1))
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
            continue
        if re.match(r"^-{3,}\s*$", line):
            flush_para()
            close_lists()
            out.append("<hr/>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and _is_sep(lines[i + 1]):
            flush_para()
            close_lists()
            head = _cells(line)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            body = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows
            )
            out.append(f"<table><tr>{th}</tr>{body}</table>")
            continue
        if line.startswith(">"):
            flush_para()
            close_lists()
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip(">").strip())
                i += 1
            out.append("<blockquote>" + inline(" ".join(buf)) + "</blockquote>")
            continue
        lm = _LIST_RE.match(line)
        if lm:
            flush_para()
            tag = "ol" if lm.group(2)[0].isdigit() else "ul"
            depth = len(lm.group(1)) // 2 + 1
            while len(stack) > depth:
                out.append(f"</{stack.pop()}>")
            while len(stack) < depth:
                stack.append(tag)
                out.append(f"<{tag}>")
            out.append(f"<li>{inline(lm.group(3))}</li>")
            i += 1
            continue
        close_lists()
        para.append(line.strip())
        i += 1
    flush_para()
    close_lists()
    return "\n".join(out)


def to_html(md: str, title: str = "ФСП Карьера: документ сдачи") -> str:
    return (
        f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{CSS}</style></head><body>{convert(md)}</body></html>"
    )


def build(src: Path, out: Path) -> int:
    from weasyprint import HTML  # тяжёлая зависимость core; импорт отложен ради тестов конвертера

    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=to_html(src.read_text(encoding="utf-8")), base_url=str(src.parent)).write_pdf(out)
    return out.stat().st_size


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=Path("docs/submission.md"))
    ap.add_argument("--out", type=Path, default=Path("reports/submission/submission.pdf"))
    args = ap.parse_args()
    size = build(args.src, args.out)
    print(f"{args.out}: {size // 1024} КБ")


if __name__ == "__main__":
    main()
