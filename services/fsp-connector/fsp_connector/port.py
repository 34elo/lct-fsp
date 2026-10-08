"""Порт ФСП (fsp.md §2). Адаптеры нормализуют ответы источника в DTO `fsp_contracts.fsp`."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from fsp_contracts.fsp import (
    FspCompetition,
    FspOAuthIdentity,
    FspParticipant,
    FspParticipantBrief,
    FspRank,
    FspResult,
    FspStandingRow,
    FspTeam,
    MaskedContact,
)


class FspPort(Protocol):
    async def get_participant(self, participant_id: str) -> FspParticipant: ...

    async def find_participant(
        self,
        *,
        email: str | None = None,
        last_name: str | None = None,
        birth_date: date | None = None,
    ) -> list[FspParticipantBrief]: ...

    async def get_results(
        self, participant_id: str, since: date | None = None
    ) -> list[FspResult]: ...

    async def get_ranks(self, participant_id: str) -> list[FspRank]: ...

    async def get_competitions(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        discipline: str | None = None,
    ) -> list[FspCompetition]: ...

    async def get_standings(self, competition_id: str) -> list[FspStandingRow]: ...

    async def get_team(self, team_id: str) -> FspTeam: ...

    # верификация
    async def send_verification_code(self, participant_id: str) -> MaskedContact: ...

    async def check_verification_code(self, participant_id: str, code: str) -> bool: ...

    # OAuth
    def authorize_url(self, state: str, code_challenge: str) -> str: ...

    async def exchange_code(self, code: str, code_verifier: str) -> FspOAuthIdentity: ...
