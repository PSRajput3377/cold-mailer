"""Job-board source adapters.

Each adapter pulls open roles from a company's hosted job board (Greenhouse,
Lever, Ashby, ...) and yields normalised :class:`JobPosting` objects. These
feed the cold-mailer pipeline: a posting supplies the ``job_title`` /
``job_id`` / ``job_url`` context for a :class:`models.Recipient`, and the
``filter_postings`` helper narrows a board down to the roles you care about.

Adding a new board (Workday, SmartRecruiters, ...) means writing one
:class:`JobSource` subclass and registering it in ``_REGISTRY`` — nothing else
in the system changes.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .ashby import AshbySource
from .base import JobPosting, JobSource, filter_postings
from .greenhouse import GreenhouseSource
from .lever import LeverSource

# name -> source class. Keyed by the ATS vendor.
_REGISTRY: dict[str, type[JobSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "ashby": AshbySource,
}


def available_sources() -> list[str]:
    return list(_REGISTRY)


def get_source(name: str, **kwargs) -> JobSource:
    """Instantiate a source adapter by vendor name."""
    key = name.strip().lower()
    if key not in _REGISTRY:
        raise ValueError(f"unknown job source {name!r}; "
                         f"available: {', '.join(_REGISTRY)}")
    return _REGISTRY[key](**kwargs)


def fetch_jobs(
    source: str,
    board_token: str,
    *,
    keywords: Optional[Iterable[str]] = None,
    locations: Optional[Iterable[str]] = None,
    with_content: bool = False,
) -> list[JobPosting]:
    """Convenience one-shot: fetch and filter postings from one board.

    ``board_token`` is the company's slug on that ATS (e.g. ``stripe`` for
    ``boards.greenhouse.io/stripe``).
    """
    src = get_source(source)
    postings = src.fetch(board_token, with_content=with_content)
    return filter_postings(postings, keywords=keywords, locations=locations)


__all__ = [
    "JobPosting", "JobSource", "filter_postings",
    "GreenhouseSource", "LeverSource", "AshbySource",
    "available_sources", "get_source", "fetch_jobs",
]
