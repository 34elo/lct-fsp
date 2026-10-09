"""Проверка ссылок в Markdown-документах репозитория (E39-37).

Проверяет относительные ссылки `[текст](путь#якорь)` и `<a href="...">`: файл или каталог
существует, якорь есть среди заголовков целевого `.md` (слаг как у GitHub). Внешние ссылки
(`http(s)://`, `mailto:`) не проверяет — CI не ходит в сеть.

Запуск: `uv run python tools/check_links.py [пути...]` (по умолчанию — весь репозиторий).
Код выхода 1, если есть битые ссылки.
"""

from __future__ import annotations

import re
import sys
from functools import cache
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {
    "node_modules",
    ".venv",
    ".git",
    "dist",
    "test-results",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}
# Архив хранится как есть: ссылки в нём не правим и не проверяем.
SKIP_PREFIXES = ("docs/archive/",)

LINK_RE = re.compile(r"(?<!!)\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
IMAGE_RE = re.compile(r"!\[[^\]\n]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HREF_RE = re.compile(r"""<a\s[^>]*href=["']([^"']+)["']""", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
ANCHOR_TAG_RE = re.compile(r"""<a\s[^>]*(?:name|id)=["']([^"']+)["']""", re.IGNORECASE)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def slug(text: str) -> str:
    """Якорь заголовка по правилам GitHub: нижний регистр, без пунктуации, пробел → `-`."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("`", "").strip().lower()
    text = "".join(ch for ch in text if ch.isalnum() or ch in " -_")
    return text.replace(" ", "-")


def strip_code(lines: list[str], *, inline: bool = True) -> list[str]:
    """Строки без блоков кода (и инлайн-кода при `inline`): ссылки в примерах не проверяем."""
    out, fenced = [], False
    for line in lines:
        if FENCE_RE.match(line):
            fenced = not fenced
            out.append("")
            continue
        out.append("" if fenced else INLINE_CODE_RE.sub("", line) if inline else line)
    return out


@cache
def anchors(path: Path) -> frozenset[str]:
    """Все якоря файла: слаги заголовков (с суффиксами `-1`, `-2` для повторов) и `<a id>`."""
    seen: dict[str, int] = {}
    result: set[str] = set()
    for line in strip_code(path.read_text(encoding="utf-8").splitlines(), inline=False):
        m = HEADING_RE.match(line)
        if m:
            base = slug(m.group(2))
            n = seen.get(base, 0)
            seen[base] = n + 1
            result.add(base if n == 0 else f"{base}-{n}")
        result.update(a.lower() for a in ANCHOR_TAG_RE.findall(line))
    return frozenset(result)


def check_target(src: Path, target: str) -> str | None:
    """Текст ошибки для ссылки или `None`, если она ведёт куда надо."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith("//"):
        return None  # http, mailto, tg и прочие схемы — наружу не ходим
    path_part, _, anchor = target.partition("#")
    path_part = unquote(path_part.split("?", 1)[0])
    anchor = unquote(anchor)
    dest = src if not path_part else (src.parent / path_part).resolve()
    if path_part.startswith("/"):
        dest = (ROOT / path_part.lstrip("/")).resolve()
    if not dest.exists():
        return f"нет файла {path_part}"
    if anchor and dest.is_file() and dest.suffix == ".md":
        if anchor.lower() not in anchors(dest) and not re.fullmatch(r"L\d+(-L\d+)?", anchor):
            return f"нет якоря #{anchor} в {dest.relative_to(ROOT).as_posix()}"
    return None


def iter_md(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_file():
            files.append(p)
            continue
        for f in p.rglob("*.md"):
            rel = f.relative_to(ROOT).as_posix()
            if SKIP_DIRS.intersection(f.relative_to(ROOT).parts) or rel.startswith(SKIP_PREFIXES):
                continue
            files.append(f)
    return sorted(files)


def check_file(path: Path) -> list[str]:
    errors = []
    lines = strip_code(path.read_text(encoding="utf-8").splitlines())
    for no, line in enumerate(lines, 1):
        targets = LINK_RE.findall(line) + IMAGE_RE.findall(line) + HREF_RE.findall(line)
        for target in targets:
            err = check_target(path, target)
            if err:
                errors.append(f"{path.relative_to(ROOT).as_posix()}:{no}: {target} — {err}")
    return errors


def main(argv: list[str]) -> int:
    roots = [Path(a).resolve() for a in argv] or [ROOT]
    files = iter_md(roots)
    errors = [e for f in files for e in check_file(f)]
    for e in errors:
        print(e)
    print(f"Проверено файлов: {len(files)}, битых ссылок: {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
