"""Реестр моделей для Alembic: импортируй сюда модули с таблицами core."""

from fsp_platform.db import Base
from fsp_platform.outbox import InboxRecord, OutboxRecord  # noqa: F401

from app.candidates.models import Candidate  # noqa: F401
from app.companies.models import Company, CompanyMember  # noqa: F401
from app.consents.models import Consent  # noqa: F401
from app.graph.models import CandidateSkill, Evidence  # noqa: F401
from app.identity.models import RefreshToken, User  # noqa: F401
from app.taxonomy import models as _taxonomy  # noqa: F401
from app.vacancies.models import Vacancy, VacancySkill  # noqa: F401

metadata = Base.metadata
