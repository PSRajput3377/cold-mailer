"""Shared types and helpers for job-board source adapters."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


@dataclass
class JobPosting:
    """A normalised open role from any job board."""

    title: str
    job_id: str = ""
    url: str = ""
    location: str = ""
    department: str = ""
    company: str = ""
    source: str = ""           # "greenhouse" | "lever" | "ashby"
    content: str = ""          # full description (only when with_content=True)
    raw: dict = field(default_factory=dict)  # original payload, for debugging

    def to_recipient_fields(self) -> dict:
        """The job-context kwargs a Recipient cares about."""
        return {"job_title": self.title, "job_id": self.job_id, "job_url": self.url}


class JobSource(ABC):
    """Base class for an ATS adapter.

    Subclasses implement :meth:`fetch`; the shared HTTP helper handles the
    request boilerplate and graceful degradation when ``requests`` is missing.
    """

    name: str = "base"

    def __init__(self, timeout: float = 10.0, session: Optional["requests.Session"] = None):
        self.timeout = timeout
        self._session = session

    @abstractmethod
    def fetch(self, board_token: str, *, with_content: bool = False) -> list[JobPosting]:
        """Return all open postings for ``board_token``."""

    # -- shared HTTP --------------------------------------------------------
    def _get_json(self, url: str, params: Optional[dict] = None) -> Optional[dict | list]:
        if requests is None:
            raise RuntimeError("the 'requests' package is required for job sources")
        sess = self._session or requests
        resp = sess.get(url, params=params, timeout=self.timeout,
                        headers={"Accept": "application/json"})
        resp.raise_for_status()
        return resp.json()


def filter_postings(
    postings: Iterable[JobPosting],
    *,
    keywords: Optional[Iterable[str]] = None,
    locations: Optional[Iterable[str]] = None,
) -> list[JobPosting]:
    """Filter postings by title keywords and/or location substrings.

    Matching is case-insensitive. ``keywords`` matches the title (any keyword);
    ``locations`` matches the location field (any location). Empty filters pass
    everything through.
    """
    kw = [k.lower() for k in keywords] if keywords else []
    locs = [l.lower() for l in locations] if locations else []

    def matches(p: JobPosting) -> bool:
        if kw and not any(re.search(re.escape(k), p.title, re.IGNORECASE) for k in kw):
            return False
        if locs and not any(l in p.location.lower() for l in locs):
            return False
        return True

    return [p for p in postings if matches(p)]
