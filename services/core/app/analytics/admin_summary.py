"""Сводка «Что требует вас» на главной админки.

Только счётчики очередей, где нужно решение человека. Всё остальное (тест, грейд, подбор,
калибровка, сила) работает само и сюда не попадает. Без ПДн.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Request
from fsp_platform.app import ProblemError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import service as assessment
from app.companies import service as companies
from app.fsp import service as fsp
from app.fsp.router import get_connector
from app.offers import service as offers
from app.taxonomy import service as taxonomy

QueueId = Literal["fsp_requests", "families", "skills", "companies", "complaints"]


class QueueCount(BaseModel):
    id: QueueId
    count: int | None = None  # None — источник сейчас недоступен (fsp-connector)


class AdminSummaryOut(BaseModel):
    queues: list[QueueCount]
    total: int  # сумма известных счётчиков


async def _fsp_requests(request: Request) -> int | None:
    try:
        return await fsp.pending_requests_count(get_connector(request))
    except ProblemError:
        return None


async def build(session: AsyncSession, request: Request) -> AdminSummaryOut:
    queues = [
        QueueCount(id="fsp_requests", count=await _fsp_requests(request)),
        QueueCount(id="families", count=await assessment.count_families(session, "pilot")),
        QueueCount(id="skills", count=await taxonomy.pending_merge_count(session)),
        QueueCount(id="companies", count=await companies.count_by_status(session, "pending")),
        QueueCount(id="complaints", count=await offers.count_complaints(session, "open")),
    ]
    return AdminSummaryOut(queues=queues, total=sum(q.count or 0 for q in queues))
