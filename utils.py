"""Small, dependency-light helpers shared across modules."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

# RFC-5322-ish practical email validation (good enough for our purposes).
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)


def slugify_name(value: str) -> str:
    """Normalise a name part for use in an email local-part.

    Strips accents, lowercases, and removes anything that isn't ``a-z0-9``.
    e.g. "Renée O'Brien" -> "reneeobrien".
    """
    if not value:
        return ""
    # Decompose accents (é -> e) then drop combining marks.
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_only.lower())


def is_valid_email_syntax(email: str) -> bool:
    """Return True if the address is syntactically plausible."""
    return bool(email) and bool(_EMAIL_RE.match(email.strip()))


def normalize_company_root(company_name: str) -> str:
    """Turn a company display name into a bare domain root candidate.

    "DevRev, Inc." -> "devrev" ; "J.P. Morgan" -> "jpmorgan".
    Common corporate suffixes are stripped.
    """
    name = slugify_name(company_name)
    for suffix in ("inc", "llc", "ltd", "corp", "co", "company", "technologies",
                   "technology", "labs", "software", "systems", "group"):
        if name.endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
    return name


def utc_now_iso() -> str:
    """Timezone-aware UTC timestamp suitable for CSV logs."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tidy_text(text: str) -> str:
    """Clean up cosmetic artifacts left when optional placeholders render empty.

    Collapses runs of spaces, removes spaces before punctuation, strips lines
    that became blank, and caps blank-line runs at one. Keeps single newlines
    (within a paragraph) and paragraph breaks (double newline) intact.
    """
    # Normalise spaces/tabs (not newlines) within each line.
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line)          # collapse runs of spaces
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)  # no space before punctuation
        # Drop dangling connectors left by an empty value, e.g. "in ." / "in ,".
        line = re.sub(r"\b(in|with|on|of|as|using|like)\s*([.,;:])", r"\2", line)
        lines.append(line.strip())
    text = "\n".join(lines)
    # Collapse 3+ newlines down to a paragraph break.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_domain(domain: str) -> tuple[str, str]:
    """Split ``devrev.ai`` -> ("devrev", "ai"). TLD may be multi-label
    (``co.uk``) — we only split on the first dot for the root."""
    domain = domain.strip().lower().lstrip("@")
    if "." not in domain:
        return domain, ""
    root, tld = domain.split(".", 1)
    return root, tld
