"""Step 8 — pluggable email sender with retry (Step 12 — attachments).

Architecture: a small :class:`EmailProvider` interface with one concrete
implementation per backend. :class:`EmailSender` builds the MIME message
(including attachments), enforces retry-with-backoff, and delegates the actual
transport to the configured provider. Adding a new backend later (e.g. Mailgun)
means writing one ``EmailProvider`` subclass — nothing else changes.

Providers:
    GmailProvider / OutlookProvider  -> SMTP (smtplib, STARTTLS)
    SendGridProvider                 -> SendGrid v3 REST API
    SesProvider                      -> AWS SES via boto3
    GraphProvider                    -> Microsoft Graph sendMail REST API
"""
from __future__ import annotations

import base64
import mimetypes
import smtplib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    body: str
    from_name: str = ""
    from_email: str = ""
    attachments: list[str] = field(default_factory=list)


@dataclass
class SendResult:
    success: bool
    message_id: str = ""
    error: str = ""
    attempts: int = 0


# --- Provider interface ------------------------------------------------------
class EmailProvider(ABC):
    """Transport-specific send. Raise on failure; return a message-id on
    success (empty string is acceptable when the backend gives none)."""

    @abstractmethod
    def send(self, email: OutgoingEmail) -> str: ...


def _build_mime(email: OutgoingEmail) -> EmailMessage:
    """Construct a MIME message with optional file attachments (Step 12)."""
    msg = EmailMessage()
    from_addr = f"{email.from_name} <{email.from_email}>" if email.from_name else email.from_email
    msg["From"] = from_addr
    msg["To"] = email.to
    msg["Subject"] = email.subject
    msg.set_content(email.body)

    for path_str in email.attachments:
        path = Path(path_str)
        if not path.exists():
            continue
        ctype, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype.split("/", 1) if ctype else ("application", "octet-stream"))
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype,
                           filename=path.name)
    return msg


class _SmtpProvider(EmailProvider):
    """Shared SMTP implementation for Gmail / Outlook / any SMTP host."""

    def __init__(self, host: str, port: int, username: str, password: str,
                 use_tls: bool = True):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.use_tls = use_tls

    def send(self, email: OutgoingEmail) -> str:
        msg = _build_mime(email)
        with smtplib.SMTP(self.host, self.port, timeout=30) as server:
            server.ehlo()
            if self.use_tls:
                server.starttls()
                server.ehlo()
            if self.username:
                server.login(self.username, self.password)
            server.send_message(msg)
        return msg["Message-ID"] or ""


class GmailProvider(_SmtpProvider):
    pass


class OutlookProvider(_SmtpProvider):
    pass


class SendGridProvider(EmailProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def send(self, email: OutgoingEmail) -> str:
        if requests is None:
            raise RuntimeError("requests is required for SendGrid")
        attachments = []
        for path_str in email.attachments:
            path = Path(path_str)
            if not path.exists():
                continue
            ctype, _ = mimetypes.guess_type(path.name)
            attachments.append({
                "content": base64.b64encode(path.read_bytes()).decode(),
                "filename": path.name,
                "type": ctype or "application/octet-stream",
                "disposition": "attachment",
            })
        payload = {
            "personalizations": [{"to": [{"email": email.to}]}],
            "from": {"email": email.from_email, "name": email.from_name},
            "subject": email.subject,
            "content": [{"type": "text/plain", "value": email.body}],
        }
        if attachments:
            payload["attachments"] = attachments
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload, timeout=30,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"SendGrid {resp.status_code}: {resp.text}")
        return resp.headers.get("X-Message-Id", "")


class SesProvider(EmailProvider):
    def __init__(self, region: str, access_key_id: str, secret_access_key: str):
        try:
            import boto3  # noqa
        except ImportError as exc:
            raise RuntimeError("boto3 is required for SES") from exc
        import boto3
        self._client = boto3.client(
            "ses", region_name=region,
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
        )

    def send(self, email: OutgoingEmail) -> str:
        msg = _build_mime(email)
        resp = self._client.send_raw_email(
            Source=email.from_email,
            Destinations=[email.to],
            RawMessage={"Data": msg.as_bytes()},
        )
        return resp.get("MessageId", "")


class GraphProvider(EmailProvider):
    """Microsoft Graph sendMail using client-credentials OAuth."""

    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 sender_user_id: str):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.sender_user_id = sender_user_id
        self._token: Optional[str] = None

    def _access_token(self) -> str:
        if requests is None:
            raise RuntimeError("requests is required for Microsoft Graph")
        resp = requests.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            }, timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def send(self, email: OutgoingEmail) -> str:
        token = self._access_token()
        attachments = []
        for path_str in email.attachments:
            path = Path(path_str)
            if not path.exists():
                continue
            ctype, _ = mimetypes.guess_type(path.name)
            attachments.append({
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": path.name,
                "contentType": ctype or "application/octet-stream",
                "contentBytes": base64.b64encode(path.read_bytes()).decode(),
            })
        message = {
            "subject": email.subject,
            "body": {"contentType": "Text", "content": email.body},
            "toRecipients": [{"emailAddress": {"address": email.to}}],
        }
        if attachments:
            message["attachments"] = attachments
        resp = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{self.sender_user_id}/sendMail",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={"message": message, "saveToSentItems": True}, timeout=30,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"Graph {resp.status_code}: {resp.text}")
        return ""


# --- Factory + sender --------------------------------------------------------
def build_provider(provider_name: str, provider_cfg: dict) -> EmailProvider:
    name = provider_name.lower()
    if name == "gmail":
        return GmailProvider(provider_cfg["host"], provider_cfg["port"],
                             provider_cfg.get("username", ""), provider_cfg.get("password", ""),
                             provider_cfg.get("use_tls", True))
    if name == "outlook":
        return OutlookProvider(provider_cfg["host"], provider_cfg["port"],
                               provider_cfg.get("username", ""), provider_cfg.get("password", ""),
                               provider_cfg.get("use_tls", True))
    if name == "sendgrid":
        return SendGridProvider(provider_cfg["api_key"])
    if name == "ses":
        return SesProvider(provider_cfg["region"], provider_cfg.get("access_key_id", ""),
                           provider_cfg.get("secret_access_key", ""))
    if name == "graph":
        return GraphProvider(provider_cfg["tenant_id"], provider_cfg["client_id"],
                             provider_cfg["client_secret"], provider_cfg["sender_user_id"])
    raise ValueError(f"unknown provider: {provider_name}")


class EmailSender:
    """Sends an :class:`OutgoingEmail` through a provider with retry/backoff."""

    def __init__(self, provider: EmailProvider, max_attempts: int = 3,
                 backoff_seconds: int = 5, dry_run: bool = False,
                 sleep=time.sleep):
        self.provider = provider
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.dry_run = dry_run
        self._sleep = sleep

    def send(self, email: OutgoingEmail) -> SendResult:
        if self.dry_run:
            return SendResult(success=True, message_id="DRY_RUN", attempts=0)

        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                message_id = self.provider.send(email)
                return SendResult(success=True, message_id=message_id, attempts=attempt)
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.max_attempts:
                    self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        return SendResult(success=False, error=last_error, attempts=self.max_attempts)
