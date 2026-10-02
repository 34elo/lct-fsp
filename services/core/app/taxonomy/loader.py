"""Чтение и проверка YAML ядра графа навыков (`data/taxonomy/*.yaml`) и правил ФСП.

Формат (поддерживаются любые файлы `*.yaml`, ключи верхнего уровня сливаются, остальное
игнорируется — например, `package_map.yaml` читает только ml):

    skills:      [{slug, name, kind: hard|soft|domain, group?, testable?, description?, aliases?}]
    adjacent:    [{a, b, weight}]            # смежность, симметрична
    parent:      [{child, parent, weight}]   # иерархия, коэффициент наследования
    distinct:    [[a, b], ...]               # «точно разные»
    blocklist:   [{norm, reason?}]
    roles:       [{slug, name, skills: {slug: weight}}]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from fsp_contracts.enums import RoleSlug
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SKILL_KINDS = ("hard", "soft", "domain")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_.+#-]*$")


class TaxonomyError(ValueError):
    """YAML справочника не прошёл проверку."""


def norm_alias(text: str) -> str:
    """Лёгкая нормализация синонима: нижний регистр, ё → е, пробелы схлопнуты.

    Полная нормализация упоминаний (версии, лемматизация) живёт в конвейере ml.
    """
    return " ".join(text.lower().replace("ё", "е").split())


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkillIn(_Strict):
    slug: str
    name: str = Field(min_length=1)
    kind: str
    group: str | None = None
    testable: bool = False
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not _SLUG.match(v):
            raise ValueError(f"недопустимый slug {v!r}")
        return v

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in SKILL_KINDS:
            raise ValueError(f"kind должен быть один из {SKILL_KINDS}")
        return v


class AdjacentIn(_Strict):
    a: str
    b: str
    weight: float = Field(ge=0, le=1)


class ParentIn(_Strict):
    child: str
    parent: str
    weight: float = Field(ge=0, le=1)


class BlockIn(_Strict):
    norm: str
    reason: str | None = None


class RoleIn(_Strict):
    slug: str
    name: str = Field(min_length=1)
    skills: dict[str, float] = Field(default_factory=dict)

    @field_validator("slug")
    @classmethod
    def _role(cls, v: str) -> str:
        RoleSlug(v)  # роль должна быть в контракте
        return v

    @field_validator("skills")
    @classmethod
    def _weights(cls, v: dict[str, float]) -> dict[str, float]:
        for k, w in v.items():
            if not 0 <= w <= 1:
                raise ValueError(f"вес {k}={w} вне 0..1")
        return v


@dataclass
class TaxonomyData:
    skills: list[SkillIn] = field(default_factory=list)
    adjacent: list[AdjacentIn] = field(default_factory=list)
    parent: list[ParentIn] = field(default_factory=list)
    distinct: list[tuple[str, str]] = field(default_factory=list)
    blocklist: list[BlockIn] = field(default_factory=list)
    roles: list[RoleIn] = field(default_factory=list)
    # дисциплина → [(slug навыка, вес, трек|None)]
    discipline_rules: dict[str, list[tuple[str, float, str | None]]] = field(default_factory=dict)


def _merge_yaml(directory: Path) -> dict[str, list]:
    merged: dict[str, list] = {}
    for path in sorted(directory.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(doc, dict):
            raise TaxonomyError(f"{path.name}: ожидается словарь верхнего уровня")
        for key in ("skills", "adjacent", "parent", "distinct", "blocklist", "roles"):
            if key in doc:
                if not isinstance(doc[key], list):
                    raise TaxonomyError(f"{path.name}: {key} должен быть списком")
                merged.setdefault(key, []).extend(doc[key])
    return merged


def _build(model: type[BaseModel], items: list[Any], what: str) -> list:
    out = []
    for i, item in enumerate(items):
        try:
            out.append(model.model_validate(item))
        except ValidationError as exc:
            raise TaxonomyError(f"{what}[{i}]: {exc.errors()[0]['msg']} ({item!r})") from exc
    return out


def parse_discipline_rules(path: Path) -> dict[str, list[tuple[str, float, str | None]]]:
    """`discipline_rules.yaml`: дисциплина → {навык: вес} и `tracks: {трек: {навык: вес}}`."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, list[tuple[str, float, str | None]]] = {}
    for disc, body in doc.items():
        if not isinstance(body, dict):
            raise TaxonomyError(f"{path.name}: {disc} должен быть словарём")
        rules: list[tuple[str, float, str | None]] = []
        for key, val in body.items():
            if key == "tracks":
                for track, tskills in (val or {}).items():
                    rules += [(s, float(w), str(track)) for s, w in tskills.items()]
            else:
                rules.append((str(key), float(val), None))
        for s, w, _ in rules:
            if not 0 <= w <= 1:
                raise TaxonomyError(f"{disc}.{s}: вес {w} вне 0..1")
        out[str(disc)] = rules
    return out


def load_taxonomy(directory: Path, discipline_rules: Path | None = None) -> TaxonomyData:
    """Читает и проверяет справочник целиком. Любая ошибка — `TaxonomyError`, БД не трогаем."""
    if not directory.is_dir():
        raise TaxonomyError(f"нет каталога {directory}")
    raw = _merge_yaml(directory)
    data = TaxonomyData(
        skills=_build(SkillIn, raw.get("skills", []), "skills"),
        adjacent=_build(AdjacentIn, raw.get("adjacent", []), "adjacent"),
        parent=_build(ParentIn, raw.get("parent", []), "parent"),
        blocklist=_build(BlockIn, raw.get("blocklist", []), "blocklist"),
        roles=_build(RoleIn, raw.get("roles", []), "roles"),
    )
    for i, pair in enumerate(raw.get("distinct", [])):
        if not (isinstance(pair, list | tuple) and len(pair) == 2):
            raise TaxonomyError(f"distinct[{i}]: ожидается пара [a, b]")
        data.distinct.append((str(pair[0]), str(pair[1])))
    if discipline_rules is not None and discipline_rules.exists():
        data.discipline_rules = parse_discipline_rules(discipline_rules)
    _validate(data)
    return data


def _validate(d: TaxonomyData) -> None:
    slugs: set[str] = set()
    for s in d.skills:
        if s.slug in slugs:
            raise TaxonomyError(f"дубликат навыка {s.slug}")
        slugs.add(s.slug)
    owner: dict[str, str] = {}
    for s in d.skills:
        for alias in {norm_alias(a) for a in s.aliases} | {norm_alias(s.name), norm_alias(s.slug)}:
            if not alias:
                raise TaxonomyError(f"{s.slug}: пустой синоним")
            if owner.setdefault(alias, s.slug) != s.slug:
                raise TaxonomyError(f"синоним {alias!r} у {owner[alias]} и {s.slug}")
    blocked = {norm_alias(b.norm) for b in d.blocklist}
    if clash := blocked & owner.keys():
        raise TaxonomyError(f"стоп-лист содержит синоним навыка: {sorted(clash)}")

    def need(slug: str, where: str) -> None:
        if slug not in slugs:
            raise TaxonomyError(f"{where}: неизвестный навык {slug}")

    seen_adj: set[frozenset[str]] = set()
    for r in d.adjacent:
        need(r.a, "adjacent"), need(r.b, "adjacent")
        if r.a == r.b:
            raise TaxonomyError(f"adjacent: петля {r.a}")
        if (key := frozenset((r.a, r.b))) in seen_adj:
            raise TaxonomyError(f"adjacent: дубликат пары {r.a}/{r.b}")
        seen_adj.add(key)
    parents: dict[str, str] = {}
    for p in d.parent:
        need(p.child, "parent"), need(p.parent, "parent")
        if p.child == p.parent:
            raise TaxonomyError(f"parent: петля {p.child}")
        if p.child in parents:
            raise TaxonomyError(f"parent: у {p.child} два родителя")
        parents[p.child] = p.parent
    for start in parents:  # иерархия без циклов
        cur, hops = start, 0
        while cur in parents:
            cur, hops = parents[cur], hops + 1
            if cur == start or hops > len(parents):
                raise TaxonomyError(f"parent: цикл через {start}")
    for a, b in d.distinct:
        need(a, "distinct"), need(b, "distinct")
        if a == b:
            raise TaxonomyError(f"distinct: пара из одного навыка {a}")
    for role in d.roles:
        for s in role.skills:
            need(s, f"roles.{role.slug}")
    if len({r.slug for r in d.roles}) != len(d.roles):
        raise TaxonomyError("roles: дубликат роли")
