"""Steps 4 & 5 — assemble the placeholder context for a recipient.

Every template and subject is rendered against the dict produced here. This is
the single source of truth for what ``{{first_name}}``, ``{{company}}``,
``{{resume}}`` etc. resolve to, guaranteeing that every email automatically
carries the company name, person name, role, job title/id, resume highlights,
skills, internship, portfolio, GitHub and LinkedIn (Step 4).
"""
from __future__ import annotations

from typing import Any, Optional

from models import Candidate, Recipient


def _parse_job_urls(job_url: str) -> list[str]:
    """Split one or more job URLs from a CSV cell (| or ; separated)."""
    raw = (job_url or "").strip()
    if not raw:
        return []
    for sep in ("|", ";"):
        if sep in raw:
            return [u.strip() for u in raw.split(sep) if u.strip()]
    return [raw]


def build_context(candidate: Candidate, recipient: Recipient) -> dict[str, Any]:
    """Return the full placeholder context for one (candidate, recipient)."""
    role = recipient.job_title or candidate.preferred_role or "Software Engineer"

    highlights = candidate.resume_highlights or []
    skills = candidate.skills or []

    ctx: dict[str, Any] = {
        # -- person (recipient) --
        "first_name": recipient.person_first_name,
        "last_name": recipient.person_last_name,
        "full_name": recipient.person_full_name,
        "designation": recipient.designation.value,
        # -- company / job --
        "company": recipient.company_name,
        "domain": recipient.domain or "",
        "job_title": recipient.job_title or role,
        "role": role,
        "job_id": recipient.job_id or "",
        "job_url": recipient.job_url or "",
        "job_urls_list": _parse_job_urls(recipient.job_url or ""),
        # -- candidate (sender) --
        "candidate_name": candidate.full_name,
        "candidate_email": candidate.email,
        "candidate_first_name": candidate.first_name,
        "preferred_role": candidate.preferred_role,
        "linkedin": candidate.linkedin_url,
        "github": candidate.github_url,
        "portfolio": candidate.portfolio_url,
        "phone": candidate.phone,
        # -- resume-derived (Step 4) --
        "skills": ", ".join(skills),
        "skills_list": skills,
        "resume_highlights": _bullets(highlights),
        "resume_highlights_list": highlights,
        "top_highlight": highlights[0] if highlights else "",
        "recent_internship": candidate.recent_internship,
        # convenience alias used by some templates
        "resume": _bullets(highlights) if highlights else candidate.preferred_role,
    }
    return ctx


def _bullets(items: list[str]) -> str:
    """Render a list as dash bullets for inline use in a plain-text email."""
    return "\n".join(f"- {item}" for item in items)
