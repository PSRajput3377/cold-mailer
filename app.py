"""Cold Mailer — application orchestrator.

Wires together every module into one pipeline and exposes:

* :class:`ColdMailer`  — programmatic API.
* a CLI                — ``python app.py send --recipients recipients.csv``
                         ``python app.py preview ...`` (render without sending)
                         ``python app.py emails ...``  (just list candidate addrs)

Pipeline per recipient (Steps 1-12):

    resolve domain ─▶ generate candidate emails ─▶ verify & pick one
        ─▶ dedupe check ─▶ choose template + subject ─▶ render + personalize
        ─▶ attach files ─▶ send (retry) ─▶ log

The orchestrator is deliberately thin: it sequences the specialised modules and
applies the policies from ``config.yaml``. Anything heavier belongs in a module.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from config import Config, load_config
from context_builder import build_context
from domain_resolver import DomainResolver
from email_generator import EmailGenerator
from email_sender import EmailSender, OutgoingEmail, build_provider
from email_verifier import EmailVerifier
from logger import CsvLogger, get_logger
from models import Candidate, Designation, Recipient
from personalization import Personalizer
from resume_parser import parse_resume
from subject_generator import SubjectGenerator
from template_engine import CATEGORIES, TemplateEngine
from utils import tidy_text


@dataclass
class PreparedEmail:
    """Everything needed to send (or preview) one email."""

    recipient: Recipient
    to_email: Optional[str]
    subject: str
    body: str
    category: str
    template_id: str
    attachments: list[str]
    skipped_reason: str = ""


class ColdMailer:
    def __init__(self, config: Config):
        self.cfg = config
        log_cfg = config.get("logging", {})
        self.log = get_logger(level=log_cfg.get("level", "INFO"))
        self.csv = CsvLogger(
            self.cfg.resolve_path(log_cfg.get("directory", "logs")),
            log_cfg.get("files", {}),
        )

        # --- core modules ---
        ef = config.get("email_formats", {})
        self.generator = EmailGenerator(ef.get("tlds"), ef.get("max_candidates", 60))

        dr = config.get("domain_resolution", {})
        self.resolver = DomainResolver(
            dr.get("tld_priority"), dr.get("use_clearbit_autocomplete", True))

        self.verifier = EmailVerifier(config.get("verification", {}))

        tpl_cfg = config.get("templates", {})
        self.templates = TemplateEngine(
            self.cfg.resolve_path(tpl_cfg.get("directory", "templates")),
            tpl_cfg.get("enabled_categories"))

        pcfg = config.get("personalization", {})
        self.personalizer = Personalizer(
            pcfg.get("vary_greeting", True), pcfg.get("vary_closing", True),
            pcfg.get("vary_sentence_order", True), pcfg.get("seed"))
        self.subjects = SubjectGenerator(seed=pcfg.get("seed"))

        provider = build_provider(config["provider"], config.provider_config())
        retry = config.get("retry", {})
        self.sender = EmailSender(
            provider, retry.get("max_attempts", 3), retry.get("backoff_seconds", 5),
            dry_run=config.get("dry_run", True))

        self.rate = config.get("rate_limit", {})

    # ------------------------------------------------------------------ #
    # Candidate (sender) construction                                    #
    # ------------------------------------------------------------------ #
    def build_candidate(self, **kw) -> Candidate:
        """Build the sending candidate, enriching from the resume PDF."""
        cand = Candidate(
            full_name=kw.get("full_name") or self.cfg.get("sender", {}).get("name", ""),
            email=kw.get("email") or self.cfg.get("sender", {}).get("email", ""),
            linkedin_url=kw.get("linkedin_url", ""),
            github_url=kw.get("github_url", ""),
            portfolio_url=kw.get("portfolio_url", ""),
            phone=kw.get("phone") or self.cfg.get("sender", {}).get("phone", ""),
            preferred_role=kw.get("preferred_role", "Software Engineer"),
            resume_path=kw.get("resume_path"),
        )
        resume_path = kw.get("resume_path") or self.cfg.get("attachments", {}).get("resume")
        if resume_path:
            resolved = self.cfg.resolve_path(resume_path)
            if resolved and resolved.exists():
                data = parse_resume(resolved)
                cand.resume_path = str(resolved)
                cand.resume_highlights = kw.get("resume_highlights") or data.highlights
                cand.skills = kw.get("skills") or data.skills
                cand.recent_internship = kw.get("recent_internship") or data.recent_internship
        # Allow explicit overrides even without a resume file.
        cand.resume_highlights = kw.get("resume_highlights", cand.resume_highlights)
        cand.skills = kw.get("skills", cand.skills)
        return cand

    # ------------------------------------------------------------------ #
    # Address resolution (Steps 1, 2, 9)                                 #
    # ------------------------------------------------------------------ #
    def resolve_addresses(self, recipient: Recipient) -> list[str]:
        domain = self.resolver.resolve(recipient.company_name, recipient.company_domain)
        recipient.resolved_domain = domain
        if not domain:
            self.log.warning("Could not resolve a domain for %s", recipient.company_name)
            return []
        emails = self.generator.generate(
            recipient.person_first_name, recipient.person_last_name, [domain])
        recipient.candidate_emails = emails
        return emails

    def pick_deliverable(self, candidates: Iterable[str]) -> Optional[str]:
        """Verify candidates in order; return the first send-worthy address."""
        for email in candidates:
            result = self.verifier.verify(email)
            self.csv.log_verified(email=email, result=result.result,
                                  strategy=result.strategy, score=result.score or "")
            if result.is_invalid:
                self.log.debug("invalid: %s (%s)", email, result.detail)
                continue
            if self.verifier.should_send(result):
                return email
        return None

    # ------------------------------------------------------------------ #
    # Email assembly (Steps 3-7, 12)                                     #
    # ------------------------------------------------------------------ #
    def prepare(self, candidate: Candidate, recipient: Recipient,
                category: Optional[str] = None) -> PreparedEmail:
        rng = self.personalizer.rng_for(
            recipient.chosen_email or recipient.person_full_name + recipient.company_name)

        category = self._key(category) if category else self._choose_category(recipient, rng)
        template = self.templates.choose(category, rng)
        context = build_context(candidate, recipient)

        # Add personalization pieces into the context so templates can use them.
        context["greeting"] = self.personalizer.greeting(recipient.person_first_name, rng)
        context["closing"] = self.personalizer.closing(rng)
        context["cta"] = self.personalizer.cta(rng)
        context["signature"] = self._render_signature(context)

        body = self.templates.render(template, context)
        body = self.personalizer.personalize_body(body, rng)
        body = tidy_text(body)  # clean artifacts from empty optional placeholders
        subject = (self.subjects.generate(context, category, rng)).strip()

        return PreparedEmail(
            recipient=recipient,
            to_email=recipient.chosen_email,
            subject=subject,
            body=body,
            category=category,
            template_id=template.id,
            attachments=self._attachments(candidate),
        )

    def _render_signature(self, context: dict) -> str:
        sig = self.cfg.get("sender", {}).get("signature", "")
        if not sig:
            return ""
        return self.templates.render(sig, context)

    def _attachments(self, candidate: Candidate) -> list[str]:
        acfg = self.cfg.get("attachments", {})
        paths: list[str] = []
        if acfg.get("attach_resume", True) and candidate.resume_path:
            paths.append(candidate.resume_path)
        for key in ("cover_letter", "transcript", "portfolio_pdf"):
            p = self.cfg.resolve_path(acfg.get(key))
            if p and p.exists():
                paths.append(str(p))
        return paths

    def _choose_category(self, recipient: Recipient, rng: random.Random) -> str:
        """Pick a sensible default category based on the recipient's role."""
        by_designation = {
            Designation.HR: ["job_opening_inquiry", "swe_opportunity"],
            Designation.RECRUITER: ["job_opening_inquiry", "followup_after_recruiter",
                                    "applied_requesting_referral"],
            Designation.TALENT_ACQUISITION: ["job_opening_inquiry", "swe_opportunity"],
            Designation.ENGINEERING_MANAGER: ["informational_chat", "swe_opportunity",
                                             "resume_review_request"],
            Designation.SOFTWARE_ENGINEER: ["referral_request", "informational_chat",
                                           "circulate_resume"],
            Designation.FOUNDER: ["swe_opportunity", "informational_chat"],
        }
        options = [c for c in by_designation.get(recipient.designation, list(CATEGORIES))
                   if self.templates.count(c) > 0]
        if not options:
            options = [c for c in self.templates.categories()]
        return rng.choice(options)

    # ------------------------------------------------------------------ #
    # Full pipeline for one recipient                                    #
    # ------------------------------------------------------------------ #
    def process(self, candidate: Candidate, recipient: Recipient,
                category: Optional[str] = None) -> PreparedEmail:
        # Step 1 & 2: resolve domain + generate candidate emails.
        candidates = self.resolve_addresses(recipient)
        if not candidates:
            return PreparedEmail(recipient, None, "", "", "", "", [],
                                 skipped_reason="no_domain_or_candidates")

        # Step 9: verify and pick a deliverable address.
        chosen = self.pick_deliverable(candidates)
        if not chosen:
            return PreparedEmail(recipient, None, "", "", "", "", [],
                                 skipped_reason="no_deliverable_address")
        recipient.chosen_email = chosen

        # Step 11: skip if already contacted.
        if self.csv.already_contacted(chosen):
            self.csv.log_duplicate(email=chosen, company=recipient.company_name,
                                   person=recipient.person_full_name)
            return PreparedEmail(recipient, chosen, "", "", "", "", [],
                                 skipped_reason="duplicate")

        # Steps 3-7, 12: build the email.
        return self.prepare(candidate, recipient, category)

    def send_one(self, candidate: Candidate, recipient: Recipient,
                 category: Optional[str] = None) -> PreparedEmail:
        prepared = self.process(candidate, recipient, category)
        if prepared.skipped_reason:
            self.log.info("Skipped %s (%s)", recipient.person_full_name,
                          prepared.skipped_reason)
            return prepared

        out = OutgoingEmail(
            to=prepared.to_email, subject=prepared.subject, body=prepared.body,
            from_name=self.cfg.get("sender", {}).get("name", ""),
            from_email=candidate.email, attachments=prepared.attachments)

        result = self.sender.send(out)
        if result.success:
            self.csv.log_sent(email=prepared.to_email, company=recipient.company_name,
                              person=recipient.person_full_name,
                              designation=recipient.designation.value,
                              subject=prepared.subject,
                              template_category=prepared.category,
                              template_id=prepared.template_id,
                              provider=self.cfg["provider"],
                              message_id=result.message_id,
                              status="dry_run" if self.sender.dry_run else "sent")
            self.log.info("%s -> %s | %s", "DRY-RUN" if self.sender.dry_run else "SENT",
                          prepared.to_email, prepared.subject)
        else:
            self.csv.log_failed(email=prepared.to_email, company=recipient.company_name,
                                person=recipient.person_full_name,
                                subject=prepared.subject, error=result.error,
                                attempts=result.attempts)
            self.log.error("FAILED -> %s | %s", prepared.to_email, result.error)
        return prepared

    def send_batch(self, candidate: Candidate, recipients: list[Recipient],
                   category: Optional[str] = None) -> list[PreparedEmail]:
        results: list[PreparedEmail] = []
        max_run = self.rate.get("max_per_run", len(recipients))
        base_delay = self.rate.get("seconds_between_emails", 0)
        for i, recipient in enumerate(recipients[:max_run]):
            results.append(self.send_one(candidate, recipient, category))
            if base_delay and i < len(recipients) - 1 and not self.sender.dry_run:
                # base delay + jitter to look human and respect rate limits.
                time.sleep(base_delay + random.uniform(0, base_delay * 0.3))
        return results


# ---------------------------------------------------------------------- #
# CSV input loading                                                      #
# ---------------------------------------------------------------------- #
def load_recipients(path: str | Path) -> list[Recipient]:
    """Load recipients from a CSV. Columns map to Recipient fields; only
    company_name, person_first_name, person_last_name, designation are required."""
    recipients: list[Recipient] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            recipients.append(Recipient(
                company_name=row["company_name"].strip(),
                person_first_name=row["person_first_name"].strip(),
                person_last_name=row.get("person_last_name", "").strip(),
                designation=Designation.from_str(row.get("designation", "Recruiter")),
                company_domain=(row.get("company_domain") or "").strip() or None,
                job_title=row.get("job_title", "").strip(),
                job_id=row.get("job_id", "").strip(),
                job_url=row.get("job_url", "").strip(),
            ))
    return recipients


# ---------------------------------------------------------------------- #
# CLI                                                                    #
# ---------------------------------------------------------------------- #
def _candidate_kwargs(args) -> dict:
    return dict(
        full_name=args.name, email=args.from_email, resume_path=args.resume,
        linkedin_url=args.linkedin, github_url=args.github,
        portfolio_url=args.portfolio, preferred_role=args.role)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Cold Mailer — automated cold email sender")
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--recipients", required=True, help="recipients CSV path")
    common.add_argument("--name", default=None, help="your full name (sender)")
    common.add_argument("--from-email", default=None, dest="from_email")
    common.add_argument("--resume", default=None)
    common.add_argument("--linkedin", default="")
    common.add_argument("--github", default="")
    common.add_argument("--portfolio", default="")
    common.add_argument("--role", default="Software Engineer")
    common.add_argument("--category", default=None,
                        help="force a template category (else auto by designation)")

    sub.add_parser("send", parents=[common], help="send emails")
    sub.add_parser("preview", parents=[common], help="render emails without sending")

    em = sub.add_parser("emails", parents=[common],
                        help="list generated candidate addresses only")
    em.add_argument("--no-verify", action="store_true")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cfg = load_config(args.config)
    mailer = ColdMailer(cfg)
    candidate = mailer.build_candidate(**_candidate_kwargs(args))
    recipients = load_recipients(args.recipients)

    if args.command == "emails":
        for r in recipients:
            addrs = mailer.resolve_addresses(r)
            print(f"\n# {r.person_full_name} @ {r.company_name} "
                  f"(domain: {r.resolved_domain})")
            for a in addrs:
                print(f"  {a}")
        return 0

    if args.command == "preview":
        for r in recipients:
            prepared = mailer.process(candidate, r, args.category)
            print("=" * 70)
            if prepared.skipped_reason:
                print(f"SKIPPED {r.person_full_name}: {prepared.skipped_reason}")
                continue
            print(f"To:      {prepared.to_email}")
            print(f"Subject: {prepared.subject}")
            print(f"[{prepared.category} / {prepared.template_id}]")
            print(f"Attach:  {prepared.attachments}")
            print("-" * 70)
            print(prepared.body)
        return 0

    # send
    if cfg.get("dry_run", True):
        mailer.log.warning("dry_run is ON — no emails will actually be sent. "
                           "Set dry_run: false in config.yaml to send for real.")
    mailer.send_batch(candidate, recipients, args.category)
    return 0


if __name__ == "__main__":
    sys.exit(main())
