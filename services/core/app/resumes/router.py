from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fsp_contracts.enums import ConsentType
from fsp_contracts.ml import ParsedResume
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.candidates import service as candidates
from app.consents.deps import require_consent
from app.deps import get_limiter, get_session, get_storage
from app.identity.deps import require_roles
from app.identity.models import User
from app.resumes import service

router = APIRouter(prefix="/candidates/me/resumes", tags=["resumes"])

_owner = require_roles("candidate")
_writer = require_consent(ConsentType.pd_processing)


async def writer(user: User = Depends(_owner), _: User = Depends(_writer)) -> User:
    return user


class ResumeAccepted(BaseModel):
    resume_id: UUID
    job_id: UUID


class ResumeOut(BaseModel):
    status: Literal["queued", "parsing", "parsed", "confirmed", "failed"]
    parsed: ParsedResume | None = None
    error: str | None = None


class ConfirmIn(BaseModel):
    edits: service.ParsedResumeEdits = service.ParsedResumeEdits()


def _out(resume) -> ResumeOut:
    return ResumeOut(
        status=resume.status,
        parsed=ParsedResume.model_validate(resume.parsed) if resume.parsed else None,
        error=resume.error,
    )


@router.post("", status_code=202, response_model=ResumeAccepted)
async def upload_resume(
    request: Request,
    file: Annotated[UploadFile, File()],
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
    storage=Depends(get_storage),
    limiter=Depends(get_limiter),
):
    await limiter.check(f"resume:{user.id}", service.UPLOAD_LIMIT, service.UPLOAD_WINDOW)
    data = await file.read(service.MAX_BYTES + 1)
    if not getattr(request.app.state, "bucket_ready", False):  # лениво: MinIO не нужен для старта
        await storage.ensure_bucket()
        request.app.state.bucket_ready = True
    await candidates.get_or_create(session, user.id, request.app.state.settings.pseudo_id_secret)
    resume, job_id = await service.upload(session, storage, user.id, data)
    return ResumeAccepted(resume_id=resume.id, job_id=job_id)


@router.get("/{resume_id}", response_model=ResumeOut)
async def get_resume(
    resume_id: UUID,
    user: User = Depends(_owner),
    session: AsyncSession = Depends(get_session),
):
    return _out(await service.get_owned(session, user.id, resume_id))


@router.post("/{resume_id}/confirm", response_model=ResumeOut)
async def confirm_resume(
    resume_id: UUID,
    body: ConfirmIn | None = None,
    user: User = Depends(writer),
    session: AsyncSession = Depends(get_session),
):
    resume = await service.get_owned(session, user.id, resume_id)
    await service.confirm(session, resume, (body or ConfirmIn()).edits)
    return _out(resume)
