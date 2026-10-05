"""Реестр моделей для Alembic: импортируй сюда модули с таблицами core."""

from fsp_platform.db import Base
from fsp_platform.outbox import InboxRecord, OutboxRecord  # noqa: F401

from app.analytics.models import AnalyticsEventRow  # noqa: F401

# >>> block1 (assessment, taxonomy, identity, candidates, graph, resumes)
from app.assessment.models import Grade  # noqa: F401
from app.candidates.models import Candidate, CategoryDispute  # noqa: F401
from app.companies.models import Company, CompanyMember  # noqa: F401
from app.consents.models import Consent  # noqa: F401
from app.graph import fsp_models as _fsp  # noqa: F401
from app.graph.models import CandidateSkill, Evidence  # noqa: F401
from app.identity.models import RefreshToken, User  # noqa: F401
from app.matching.models import Match  # noqa: F401
from app.notifications.models import Notification  # noqa: F401
from app.offers.models import (  # noqa: F401
    Complaint,
    ContactReveal,
    Offer,
    OfferEvent,
    OfferMessage,
)
from app.resumes.models import Education, Experience, Resume  # noqa: F401
from app.taxonomy import models as _taxonomy  # noqa: F401
from app.telegram.models import TelegramAccount  # noqa: F401
from app.vacancies.models import Vacancy, VacancySkill  # noqa: F401
from app.views.models import ProfileView  # noqa: F401

# <<< block1
# >>> block2 (matching, offers, vacancies, companies, consents, fsp, telegram, analytics)
# <<< block2

metadata = Base.metadata
