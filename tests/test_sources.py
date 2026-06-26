"""Offline tests for job-board adapters and the AI generator wiring.

Uses fake HTTP sessions with canned ATS payloads — no network. Verifies each
adapter normalises its vendor's JSON shape into JobPosting correctly, the
filter helper works, and the AIGenerator degrades safely when disabled.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai_generator import AIGenerator                       # noqa: E402
from sources import filter_postings, get_source            # noqa: E402
from sources.base import JobPosting                         # noqa: E402


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    """Stands in for requests; returns a canned payload regardless of URL."""

    def __init__(self, payload):
        self._payload = payload
        self.last_url = None
        self.last_params = None

    def get(self, url, params=None, timeout=None, headers=None):
        self.last_url = url
        self.last_params = params
        return _FakeResponse(self._payload)


# --- Greenhouse -------------------------------------------------------------
def test_greenhouse_parsing():
    payload = {"jobs": [
        {"id": 123, "title": "Software Engineer",
         "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
         "location": {"name": "Remote"},
         "departments": [{"name": "Engineering"}],
         "content": "<p>Build <b>things</b>.</p>"},
    ]}
    src = get_source("greenhouse", session=_FakeSession(payload))
    posts = src.fetch("acme", with_content=True)
    assert len(posts) == 1
    p = posts[0]
    assert p.title == "Software Engineer"
    assert p.job_id == "123"
    assert p.location == "Remote"
    assert p.department == "Engineering"
    assert p.source == "greenhouse"
    assert "Build" in p.content and "<" not in p.content  # HTML stripped


# --- Lever ------------------------------------------------------------------
def test_lever_parsing():
    payload = [
        {"id": "abc-1", "text": "Backend Engineer",
         "hostedUrl": "https://jobs.lever.co/acme/abc-1",
         "categories": {"location": "NYC", "team": "Platform"},
         "descriptionPlain": "Own the API."},
    ]
    src = get_source("lever", session=_FakeSession(payload))
    posts = src.fetch("acme", with_content=True)
    assert len(posts) == 1
    p = posts[0]
    assert p.title == "Backend Engineer"
    assert p.job_id == "abc-1"
    assert p.location == "NYC"
    assert p.department == "Platform"
    assert p.content == "Own the API."
    assert p.source == "lever"


# --- Ashby ------------------------------------------------------------------
def test_ashby_parsing():
    payload = {"jobs": [
        {"id": "xyz-9", "title": "Full-Stack Engineer",
         "jobUrl": "https://jobs.ashbyhq.com/acme/xyz-9",
         "location": "Remote - US", "department": "Product",
         "descriptionPlain": "Ship features."},
    ]}
    src = get_source("ashby", session=_FakeSession(payload))
    posts = src.fetch("acme", with_content=True)
    assert len(posts) == 1
    p = posts[0]
    assert p.title == "Full-Stack Engineer"
    assert p.job_id == "xyz-9"
    assert p.location == "Remote - US"
    assert p.source == "ashby"
    assert p.content == "Ship features."


# --- filtering --------------------------------------------------------------
def test_filter_postings_by_keyword_and_location():
    posts = [
        JobPosting(title="Software Engineer", location="Remote"),
        JobPosting(title="Product Manager", location="NYC"),
        JobPosting(title="Senior Backend Engineer", location="NYC"),
    ]
    eng = filter_postings(posts, keywords=["engineer"])
    assert {p.title for p in eng} == {"Software Engineer", "Senior Backend Engineer"}
    nyc_eng = filter_postings(posts, keywords=["engineer"], locations=["nyc"])
    assert [p.title for p in nyc_eng] == ["Senior Backend Engineer"]
    assert len(filter_postings(posts)) == 3  # empty filter passes all


def test_to_recipient_fields():
    p = JobPosting(title="SWE", job_id="42", url="http://x/42")
    assert p.to_recipient_fields() == {
        "job_title": "SWE", "job_id": "42", "job_url": "http://x/42"}


# --- AI generator fail-safe -------------------------------------------------
def test_ai_generator_disabled_is_unavailable():
    gen = AIGenerator({"enabled": False})
    assert not gen.available
    # generate() must return None (caller then falls back to templates).
    assert gen.generate("referral_request", {"company": "Acme"}) is None


def test_ai_generator_unknown_source_rejected():
    import sources
    try:
        sources.get_source("workday")
    except ValueError as e:
        assert "workday" in str(e)
    else:
        raise AssertionError("expected ValueError for unknown source")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL  {name}: {exc}")
    print(f"\n{'ALL PASSED' if not failures else f'{failures} FAILED'}")
    sys.exit(1 if failures else 0)
