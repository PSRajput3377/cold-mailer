"""Step 3 + Step 5 — template loading and placeholder rendering.

Templates live as YAML files under ``templates/`` — one file per category. Each
file has the shape::

    category: referral_request
    label: "Referral Request"
    templates:
      - id: referral_request_01
        subject: "Referral request — {{job_title}} at {{company}}"   # optional hint
        body: |
          Hi {{first_name}},
          ...

Bodies use Jinja2 ``{{ placeholder }}`` syntax (Step 5). Rendering is done with
a sandboxed environment and ``undefined`` placeholders collapse to empty strings
so a missing optional field (e.g. ``job_id``) never breaks an email.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml
from jinja2 import Environment, BaseLoader, ChainableUndefined


@dataclass
class Template:
    id: str
    category: str
    body: str
    subject: str = ""


# Canonical category keys -> human labels. Used to validate template files and
# to let callers request a category by either key or label.
CATEGORIES: dict[str, str] = {
    "referral_request": "Referral Request",
    "job_opening_inquiry": "Job Opening Inquiry",
    "resume_review_request": "Resume Review Request",
    "circulate_resume": "Request to circulate resume internally",
    "swe_opportunity": "Request for Software Engineer opportunity",
    "new_grad": "New Graduate Opportunity",
    "applied_requesting_referral": "Applied already and requesting referral",
    "followup_after_application": "Following up after application",
    "followup_after_recruiter": "Following up after recruiter connection",
    "informational_chat": "Request for informational chat",
}


class TemplateEngine:
    """Loads template files and renders them against a context dict."""

    def __init__(self, directory: str | Path, enabled_categories: Optional[list[str]] = None):
        self.dir = Path(directory)
        self.enabled = set(enabled_categories or [])
        # ChainableUndefined => {{ a.b }} on a missing var yields "" not an error.
        self._env = Environment(
            loader=BaseLoader(),
            undefined=ChainableUndefined,
            autoescape=False,           # plain-text emails, not HTML
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._by_category: dict[str, list[Template]] = {}
        self._load()

    # -- loading ------------------------------------------------------------
    def _load(self) -> None:
        if not self.dir.exists():
            raise FileNotFoundError(f"templates directory not found: {self.dir}")
        for path in sorted(self.dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            category = data.get("category")
            if not category:
                continue
            if self.enabled and category not in self.enabled:
                continue
            templates = []
            for t in data.get("templates", []):
                templates.append(Template(
                    id=t["id"],
                    category=category,
                    body=t["body"],
                    subject=t.get("subject", ""),
                ))
            if templates:
                self._by_category.setdefault(category, []).extend(templates)

    # -- access -------------------------------------------------------------
    def categories(self) -> list[str]:
        return list(self._by_category.keys())

    def count(self, category: str) -> int:
        return len(self._by_category.get(self._key(category), []))

    def get_templates(self, category: str) -> list[Template]:
        return list(self._by_category.get(self._key(category), []))

    def choose(self, category: str, rng: Optional[random.Random] = None) -> Template:
        """Pick one template from a category at random."""
        templates = self.get_templates(category)
        if not templates:
            raise ValueError(f"no templates for category {category!r}")
        return (rng or random).choice(templates)

    # -- rendering ----------------------------------------------------------
    def render(self, template: Template | str, context: dict[str, Any]) -> str:
        body = template.body if isinstance(template, Template) else template
        return self._env.from_string(body).render(**context)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _key(category: str) -> str:
        """Accept either the canonical key or the human label."""
        if category in CATEGORIES:
            return category
        for key, label in CATEGORIES.items():
            if label.lower() == category.lower():
                return key
        return category
