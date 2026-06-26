"""Step 2 — resolve a company name to its email domain.

Resolution strategy (cheapest / most reliable first):

1. If a domain was provided explicitly, use it.
2. Try Clearbit's free Autocomplete endpoint (no key required) which maps
   company display names to their primary domain — this nails cases like
   "DevRev" -> "devrev.ai" that a naive guess would miss.
3. Fall back to guessing ``<root>.<tld>`` across the configured TLD priority,
   optionally confirming via DNS that the domain at least resolves.

The network calls are best-effort and fully optional: if ``requests`` isn't
installed or there's no connectivity, the guesser still returns candidates so
the pipeline can proceed.
"""
from __future__ import annotations

import socket
from typing import Optional

from utils import normalize_company_root, split_domain

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


_CLEARBIT_AUTOCOMPLETE = "https://autocomplete.clearbit.com/v1/companies/suggest"


class DomainResolver:
    def __init__(
        self,
        tld_priority: Optional[list[str]] = None,
        use_clearbit: bool = True,
        timeout: float = 5.0,
    ):
        self.tld_priority = tld_priority or ["com", "ai", "io", "co", "in"]
        self.use_clearbit = use_clearbit
        self.timeout = timeout

    def resolve(self, company_name: str, provided_domain: Optional[str] = None
                ) -> Optional[str]:
        """Return the best single domain for the company, or None."""
        if provided_domain:
            return provided_domain.strip().lower().lstrip("@")

        # Try the authoritative lookup first.
        if self.use_clearbit:
            domain = self._clearbit_lookup(company_name)
            if domain:
                return domain

        # Fall back to guessing and confirm via DNS where possible.
        for candidate in self.guess_candidates(company_name):
            if self._domain_resolves(candidate):
                return candidate
        # Nothing confirmed — return the top guess so the pipeline can still try.
        guesses = self.guess_candidates(company_name)
        return guesses[0] if guesses else None

    def guess_candidates(self, company_name: str) -> list[str]:
        """All ``<root>.<tld>`` permutations in priority order."""
        root = normalize_company_root(company_name)
        if not root:
            return []
        return [f"{root}.{tld}" for tld in self.tld_priority]

    # -- network helpers ----------------------------------------------------
    def _clearbit_lookup(self, company_name: str) -> Optional[str]:
        if requests is None or not company_name:
            return None
        try:
            resp = requests.get(
                _CLEARBIT_AUTOCOMPLETE,
                params={"query": company_name},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            suggestions = resp.json()
        except Exception:
            return None
        if not suggestions:
            return None
        # Prefer an exact (case-insensitive) name match; else take the first.
        target = company_name.strip().lower()
        for s in suggestions:
            if (s.get("name") or "").strip().lower() == target and s.get("domain"):
                return s["domain"].lower()
        return (suggestions[0].get("domain") or "").lower() or None

    @staticmethod
    def _domain_resolves(domain: str) -> bool:
        """True if the domain has any DNS A record (cheap reachability check)."""
        try:
            socket.getaddrinfo(domain, None)
            return True
        except (socket.gaierror, UnicodeError):
            return False
