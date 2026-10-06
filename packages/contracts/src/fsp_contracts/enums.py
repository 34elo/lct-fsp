"""Перечисления, общие для бэка, фронта и ML (data-model.md §1).

⚠️ Значения ФСП (`FspDiscipline`, `FspLevel`, `FspRankCode`) — предположение до ответа организаторов.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class UserRole(StrEnum):
    candidate = "candidate"
    employer = "employer"
    fsp_admin = "fsp_admin"


class CompanyMemberRole(StrEnum):
    admin = "admin"
    member = "member"


class Grade(StrEnum):
    intern = "intern"
    junior = "junior"
    junior_plus = "junior_plus"
    middle = "middle"
    middle_plus = "middle_plus"
    senior = "senior"
    lead = "lead"

    @property
    def order(self) -> int:
        """Порядок 0…6 для сравнения грейдов."""
        return _GRADE_ORDER[self]


_GRADE_ORDER = {g: i for i, g in enumerate(Grade)}


class RoleSlug(StrEnum):
    backend = "backend"
    frontend = "frontend"
    fullstack = "fullstack"
    mobile = "mobile"
    ml = "ml"
    data_engineer = "data_engineer"
    devops = "devops"
    qa = "qa"
    security = "security"
    gamedev = "gamedev"
    embedded = "embedded"
    analyst = "analyst"
    product = "product"
    designer = "designer"


class WorkFormat(StrEnum):
    office = "office"
    hybrid = "hybrid"
    remote = "remote"


class EmploymentType(StrEnum):
    full = "full"
    part = "part"
    internship = "internship"
    project = "project"


class SearchStatus(StrEnum):
    active = "active"
    open = "open"
    dnd = "dnd"


class EvidenceSource(StrEnum):
    self_ = "self"
    resume = "resume"
    github = "github"
    test = "test"
    ai_interview = "ai_interview"
    fsp = "fsp"
    codeforces = "codeforces"


class SkillKind(StrEnum):
    hard = "hard"
    soft = "soft"
    domain = "domain"


class SkillStatus(StrEnum):
    provisional = "provisional"
    active = "active"
    merged = "merged"
    rejected = "rejected"


class RelationKind(StrEnum):
    adjacent = "adjacent"
    parent = "parent"


class RelationSource(StrEnum):
    seed = "seed"
    judge = "judge"
    cooccurrence = "cooccurrence"
    admin = "admin"


class TeamSignalKind(StrEnum):
    leadership = "leadership"
    teamwork = "teamwork"
    results = "results"
    growth = "growth"


class TrustLevel(IntEnum):
    """○○○○ … ●●●●"""

    l0 = 0
    l1 = 1
    l2 = 2
    l3 = 3
    l4 = 4


class OfferStatus(StrEnum):
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    withdrawn = "withdrawn"
    interview = "interview"
    hired = "hired"
    not_hired = "not_hired"
    # ADR-026 (E33-1): интерес — шаг до приглашения; `interest_opened` — кандидат открыл интерес
    interest = "interest"
    interest_opened = "interest_opened"


class DeclineReason(StrEnum):
    low_salary = "low_salary"
    wrong_stack = "wrong_stack"
    wrong_format = "wrong_format"
    wrong_grade = "wrong_grade"
    not_looking = "not_looking"
    other = "other"
    wrong_company = "wrong_company"  # «не интересно»: компания (E33-1)


class ConsentType(StrEnum):
    pd_processing = "pd_processing"
    fsp_data = "fsp_data"
    code_analysis = "code_analysis"
    telegram_notifications = "telegram_notifications"
    public_profile = "public_profile"
    profile_publication = "profile_publication"


class FspDiscipline(StrEnum):
    algorithmic = "algorithmic"
    product = "product"
    security = "security"
    uav = "uav"
    robotics = "robotics"


class FspLevel(StrEnum):
    regional = "regional"
    interregional = "interregional"
    national = "national"
    international = "international"


class FspRankCode(StrEnum):
    youth_3 = "youth_3"
    youth_2 = "youth_2"
    youth_1 = "youth_1"
    rank_3 = "rank_3"
    rank_2 = "rank_2"
    rank_1 = "rank_1"
    cms = "cms"
    ms = "ms"
    msic = "msic"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class CompanyStatus(StrEnum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"
    blocked = "blocked"
