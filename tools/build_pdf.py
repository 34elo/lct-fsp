"""Собирает PDF из Markdown-документов: Markdown → HTML → печать в PDF браузером.

    uv run --with markdown python tools/build_pdf.py summary      # сводка для жюри
    uv run --with markdown python tools/build_pdf.py docs         # сопроводительная документация

Нужен установленный Edge или Chrome (`BROWSER` — путь к исполняемому файлу). Диаграммы Mermaid
рисуются скриптом с CDN, поэтому при сборке нужен интернет. Результат — `submission/*.pdf`.
"""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT / "submission"  # каталог в .gitignore: PDF для сдачи в репозиторий не входят
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
)

# Порядок разделов сопроводительной документации
SUPPORT = [
    ("Обзор документации", ["README.md"]),
    ("Как решение закрывает критерии оценки", ["product/criteria.md"]),
    (
        "Продукт",
        [
            "product/case.md",
            "product/requirements.md",
            "product/features.md",
            "product/qa-session.md",
            "product/questions.md",
            "product/roadmap.md",
        ],
    ),
    (
        "Архитектура",
        [
            "architecture/overview.md",
            "architecture/modules.md",
            "architecture/data-model.md",
            "architecture/api.md",
            "architecture/messaging.md",
            "architecture/security.md",
            "architecture/frontend.md",
            "design.md",
        ],
    ),
    (
        "Механики",
        [
            "mechanics/assessment.md",
            "mechanics/matching.md",
            "mechanics/contact.md",
            "mechanics/skills.md",
            "mechanics/fsp.md",
            "mechanics/ml.md",
        ],
    ),
    ("Валидация и качество", ["quality/validation.md", "quality/testing.md"]),
    (
        "Запуск и эксплуатация",
        ["operations/running.md", "operations/infrastructure.md", "operations/configuration.md"],
    ),
    (
        "Решения (ADR)",
        [
            "adr/README.md",
            *sorted(
                str(p.relative_to(DOCS)).replace("\\", "/") for p in (DOCS / "adr").glob("0*.md")
            ),
        ],
    ),
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font: 10.5pt/1.5 'Segoe UI', Arial, sans-serif; color: #1b1c21; }
h1 { font-size: 20pt; color: #201880; border-bottom: 2px solid #402fff; padding-bottom: 4px; margin-top: 0; }
h2 { font-size: 14pt; color: #201880; margin-top: 18px; }
h3 { font-size: 11.5pt; margin-top: 14px; }
a { color: #402fff; text-decoration: none; }
code { font: 9pt Consolas, monospace; background: #f4f3ff; padding: 0 3px; border-radius: 3px; }
pre { background: #1b1c21; color: #ededed; padding: 8px 10px; border-radius: 6px; white-space: pre-wrap;
      page-break-inside: avoid; font: 8.5pt/1.4 Consolas, monospace; }
pre code { background: none; color: inherit; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #e6e4ff; text-align: left; }
th, td { border: 1px solid #e1e1e5; padding: 3px 6px; vertical-align: top; }
blockquote { border-left: 3px solid #a9a1ff; margin: 8px 0; padding: 2px 10px; color: #5b5d66; }
.doc { page-break-before: always; }
.part { page-break-before: always; font-size: 26pt; color: #402fff; margin-top: 120px; border: 0; }
.cover { text-align: center; margin-top: 200px; }
.cover h1 { font-size: 30pt; border: 0; }
.mermaid { text-align: center; page-break-inside: avoid; margin: 8px 0; }
"""


def slug(path: str) -> str:
    return "doc-" + re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")


def convert(md_path: Path, rel: str, known: dict[str, str]) -> str:
    text = md_path.read_text(encoding="utf-8")
    text = re.sub(
        r"```mermaid\n(.*?)```",
        lambda m: f'<div class="mermaid">{html.escape(m.group(1))}</div>',
        text,
        flags=re.S,
    )

    def link(m: re.Match[str]) -> str:
        label, target = m.group(1), m.group(2)
        if re.match(r"[a-z]+://|#", target):
            return m.group(0)
        file = target.split("#")[0]
        resolved = os.path.normpath(os.path.join(os.path.dirname(rel), file)).replace("\\", "/")
        if resolved in known:
            return f"[{label}](#{known[resolved]})"
        return label  # ссылка на файл вне PDF (код, JSON) — оставляем текст

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    return f'<section class="doc" id="{known.get(rel, slug(rel))}">{body}</section>'


def page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
        f"<style>{CSS}</style><script src='{MERMAID}'></script>"
        "<script>mermaid.initialize({startOnLoad:true,theme:'neutral',flowchart:{useMaxWidth:true}});</script>"
        f"</head><body>{body}</body></html>"
    )


def to_pdf(html_text: str, out: Path) -> None:
    browser = os.environ.get("BROWSER") or next((b for b in BROWSERS if Path(b).exists()), None)
    if not browser:
        sys.exit("Не найден Edge или Chrome: задайте BROWSER")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "doc.html"
        src.write_text(html_text, encoding="utf-8")
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                "--virtual-time-budget=30000",
                f"--print-to-pdf={out}",
                src.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
    print(f"{out.relative_to(ROOT)}  {out.stat().st_size // 1024} КБ")


def build_summary() -> None:
    known = {"product/summary.md": "summary"}
    body = convert(DOCS / "product/summary.md", "product/summary.md", known).replace(
        ' class="doc"', "", 1
    )
    to_pdf(page("ФСП Карьера — сводка проекта", body), OUT / "fsp-career-summary.pdf")


def build_support() -> None:
    files = [f for _, group in SUPPORT for f in group]
    known = {f: slug(f) for f in files}
    parts = [
        "<div class='cover'><h1>ФСП Карьера</h1><h2>Сопроводительная документация</h2>"
        "<p>Архитектура, механики тестирования и подбора, валидация, API, запуск, решения команды</p>"
        "<p>https://github.com/34elo/lct-fsp</p></div>"
    ]
    for title, group in SUPPORT:
        parts.append(f"<h1 class='part'>{html.escape(title)}</h1>")
        parts.extend(convert(DOCS / f, f, known) for f in group)
    to_pdf(
        page("ФСП Карьера — сопроводительная документация", "".join(parts)),
        OUT / "fsp-career-documentation.pdf",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["summary", "docs", "all"])
    a = ap.parse_args()
    if a.what in ("summary", "all"):
        build_summary()
    if a.what in ("docs", "all"):
        build_support()
