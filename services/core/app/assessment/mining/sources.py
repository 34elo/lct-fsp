"""Источники для майнинга (E30-3): список проектов, лицензия, загрузка архива с GitHub.

Список — `data/questions/mutations/sources.yaml`. Наружу ходим только в GitHub и только при
`MUTMINE_GITHUB=1` (токен — необязательный `GITHUB_TOKEN` из окружения). Без этого майнинг
работает по локальному каталогу (`--dir`). Из архива распаковываются только `.py` и файлы
лицензии: без ссылок, без выхода из каталога, с лимитами размера. Ничего не исполняется.
"""

from __future__ import annotations

import io
import os
import re
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

from app.assessment.mining.bank import Project

ROOT = Path(__file__).resolve().parents[5]
SOURCES = ROOT / "data" / "questions" / "mutations" / "sources.yaml"
BANK_DIR = SOURCES.parent
MAX_ARCHIVE = 200 * 1024 * 1024
MAX_MEMBER = 1024 * 1024
ALLOWED_LICENSES = ("MIT", "Apache-2.0")
_LICENSE_FILE = re.compile(r"^(LICEN[CS]E|COPYING)(\.(md|txt|rst))?$", re.I)


class SourceError(RuntimeError):
    """Источник нельзя использовать: нет сети, не та лицензия, плохой архив."""


@dataclass(frozen=True)
class Source:
    project: Project
    include: list[str] = field(default_factory=list)


def load_sources(path: Path = SOURCES) -> dict[str, Source]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for s in raw.get("sources", []):
        if s["license"] not in ALLOWED_LICENSES:
            raise SourceError(f"{s['name']}: лицензия {s['license']} не из {ALLOWED_LICENSES}")
        out[s["name"]] = Source(
            Project(
                name=s["name"],
                repo=s["repo"],
                ref=str(s["ref"]),
                license=s["license"],
                url=f"https://github.com/{s['repo']}",
            ),
            include=list(s.get("include") or []),
        )
    return out


def detect_license(root: Path) -> str | None:
    """MIT или Apache-2.0 по тексту файла лицензии в корне; иначе None."""
    for p in sorted(root.iterdir()):
        if not p.is_file() or not _LICENSE_FILE.match(p.name):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")[:20_000]
        if "Permission is hereby granted, free of charge" in text:
            return "MIT"
        if "Apache License" in text and "Version 2.0" in text:
            return "Apache-2.0"
    return None


def require_license(root: Path, expected: str) -> None:
    got = detect_license(root)
    if got != expected:
        raise SourceError(f"лицензия проекта {got or 'не найдена'}, ожидалась {expected}")


def _safe_member(m: tarfile.TarInfo) -> PurePosixPath | None:
    """Путь внутри архива без верхнего каталога `owner-repo-sha/`; None — пропустить."""
    if not m.isfile() or m.size > MAX_MEMBER:
        return None
    parts = PurePosixPath(m.name).parts[1:]
    if not parts or any(p in ("", ".", "..") for p in parts) or m.name.startswith("/"):
        return None
    rel = PurePosixPath(*parts)
    if rel.suffix == ".py" or (len(parts) == 1 and _LICENSE_FILE.match(parts[0])):
        return rel
    return None


def unpack(data: bytes, dest: Path) -> int:
    """Распаковать `.py` и лицензию из tar.gz; вернуть число файлов."""
    n = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar:
            rel = _safe_member(m)
            if rel is None:
                continue
            f = tar.extractfile(m)
            if f is None:
                continue
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(f.read(MAX_MEMBER + 1)[:MAX_MEMBER])
            n += 1
    return n


def fetch(src: Source, cache: Path | None = None) -> Path:
    """Скачать архив `repo@ref` с GitHub (только при `MUTMINE_GITHUB=1`) в кеш."""
    if os.environ.get("MUTMINE_GITHUB") != "1":
        raise SourceError("сеть выключена: задайте MUTMINE_GITHUB=1 или укажите --dir")
    p = src.project
    cache = cache or Path(os.environ.get("MUTMINE_CACHE", tempfile.gettempdir())) / "fsp-mutmine"
    dest = cache / f"{p.name}-{re.sub(r'[^A-Za-z0-9._-]', '_', p.ref)}"
    if dest.exists() and any(dest.iterdir()):
        return dest
    url = f"https://api.github.com/repos/{p.repo}/tarball/{p.ref}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})  # noqa: S310
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - только api.github.com
        data = resp.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise SourceError("архив больше лимита")
    dest.mkdir(parents=True, exist_ok=True)
    unpack(data, dest)
    return dest
