"""AI-generated personalized emails via Claude (Anthropic API).

This is an optional, drop-in alternative to the template engine. When enabled
(``ai.enabled: true`` in config.yaml and an API key present), :class:`AIGenerator`
asks Claude to write a short, human-sounding cold email tailored to the
recipient, category, and — when available — the actual job description scraped
from the company's board.

Design notes
------------
* Provider-correct: uses the official ``anthropic`` SDK and ``claude-opus-4-8``
  with adaptive thinking, per Anthropic's current guidance.
* Structured output: Claude returns ``{subject, body}`` validated against a JSON
  schema (``output_config.format``), so we never parse free text.
* Fails safe: if the SDK isn't installed, no key is set, or the call errors, the
  caller falls back to the template engine. The orchestrator wires this up so a
  missing key degrades gracefully rather than breaking a run.
* Cost aware: a system prompt is cached across recipients (prompt caching), and
  only the small per-recipient context varies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

MODEL = "claude-opus-4-8"

# Stable system prompt — cached across recipients (kept free of volatile data).
_SYSTEM_PROMPT = """\
You write cold emails for a software engineer reaching out about jobs and \
referrals. Your emails must read as if a real person wrote them in two minutes.

Hard rules:
- 3 short paragraphs maximum. Often 2 is better.
- No flowery adjectives, no buzzwords, no "I hope this email finds you well", \
no "I am writing to", no "I would be thrilled", no em-dash-heavy AI cadence.
- Specific over generic: reference the actual role, company, and one or two real \
details from the candidate's background. Never invent facts not given.
- Vary sentence structure and openings so two emails never feel templated.
- Plain text only. No markdown, no bullet symbols unless listing real highlights.
- The greeting and sign-off are added by the caller — do NOT include them. Start \
with the first sentence of the body and end with the last sentence before the \
sign-off.
- Match the requested category's intent exactly.

Return only the structured fields requested."""

# JSON schema for the structured response.
_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
    "additionalProperties": False,
}

# Human-readable intent per category (mirrors template_engine.CATEGORIES).
_CATEGORY_INTENT = {
    "referral_request": "ask this person to refer the candidate for the role",
    "job_opening_inquiry": "ask whether there are open SWE roles / inquire about a specific opening",
    "resume_review_request": "ask for a quick look at the resume and any feedback",
    "circulate_resume": "ask them to forward/circulate the resume to the hiring team",
    "swe_opportunity": "express interest in a software engineer opportunity",
    "new_grad": "express interest in new-grad / entry-level SWE roles",
    "applied_requesting_referral": "note the candidate already applied and ask for a referral",
    "followup_after_application": "politely follow up on a submitted application",
    "followup_after_recruiter": "follow up after a prior recruiter conversation",
    "informational_chat": "request a brief informational chat about the team",
}


@dataclass
class AIEmail:
    subject: str
    body: str


class AIGenerator:
    """Generates email subject + body with Claude. Optional and fail-safe."""

    def __init__(self, config: dict):
        self.enabled = bool(config.get("enabled", False))
        self.model = config.get("model", MODEL)
        self.effort = config.get("effort", "medium")
        self.max_tokens = config.get("max_tokens", 1024)
        api_key = config.get("api_key") or None
        self._client = None
        if self.enabled and anthropic is not None:
            # Anthropic() also reads ANTHROPIC_API_KEY from the env if unset here.
            self._client = anthropic.Anthropic(api_key=api_key) if api_key \
                else anthropic.Anthropic()

    @property
    def available(self) -> bool:
        """True only if AI generation can actually run."""
        return self.enabled and self._client is not None

    def generate(self, category: str, context: dict[str, Any],
                 job_description: str = "") -> Optional[AIEmail]:
        """Return an AI-written email, or None if generation is unavailable/failed."""
        if not self.available:
            return None
        try:
            prompt = self._build_prompt(category, context, job_description)
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "adaptive"},
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
                },
                # Cache the stable system prompt across recipients.
                system=[{"type": "text", "text": _SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            # Network error, bad key, refusal, etc. — caller falls back to templates.
            return None

        if getattr(resp, "stop_reason", None) == "refusal":
            return None
        text = next((b.text for b in resp.content if b.type == "text"), "")
        if not text:
            return None
        import json
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        subject, body = data.get("subject", "").strip(), data.get("body", "").strip()
        if not subject or not body:
            return None
        return AIEmail(subject=subject, body=body)

    # -- prompt assembly ----------------------------------------------------
    def _build_prompt(self, category: str, ctx: dict[str, Any],
                      job_description: str) -> str:
        intent = _CATEGORY_INTENT.get(category, "reach out about a software engineer role")
        lines = [
            f"Write a cold email whose goal is to: {intent}.",
            "",
            "Recipient:",
            f"- Name: {ctx.get('first_name', '')} {ctx.get('last_name', '')}".rstrip(),
            f"- Role/title at their company: {ctx.get('designation', '')}",
            f"- Company: {ctx.get('company', '')}",
        ]
        role = ctx.get("job_title") or ctx.get("role")
        if role:
            lines.append(f"- Target role: {role}")
        if ctx.get("job_id"):
            lines.append(f"- Job ID: {ctx['job_id']}")

        lines += ["", "Candidate (the sender):",
                  f"- Name: {ctx.get('candidate_name', '')}"]
        if ctx.get("skills"):
            lines.append(f"- Skills: {ctx['skills']}")
        if ctx.get("recent_internship"):
            lines.append(f"- Recent internship: {ctx['recent_internship']}")
        highlights = ctx.get("resume_highlights_list") or []
        if highlights:
            lines.append("- Resume highlights:")
            lines += [f"    * {h}" for h in highlights]
        for label, key in (("GitHub", "github"), ("Portfolio", "portfolio"),
                           ("LinkedIn", "linkedin")):
            if ctx.get(key):
                lines.append(f"- {label}: {ctx[key]}")

        if job_description:
            # Keep the description bounded so it doesn't dominate the prompt.
            snippet = job_description.strip()[:1500]
            lines += ["", "Job description (reference 1 concrete detail, do not copy):",
                      snippet]

        lines += ["", "Remember: no greeting and no sign-off — body sentences only."]
        return "\n".join(lines)
