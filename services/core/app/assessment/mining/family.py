"""Семейство из майнинга мутаций (`families.source = mutation`).

`families.spec` = `{"mined": <запись банка>, "project": {...}, "digest": …}`. Вариант по сиду —
один из убитых мутантов функции; ключ — номер изменённой строки (известен по построению,
мутант доказанно убит тестом проекта). При выдаче ничего не исполняется.
"""

from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING, Any

from fsp_contracts.assessment import SkillType

from app.assessment.families.base import SCORERS, Item, Kind

if TYPE_CHECKING:
    from app.assessment.world import World


class MinedFamily:
    """Реализует протокол `Family`: `find_bug` по функции открытого проекта."""

    kind = Kind.find_bug

    def __init__(
        self,
        mined: dict[str, Any],
        project: dict[str, Any],
        *,
        slug: str,
        skill: str = "python",
        skill_type: SkillType | str = SkillType.hard,
        anchor: bool = False,
    ) -> None:
        if not mined.get("mutants"):
            raise ValueError(f"{slug}: нет мутантов")
        self.mined = mined
        self.project = project
        self.slug = slug
        self.skill = skill
        self.skill_type = SkillType(skill_type)
        self.level = int(mined["level"])
        self.anchor = anchor
        self.knob_bounds: dict[str, tuple[float, float]] = {}

    @classmethod
    def from_row(cls, row: Any) -> MinedFamily:
        spec = row.spec or {}
        return cls(
            spec["mined"],
            spec.get("project", {}),
            slug=row.slug,
            skill=spec.get("skill", "python"),
            skill_type=row.skill_type,
            anchor=bool(row.anchor),
        )

    def generate(self, rng: Random, world: World) -> Item:  # noqa: ARG002 - код проекта не перекрашивается
        m = self.mined
        mut = rng.choice(m["mutants"])
        lines = list(m["lines"])
        lines[mut["line"] - 1] = mut["text"]
        listing = "\n".join(f"{i:>2} | {ln}" for i, ln in enumerate(lines, 1))
        p = self.project
        purpose = f" Назначение по документации проекта: «{m['doc']}»." if m.get("doc") else ""
        kill = mut["kill"]
        stem = (
            f"Функция `{m['function']}` из открытого проекта {p.get('name', '')} "
            f"({p.get('license', '')}, файл {m['module']}).{purpose}\n"
            f"В одной строке допущена ошибка: тест `{kill['call']}` ожидает {kill['expected']}, "
            f"но не проходит. Укажите номер строки с дефектом.\n\n{listing}"
        )
        return Item(
            kind=Kind.find_bug,
            stem=stem,
            key=[mut["line"]],
            time_limit_s=150 + 30 * max(0, self.level - 2),
            meta={"mutant_op": mut["op"], "origin": kill.get("origin")},
        )

    def score(self, item: Item, answer: Any) -> float:
        return SCORERS[item.kind](item.key, answer)
