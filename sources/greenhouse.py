"""Greenhouse job-board adapter.

Uses Greenhouse's public Job Board API (no key required):
    https://boards-api.greenhouse.io/v1/boards/{token}/jobs
    https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

The board ``token`` is the company slug, e.g. ``stripe`` for
``boards.greenhouse.io/stripe``.
"""
from __future__ import annotations

import re

from .base import JobPosting, JobSource

_BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _strip_html(html: str) -> str:
    """Greenhouse returns HTML content; reduce to readable plain text."""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html, "html.parser").get_text("\n")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace.
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


class GreenhouseSource(JobSource):
    name = "greenhouse"

    def fetch(self, board_token: str, *, with_content: bool = False) -> list[JobPosting]:
        url = _BASE.format(token=board_token.strip().strip("/"))
        params = {"content": "true"} if with_content else None
        data = self._get_json(url, params=params) or {}
        jobs = data.get("jobs", []) if isinstance(data, dict) else []

        postings: list[JobPosting] = []
        for job in jobs:
            location = (job.get("location") or {}).get("name", "")
            departments = job.get("departments") or []
            dept = departments[0]["name"] if departments and departments[0].get("name") else ""
            postings.append(JobPosting(
                title=job.get("title", "").strip(),
                job_id=str(job.get("id", "")),
                url=job.get("absolute_url", ""),
                location=location,
                department=dept,
                company=board_token,
                source=self.name,
                content=_strip_html(job.get("content", "")) if with_content else "",
                raw=job,
            ))
        return postings
