"""Step 9 — email verification.

Three strategies, selected via ``config.yaml`` (``verification.strategy``):

* ``none``  — syntax check only.
* ``smtp``  — free MX lookup + SMTP RCPT-TO probe (no third party). Many large
              providers (Google, Microsoft) accept-all or block probes, so an
              "unknown" result is common and handled via ``accept_risky``.
* ``api``   — delegate to a paid verification service (Abstract / Hunter /
              NeverBounce). Only the adapter for the configured service runs.

Every verifier returns a :class:`VerificationResult`; the caller decides whether
to send based on ``.is_valid`` and the ``accept_risky`` policy.
"""
from __future__ import annotations

import smtplib
import socket
from dataclasses import dataclass
from typing import Optional

from utils import is_valid_email_syntax

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

try:
    import dns.resolver  # dnspython, optional
    _HAS_DNS = True
except ImportError:  # pragma: no cover
    _HAS_DNS = False


@dataclass
class VerificationResult:
    email: str
    result: str          # "valid" | "invalid" | "risky" | "unknown"
    strategy: str
    score: Optional[float] = None
    detail: str = ""

    @property
    def is_valid(self) -> bool:
        return self.result == "valid"

    @property
    def is_invalid(self) -> bool:
        return self.result == "invalid"


class EmailVerifier:
    def __init__(self, config: dict):
        self.enabled = config.get("enabled", True)
        self.strategy = config.get("strategy", "smtp")
        self.accept_risky = config.get("accept_risky", False)
        self.api_cfg = config.get("api", {}) or {}
        # A plausible mailbox to use as MAIL FROM during SMTP probes.
        self._probe_sender = "verify@example.com"

    def verify(self, email: str) -> VerificationResult:
        email = (email or "").strip()
        if not is_valid_email_syntax(email):
            return VerificationResult(email, "invalid", "syntax", detail="bad syntax")
        if not self.enabled or self.strategy == "none":
            return VerificationResult(email, "unknown", "none")
        if self.strategy == "api":
            return self._verify_api(email)
        return self._verify_smtp(email)

    def should_send(self, result: VerificationResult) -> bool:
        """Policy: send on valid; send on risky/unknown only if accept_risky."""
        if result.is_invalid:
            return False
        if result.is_valid:
            return True
        return self.accept_risky  # "risky"/"unknown"

    # -- SMTP strategy ------------------------------------------------------
    def _verify_smtp(self, email: str) -> VerificationResult:
        domain = email.rsplit("@", 1)[-1]
        mx_hosts = self._mx_hosts(domain)
        if not mx_hosts:
            return VerificationResult(email, "invalid", "smtp", detail="no MX")

        for host in mx_hosts:
            try:
                server = smtplib.SMTP(timeout=10)
                server.connect(host, 25)
                server.helo(socket.getfqdn())
                server.mail(self._probe_sender)
                code, _ = server.rcpt(email)
                server.quit()
            except Exception as exc:  # connection blocked / timeout
                return VerificationResult(email, "unknown", "smtp", detail=str(exc))
            if code in (250, 251):
                return VerificationResult(email, "valid", "smtp", detail=f"rcpt {code}")
            if code in (550, 551, 553):
                return VerificationResult(email, "invalid", "smtp", detail=f"rcpt {code}")
            return VerificationResult(email, "unknown", "smtp", detail=f"rcpt {code}")
        return VerificationResult(email, "unknown", "smtp")

    @staticmethod
    def _mx_hosts(domain: str) -> list[str]:
        if _HAS_DNS:
            try:
                answers = dns.resolver.resolve(domain, "MX")
                return [str(r.exchange).rstrip(".") for r in
                        sorted(answers, key=lambda r: r.preference)]
            except Exception:
                return []
        # Fallback without dnspython: assume the domain itself accepts mail.
        try:
            socket.getaddrinfo(domain, None)
            return [domain]
        except (socket.gaierror, UnicodeError):
            return []

    # -- API strategy -------------------------------------------------------
    def _verify_api(self, email: str) -> VerificationResult:
        if requests is None:
            return VerificationResult(email, "unknown", "api", detail="requests missing")
        service = (self.api_cfg.get("service") or "abstract").lower()
        key = self.api_cfg.get("api_key", "")
        try:
            if service == "abstract":
                return self._abstract(email, key)
            if service == "hunter":
                return self._hunter(email, key)
            if service == "neverbounce":
                return self._neverbounce(email, key)
        except Exception as exc:
            return VerificationResult(email, "unknown", "api", detail=str(exc))
        return VerificationResult(email, "unknown", "api", detail=f"unknown service {service}")

    def _abstract(self, email: str, key: str) -> VerificationResult:
        r = requests.get(
            "https://emailvalidation.abstractapi.com/v1/",
            params={"api_key": key, "email": email}, timeout=15,
        )
        data = r.json()
        deliver = (data.get("deliverability") or "").upper()
        score = data.get("quality_score")
        mapping = {"DELIVERABLE": "valid", "UNDELIVERABLE": "invalid", "RISKY": "risky"}
        return VerificationResult(email, mapping.get(deliver, "unknown"), "api",
                                  score=float(score) if score else None, detail=deliver)

    def _hunter(self, email: str, key: str) -> VerificationResult:
        r = requests.get(
            "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": key}, timeout=15,
        )
        data = (r.json() or {}).get("data", {})
        status = (data.get("status") or "").lower()
        mapping = {"valid": "valid", "invalid": "invalid",
                   "accept_all": "risky", "webmail": "valid",
                   "disposable": "invalid", "unknown": "unknown"}
        return VerificationResult(email, mapping.get(status, "unknown"), "api",
                                  score=data.get("score"), detail=status)

    def _neverbounce(self, email: str, key: str) -> VerificationResult:
        r = requests.get(
            "https://api.neverbounce.com/v4/single/check",
            params={"key": key, "email": email}, timeout=15,
        )
        data = r.json()
        result = (data.get("result") or "").lower()
        mapping = {"valid": "valid", "invalid": "invalid",
                   "catchall": "risky", "unknown": "unknown",
                   "disposable": "invalid"}
        return VerificationResult(email, mapping.get(result, "unknown"), "api",
                                  detail=result)
