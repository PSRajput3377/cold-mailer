"""Resume parsing (supports Step 4 — resume highlights / skills / internship).

Extracts plain text from a resume PDF and applies light heuristics to pull out:

* skills            (from a "Skills" / "Technical Skills" section)
* highlights        (bullet lines that look like achievements)
* recent_internship (first line mentioning "intern")

This is intentionally heuristic and dependency-light. If ``pypdf`` isn't
installed or parsing fails, it degrades gracefully to empty results so the
pipeline still runs — callers can always supply these fields manually.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore

# Common tech keywords used as a fallback skill extractor.
_SKILL_HINTS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
    "React", "Node", "Django", "Flask", "FastAPI", "Spring", "AWS", "GCP",
    "Azure", "Docker", "Kubernetes", "PostgreSQL", "MySQL", "MongoDB", "Redis",
    "Kafka", "GraphQL", "REST", "SQL", "Git", "Linux", "TensorFlow", "PyTorch",
]


class ResumeData:
    def __init__(self, text: str = "", skills: Optional[list[str]] = None,
                 highlights: Optional[list[str]] = None, internship: str = ""):
        self.text = text
        self.skills = skills or []
        self.highlights = highlights or []
        self.recent_internship = internship


def parse_resume(path: str | Path) -> ResumeData:
    """Parse a resume PDF into structured fields (best-effort)."""
    p = Path(path)
    if PdfReader is None or not p.exists():
        return ResumeData()

    try:
        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ResumeData()

    return ResumeData(
        text=text,
        skills=_extract_skills(text),
        highlights=_extract_highlights(text),
        internship=_extract_internship(text),
    )


def _extract_skills(text: str) -> list[str]:
    # Try to grab a Skills section first.
    m = re.search(r"(?:technical\s+)?skills?\s*[:\n](.+?)(?:\n\n|\n[A-Z][a-z]+\s*:)",
                  text, re.IGNORECASE | re.DOTALL)
    found: list[str] = []
    if m:
        chunk = m.group(1)
        found = [s.strip() for s in re.split(r"[,•|/\n]", chunk) if 1 < len(s.strip()) < 30]
    if not found:
        # Fallback: scan for known keywords.
        for kw in _SKILL_HINTS:
            if re.search(rf"\b{re.escape(kw)}\b", text):
                found.append(kw)
    # De-dupe preserving order, cap to a reasonable number.
    seen, out = set(), []
    for s in found:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out[:15]


def _extract_highlights(text: str) -> list[str]:
    bullets = re.findall(r"(?:^|\n)\s*[•\-\*]\s*(.+)", text)
    # Prefer bullets that quantify impact (numbers / %).
    quantified = [b.strip() for b in bullets if re.search(r"\d", b)]
    pool = quantified or [b.strip() for b in bullets]
    return [b for b in pool if 15 < len(b) < 200][:5]


def _extract_internship(text: str) -> str:
    for line in text.splitlines():
        if "intern" in line.lower() and len(line.strip()) > 5:
            return line.strip()
    return ""
