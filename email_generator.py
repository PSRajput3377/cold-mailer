"""Step 1 — corporate email-format permutation engine.

Given a person's first/last name and one or more domains, produce every common
corporate email pattern (firstname.lastname@, flastname@, first_last@, ...).

The patterns are expressed declaratively as functions of the name parts so the
list is easy to read, extend, and test. Output is de-duplicated while
preserving the (priority) order in which patterns are listed.
"""
from __future__ import annotations

from typing import Callable, Iterable

from utils import slugify_name


# A pattern maps (first, last, fi, li) -> local-part string.
#   first = full first name      fi = first initial
#   last  = full last name       li = last initial
_LOCAL_PART_PATTERNS: list[tuple[str, Callable[[str, str, str, str], str]]] = [
    # Most common first.
    ("first.last",      lambda f, l, fi, li: f"{f}.{l}"),
    ("firstlast",       lambda f, l, fi, li: f"{f}{l}"),
    ("first",           lambda f, l, fi, li: f"{f}"),
    ("flast",           lambda f, l, fi, li: f"{fi}{l}"),
    ("first.l",         lambda f, l, fi, li: f"{f}.{li}"),
    ("fi.last",         lambda f, l, fi, li: f"{fi}.{l}"),
    ("first_last",      lambda f, l, fi, li: f"{f}_{l}"),
    ("first-last",      lambda f, l, fi, li: f"{f}-{l}"),
    ("last",            lambda f, l, fi, li: f"{l}"),
    ("last.first",      lambda f, l, fi, li: f"{l}.{f}"),
    ("lastfirst",       lambda f, l, fi, li: f"{l}{f}"),
    ("last_first",      lambda f, l, fi, li: f"{l}_{f}"),
    ("lastf",           lambda f, l, fi, li: f"{l}{fi}"),
    ("f.last",          lambda f, l, fi, li: f"{fi}.{l}"),
    ("firstli",         lambda f, l, fi, li: f"{f}{li}"),     # first.lastinitial concat
    ("first.li",        lambda f, l, fi, li: f"{f}.{li}"),    # first.lastinitial
    ("fili",            lambda f, l, fi, li: f"{fi}{li}"),
    ("fi.li",           lambda f, l, fi, li: f"{fi}.{li}"),
    ("firstlast.dot2",  lambda f, l, fi, li: f"{f}.{l}"),     # safety dup (deduped)
]


def _local_parts(first: str, last: str) -> list[str]:
    """Generate ordered, de-duplicated local-parts for a name."""
    f = slugify_name(first)
    l = slugify_name(last)
    fi = f[:1]
    li = l[:1]
    seen: set[str] = set()
    parts: list[str] = []
    for _name, fn in _LOCAL_PART_PATTERNS:
        try:
            local = fn(f, l, fi, li)
        except Exception:
            continue
        # Skip degenerate parts (e.g. missing last name => "first." )
        local = local.strip(".-_")
        if not local or local in seen:
            continue
        seen.add(local)
        parts.append(local)
    return parts


class EmailGenerator:
    """Produces candidate email addresses for a recipient."""

    def __init__(self, tlds: Iterable[str] | None = None, max_candidates: int = 60):
        self.tlds = list(tlds) if tlds else ["com"]
        self.max_candidates = max_candidates

    def generate(
        self,
        first_name: str,
        last_name: str,
        domains: Iterable[str],
    ) -> list[str]:
        """Return candidate addresses across all supplied domains.

        ``domains`` should be fully-qualified (``google.com``). When a bare
        root (``google``) is passed, the configured TLDs are appended.
        """
        locals_ = _local_parts(first_name, last_name)
        full_domains = self._expand_domains(domains)

        out: list[str] = []
        seen: set[str] = set()
        for domain in full_domains:
            for local in locals_:
                addr = f"{local}@{domain}"
                if addr not in seen:
                    seen.add(addr)
                    out.append(addr)
                    if len(out) >= self.max_candidates:
                        return out
        return out

    def _expand_domains(self, domains: Iterable[str]) -> list[str]:
        expanded: list[str] = []
        seen: set[str] = set()
        for d in domains:
            d = (d or "").strip().lower().lstrip("@")
            if not d:
                continue
            candidates = [d] if "." in d else [f"{d}.{tld}" for tld in self.tlds]
            for c in candidates:
                if c not in seen:
                    seen.add(c)
                    expanded.append(c)
        return expanded
