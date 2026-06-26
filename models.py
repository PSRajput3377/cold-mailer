"""Domain models shared across the application.

These are plain dataclasses with no behaviour beyond light validation and
convenience accessors. Keeping them dependency-free makes them trivial to
construct in tests and to serialize for logging.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Designation(str, Enum):
    """Recognised recipient roles. Inherits from ``str`` so values compare and
    serialize naturally (e.g. JSON / CSV)."""

    HR = "HR"
    RECRUITER = "Recruiter"
    TALENT_ACQUISITION = "Talent Acquisition"
    ENGINEERING_MANAGER = "Engineering Manager"
    SOFTWARE_ENGINEER = "Software Engineer"
    FOUNDER = "Founder"

    @classmethod
    def from_str(cls, value: str) -> "Designation":
        """Lenient parse: case-insensitive, tolerant of underscores/dashes."""
        if isinstance(value, cls):
            return value
        norm = str(value).strip().lower().replace("_", " ").replace("-", " ")
        for member in cls:
            if member.value.lower() == norm:
                return member
        # A few common aliases.
        aliases = {
            "talent": cls.TALENT_ACQUISITION,
            "ta": cls.TALENT_ACQUISITION,
            "em": cls.ENGINEERING_MANAGER,
            "swe": cls.SOFTWARE_ENGINEER,
            "engineer": cls.SOFTWARE_ENGINEER,
            "ceo": cls.FOUNDER,
            "co-founder": cls.FOUNDER,
            "cofounder": cls.FOUNDER,
        }
        if norm in aliases:
            return aliases[norm]
        raise ValueError(f"Unknown designation: {value!r}")


@dataclass
class Candidate:
    """The person *sending* the cold emails (i.e. the job-seeker)."""

    full_name: str
    email: str
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    phone: str = ""
    preferred_role: str = "Software Engineer"

    # Pulled from the resume by the generator/attachment parser.
    resume_path: Optional[str] = None
    resume_highlights: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    recent_internship: str = ""

    @property
    def first_name(self) -> str:
        return self.full_name.split()[0] if self.full_name else ""


@dataclass
class Recipient:
    """A single target contact at a company."""

    company_name: str
    person_first_name: str
    person_last_name: str
    designation: Designation
    company_domain: Optional[str] = None

    # Job context (all optional).
    job_title: str = ""
    job_id: str = ""
    job_url: str = ""

    # Job-board (ATS) source, optional — used to auto-fill job context and to
    # feed the AI generator a real job description.
    ats_vendor: Optional[str] = None     # greenhouse | lever | ashby
    ats_board_token: Optional[str] = None
    job_description: str = ""

    # Filled in by the pipeline.
    resolved_domain: Optional[str] = None
    candidate_emails: list[str] = field(default_factory=list)
    chosen_email: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.designation, Designation):
            self.designation = Designation.from_str(self.designation)

    @property
    def person_full_name(self) -> str:
        return f"{self.person_first_name} {self.person_last_name}".strip()

    @property
    def domain(self) -> Optional[str]:
        """Best-known domain: explicit > resolved."""
        return self.company_domain or self.resolved_domain
