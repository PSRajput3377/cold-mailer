"""Ashby job-board adapter.

Uses Ashby's public job-board posting API (no key required):
    https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true

The ``token`` is the company's job-board name, e.g. ``Ashby`` for
``jobs.ashbyhq.com/Ashby``. Ashby is case-sensitive about this slug.
"""
from __future__ import annotations

from .base import JobPosting, JobSource

_BASE = "https://api.ashbyhq.com/posting-api/job-board/{token}"


class AshbySource(JobSource):
    name = "ashby"

    def fetch(self, board_token: str, *, with_content: bool = False) -> list[JobPosting]:
        url = _BASE.format(token=board_token.strip().strip("/"))
        # Ashby includes a plain-text description in the list response already.
        data = self._get_json(url, params={"includeCompensation": "true"}) or {}
        jobs = data.get("jobs", []) if isinstance(data, dict) else []

        postings: list[JobPosting] = []
        for job in jobs:
            content = ""
            if with_content:
                content = (job.get("descriptionPlain")
                           or job.get("descriptionHtml", ""))
            postings.append(JobPosting(
                title=job.get("title", "").strip(),
                job_id=str(job.get("id", "")),
                url=job.get("jobUrl", "") or job.get("applyUrl", ""),
                location=job.get("location", "") or "",
                department=job.get("department", "") or job.get("team", "") or "",
                company=board_token,
                source=self.name,
                content=content,
                raw=job,
            ))
        return postings
