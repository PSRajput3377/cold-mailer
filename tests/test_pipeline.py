"""Offline test suite — no network, no real sending.

Run from the project root with:  python -m pytest tests/ -q
(or simply: python tests/test_pipeline.py)

These tests exercise the pure logic: email-format generation, template loading
and rendering, subject variation counts, personalization determinism, and the
dedup logic — all without touching SMTP, DNS, or any third-party API.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Make the package modules importable when run directly.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from context_builder import build_context          # noqa: E402
from email_generator import EmailGenerator         # noqa: E402
from logger import CsvLogger                        # noqa: E402
from models import Candidate, Designation, Recipient  # noqa: E402
from personalization import Personalizer            # noqa: E402
from subject_generator import SubjectGenerator      # noqa: E402
from template_engine import CATEGORIES, TemplateEngine  # noqa: E402
from utils import slugify_name, normalize_company_root, is_valid_email_syntax  # noqa: E402

TEMPLATES_DIR = ROOT / "templates"


# --- utils ------------------------------------------------------------------
def test_slugify_strips_accents_and_punct():
    assert slugify_name("Renée O'Brien") == "reneeobrien"
    assert slugify_name("José") == "jose"


def test_normalize_company_root_strips_suffix():
    assert normalize_company_root("DevRev, Inc.") == "devrev"
    assert normalize_company_root("Stripe") == "stripe"


def test_email_syntax():
    assert is_valid_email_syntax("a.b@c.io")
    assert not is_valid_email_syntax("nope@")
    assert not is_valid_email_syntax("no-at-sign.com")


# --- email generation (Step 1) ---------------------------------------------
def test_email_generator_patterns():
    g = EmailGenerator(tlds=["com"], max_candidates=60)
    emails = g.generate("Jane", "Doe", ["stripe.com"])
    assert "jane.doe@stripe.com" in emails
    assert "jdoe@stripe.com" in emails
    assert "jane_doe@stripe.com" in emails
    assert "jane-doe@stripe.com" in emails
    assert "j.doe@stripe.com" in emails
    assert len(emails) == len(set(emails))  # de-duplicated


def test_email_generator_expands_tlds_for_bare_root():
    g = EmailGenerator(tlds=["com", "ai", "io"])
    emails = g.generate("Sam", "Lee", ["acme"])
    assert "sam.lee@acme.com" in emails
    assert "sam.lee@acme.ai" in emails
    assert "sam.lee@acme.io" in emails


# --- templates (Step 3) -----------------------------------------------------
def test_every_category_has_templates():
    """Each declared category must load at least one template. The library
    mixes large generic categories (20 templates each) with small curated ones
    (e.g. referral_request, professional_application), so the invariant is
    non-empty rather than a fixed count."""
    te = TemplateEngine(TEMPLATES_DIR)
    for key in CATEGORIES:
        assert te.count(key) >= 1, f"{key} has no templates"


def test_every_template_renders_without_leftover_placeholders():
    import re
    te = TemplateEngine(TEMPLATES_DIR)
    cand = Candidate("Sam Lee", "s@e.com", "li/s", "gh/s", "s.dev",
                     skills=["Python", "Go"], resume_highlights=["Did X"],
                     recent_internship="Intern at Acme")
    p = Personalizer()
    for job_id in ("ENG-1", ""):
        r = Recipient("DevRev", "Aarav", "Sharma", Designation.RECRUITER,
                      company_domain="devrev.ai", job_title="Software Engineer",
                      job_id=job_id)
        ctx = build_context(cand, r)
        rng = p.rng_for("k")
        ctx.update(greeting=p.greeting("Aarav", rng), closing=p.closing(rng),
                   cta=p.cta(rng), signature="Best,\nSam")
        for key in CATEGORIES:
            for t in te.get_templates(key):
                body = te.render(t, ctx)
                assert not re.search(r"{{|{%", body), f"leftover in {t.id}"
                assert body.strip().startswith(("Hi", "Hello", "Hey", "Dear"))
                assert body.strip().endswith("Sam")


def test_templates_render_cleanly_with_empty_optional_fields():
    """A candidate with no resume (no skills/highlights/internship/links) and a
    recipient with no job_id/job_url must still produce artifact-free emails —
    every optional placeholder is guarded with {% if %}."""
    import re
    from utils import tidy_text
    te = TemplateEngine(TEMPLATES_DIR)
    ctx = dict(
        first_name="Jane", last_name="Doe", full_name="Jane Doe",
        designation="Recruiter", company="Acme", domain="acme.com",
        job_title="Software Engineer", role="Software Engineer",
        candidate_name="Sam Lee", candidate_first_name="Sam",
        preferred_role="Software Engineer", resume="Software Engineer",
        greeting="Hi Jane,", closing="Best", cta="Could we chat?", signature="Best,\nSam",
        # all optionals empty:
        job_id="", job_url="", linkedin="", github="", portfolio="", phone="",
        skills="", skills_list=[], resume_highlights="", resume_highlights_list=[],
        top_highlight="", recent_internship="",
    )
    # Artifacts that signal an unguarded empty placeholder (after tidy_text).
    artifact_patterns = [
        r"(^|\n)\s*[,.;:]",                        # line starts with punctuation
        r"\(\s*\)",                                 # empty parens
        r"[ ]{2,}",                                 # doubled spaces mid-line
        r"\b(in|with|of|using|on|as|like|here|at)\s+[.,;:]",  # connector then punct
        r"\b(experience|background|work|skills|strengths|fit) (in|with)\b(?!\s+\S)",
        r"[a-z]:\s*[.\n]",                          # "label:" then empty
        r",\s*and\s*[.\n]",                         # dangling "and"
    ]
    offenders = []
    for key in CATEGORIES:
        for t in te.get_templates(key):
            body = tidy_text(te.render(t, ctx))
            for pat in artifact_patterns:
                if re.search(pat, body):
                    offenders.append(t.id)
                    break
    assert not offenders, f"empty-field artifacts in: {offenders}"


# --- subjects (Step 6) ------------------------------------------------------
def test_subject_variations_exceed_100():
    sg = SubjectGenerator(seed=1)
    ctx = {"role": "Backend Engineer", "company": "Stripe",
           "candidate_name": "Sam Lee", "job_title": "Backend Engineer", "job_id": ""}
    assert len(sg.variations(ctx)) >= 100


# --- personalization (Step 7) ----------------------------------------------
def test_personalization_is_deterministic_per_recipient():
    p = Personalizer()
    a1 = p.greeting("Jane", p.rng_for("jane@x.com"))
    a2 = p.greeting("Jane", p.rng_for("jane@x.com"))
    b = p.greeting("Jane", p.rng_for("john@y.com"))
    assert a1 == a2                 # same recipient -> stable
    # Different recipients should *usually* differ; assert the RNG seeds differ.
    assert p.rng_for("a").random() != p.rng_for("b").random()


# --- dedup (Step 11) --------------------------------------------------------
def test_dedup_detects_contacted_address():
    with tempfile.TemporaryDirectory() as d:
        csv = CsvLogger(d, {})
        assert not csv.already_contacted("x@y.com")
        csv.log_sent(email="x@y.com", company="Y", person="X")
        # Re-open to ensure it reads from disk, not memory.
        csv2 = CsvLogger(d, {})
        assert csv2.already_contacted("x@y.com")
        assert csv2.already_contacted("X@Y.COM")  # case-insensitive


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
