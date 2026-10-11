"""Маппинги источников ФСП: сырой JSON → наши DTO.

Различия схем источников закрываются здесь, а не в адаптере: переименование полей,
перевод значений перечислений, вычисление `participants_total`, если его нет.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fsp_contracts.fsp import (
    FspCompetition,
    FspOAuthIdentity,
    FspParticipant,
    FspParticipantBrief,
    FspResult,
    FspStandingRow,
    FspTeam,
)

Raw = dict[str, Any]


@dataclass(frozen=True)
class Mapping:
    """Набор функций нормализации одного источника. По умолчанию — наша схема (мок)."""

    participant: Callable[[Raw], FspParticipant] = FspParticipant.model_validate
    brief: Callable[[Raw], FspParticipantBrief] = FspParticipantBrief.model_validate
    result: Callable[[Raw], FspResult] = FspResult.model_validate
    competition: Callable[[Raw], FspCompetition] = FspCompetition.model_validate
    standing: Callable[[Raw], FspStandingRow] = FspStandingRow.model_validate
    team: Callable[[Raw], FspTeam] = FspTeam.model_validate
    identity: Callable[[Raw], FspOAuthIdentity] = FspOAuthIdentity.model_validate
    # пути, если источник называет их иначе: {наш путь: путь источника}
    paths: dict[str, str] = field(default_factory=dict)


MOCK = Mapping()

MAPPINGS: dict[str, Mapping] = {"mock": MOCK}


def get_mapping(source: str) -> Mapping:
    try:
        return MAPPINGS[source]
    except KeyError:
        raise KeyError(f"нет маппинга для источника {source!r}") from None
