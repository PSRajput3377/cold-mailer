"""Lever job-board adapter.

Uses Lever's public postings API (no key required):
    https://api.lever.co/v0/postings/{token}?mode=json

The ``token`` is the company slug, e.g. ``netflix`` for
``jobs.lever.co/netflix``.
"""
from __future__ import annotations

from .base import JobPosting, JobSource

_BASE = "https://api.lever.co/v0/postings/{token}"


class LeverSource(JobSource):
    name = "lever"

    def fetch(self, board_token: str, *, with_content: bool = False) -> list[JobPosting]:
        url = _BASE.format(token=board_token.strip().strip("/"))
        data = self._get_json(url, params={"mode": "json"}) or []
        if not isinstance(data, list):
            return []

        postings: list[JobPosting] = []
        for job in data:
            categories = job.get("categories") or {}
            # Lever's description text fields are always present (no extra call).
            content = ""
            if with_content:
                content = (job.get("descriptionPlain")
                           or job.get("description", ""))
            postings.append(JobPosting(
                title=job.get("text", "").strip(),
                job_id=str(job.get("id", "")),
                url=job.get("hostedUrl", "") or job.get("applyUrl", ""),
                location=categories.get("location", "") or "",
                department=categories.get("team", "") or categories.get("department", "") or "",
                company=board_token,
                source=self.name,
                content=content,
                raw=job,
            ))
        return postings
