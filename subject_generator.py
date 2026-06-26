"""Step 6 — subject-line generation (100+ variations).

Rather than hard-coding 100 literal strings, subjects are built from a pool of
parameterised patterns rendered against the email context. This keeps every
subject personalised (role, company, job id) while still yielding well over a
hundred distinct variations. A few dozen fixed "evergreen" subjects are mixed
in for variety.
"""
from __future__ import annotations

import random
from typing import Any, Optional

# Parameterised patterns. Placeholders are filled from the context dict.
# Patterns referencing {job_id} are only used when a job id is present.
_PATTERNS_GENERAL = [
    "{role} Application",
    "Application for {role} Position",
    "Interested in the {role} Role at {company}",
    "Seeking {role} Opportunities at {company}",
    "{role} — {candidate_name}",
    "Application: {role} at {company}",
    "Exploring {role} Roles at {company}",
    "{candidate_name} — {role} Candidate",
    "Re: {role} Opportunities at {company}",
    "{role} at {company} — Quick Note",
    "Keen on the {role} Opening at {company}",
    "{company} {role} — Introduction",
    "Application for the {role} Team at {company}",
    "{role} Role — Would Love to Connect",
    "Strong Fit for {company}'s {role} Role",
    "{candidate_name} — Interested in {company}",
    "{role} Candidate Reaching Out — {company}",
    "Eager to Join {company} as a {role}",
    "{role} Opportunity at {company}?",
    "Introducing Myself — {role} at {company}",
    "Excited About the {role} Role at {company}",
    "{candidate_name}: {role} Application for {company}",
    "Would Love to Contribute as a {role} at {company}",
    "{role} — Reaching Out to {company}",
    "A Quick Note on the {role} Role",
]

_PATTERNS_REFERRAL = [
    "Referral Request — {role} at {company}",
    "Quick Referral Request for {company}",
    "Referral for the {role} Role at {company}",
    "Would You Refer Me for {role} at {company}?",
    "Seeking a Referral — {company} {role}",
    "Referral Request: {candidate_name} for {company}",
    "A Small Ask — Referral for {company}",
    "Hoping for a Referral at {company}",
    "Could You Refer Me at {company}?",
    "Referral Help for the {role} Role",
    "A Quick Referral Ask — {company}",
    "Open to Referring Me for {role} at {company}?",
]

_PATTERNS_JOBID = [
    "Referral for Job ID {job_id}",
    "Application for Job ID {job_id} — {role}",
    "{role} (Job ID {job_id}) at {company}",
    "Regarding Job ID {job_id} at {company}",
    "Job ID {job_id} — {candidate_name}",
    "Interested in Job ID {job_id} ({role})",
]

_PATTERNS_FOLLOWUP = [
    "Following Up — {role} Application at {company}",
    "Quick Follow-Up on My {company} Application",
    "Re: {role} Application — {candidate_name}",
    "Checking In on the {role} Role at {company}",
    "Following Up After Applying to {company}",
    "Touching Base — {role} at {company}",
    "Following Up on Our Conversation — {company}",
    "Re: {role} at {company}",
    "Still Keen on the {role} Role at {company}",
    "Quick Note Following My {company} Application",
]

_PATTERNS_CHAT = [
    "Quick Question Regarding Hiring at {company}",
    "Request for a Quick Chat — {company} Engineering",
    "15 Minutes to Chat About {company}?",
    "Informational Chat About {role} at {company}",
    "Curious About Engineering at {company}",
    "Could We Chat About {company}?",
    "A Quick Question About {role} at {company}",
    "Learning More About {company}'s Team",
    "Open to a Short Call About {company}?",
    "Coffee Chat About Engineering at {company}?",
]

# Fixed evergreen subjects (no personalisation needed) — adds raw variety.
_EVERGREEN = [
    "Software Engineer Application",
    "Referral Request",
    "Interested in Backend Engineer Role",
    "Application for SDE Position",
    "Seeking SWE Opportunities",
    "Quick Question Regarding Hiring",
    "New Grad Software Engineer",
    "Frontend Engineer — Application",
    "Full-Stack Engineer Opportunity",
    "Exploring Engineering Roles",
    "SDE New Grad — Application",
    "Software Engineering Opportunity",
    "Backend Role — Quick Note",
    "Engineering Opportunities — Introduction",
    "Reaching Out About Engineering Roles",
    "Open to a Quick Chat?",
    "Application — Software Developer",
    "Interested in Joining Your Team",
    "Software Engineer — New Grad",
    "Resume for Your Consideration",
    "Aspiring Software Engineer — Introduction",
    "Interested in Frontend Roles",
    "Interested in Full-Stack Roles",
    "SWE Internship to Full-Time — Application",
    "Backend Engineer Application",
    "Platform Engineer Opportunity",
    "Exploring SDE Roles",
    "Software Engineer — Open to Opportunities",
    "Quick Intro — Software Engineer",
    "Referral Request — New Grad SWE",
    "Would Love to Join Your Engineering Team",
    "Checking In on Engineering Roles",
    "Junior Software Engineer — Application",
    "Distributed Systems Engineer Opportunity",
    "Software Engineer (New Grad) — Resume Attached",
    "Reaching Out About a SWE Role",
    "Interested in Joining as an Engineer",
    "Application — Backend / Full-Stack Engineer",
    "Hoping to Connect About Engineering Roles",
    "Quick Note From a Software Engineer",
    "Exploring Opportunities on Your Team",
    "Software Developer — Open to New Roles",
    "A Brief Introduction — Software Engineer",
    "Interested in Contributing to Your Team",
]


class SubjectGenerator:
    """Generates and renders subject-line variations."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)

    def all_patterns(self, has_job_id: bool) -> list[str]:
        """Return the full pool of pattern templates applicable to a context."""
        pool = (
            _PATTERNS_GENERAL
            + _PATTERNS_REFERRAL
            + _PATTERNS_FOLLOWUP
            + _PATTERNS_CHAT
        )
        if has_job_id:
            pool = pool + _PATTERNS_JOBID
        return pool

    def variations(self, context: dict[str, Any]) -> list[str]:
        """All concrete subjects for a context (deduped). Easily 100+."""
        has_job_id = bool(context.get("job_id"))
        rendered = [self._safe_format(p, context) for p in self.all_patterns(has_job_id)]
        rendered += _EVERGREEN
        # De-dupe while preserving order.
        seen, out = set(), []
        for s in rendered:
            s = s.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def generate(self, context: dict[str, Any], category: Optional[str] = None,
                 rng: Optional[random.Random] = None) -> str:
        """Pick one subject, biased toward the email's category when given."""
        r = rng or self._rng
        has_job_id = bool(context.get("job_id"))

        category_pools = {
            "referral_request": _PATTERNS_REFERRAL,
            "applied_requesting_referral": _PATTERNS_REFERRAL + _PATTERNS_JOBID,
            "followup_after_application": _PATTERNS_FOLLOWUP,
            "followup_after_recruiter": _PATTERNS_FOLLOWUP,
            "informational_chat": _PATTERNS_CHAT,
        }
        pool = category_pools.get(category or "", _PATTERNS_GENERAL)
        if has_job_id and r.random() < 0.4:
            pool = pool + _PATTERNS_JOBID
        chosen = r.choice(pool)
        return self._safe_format(chosen, context)

    @staticmethod
    def _safe_format(pattern: str, context: dict[str, Any]) -> str:
        """Format ignoring missing keys (they collapse to empty string)."""
        class _Default(dict):
            def __missing__(self, key):  # noqa: D401
                return ""
        # Normalise the few keys our patterns reference.
        ctx = _Default(
            role=context.get("role") or context.get("job_title") or "Software Engineer",
            company=context.get("company", ""),
            job_id=context.get("job_id", ""),
            candidate_name=context.get("candidate_name", ""),
            job_title=context.get("job_title", ""),
        )
        try:
            return pattern.format_map(ctx)
        except Exception:
            return pattern
