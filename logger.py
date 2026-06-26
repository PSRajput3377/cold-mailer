"""Logging layer (Step 10 + Step 11).

Two responsibilities:

1. A standard Python logger for human-readable runtime output.
2. A :class:`CsvLogger` that appends structured rows to the five tracking CSVs
   and answers the "have we already contacted this address?" question used for
   de-duplication (Step 11).

CSV writes use pandas for convenience but fall back to the stdlib ``csv``
module if pandas isn't available, so the logging layer never blocks a run.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterable

from utils import utc_now_iso

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None  # type: ignore


# --- Standard logger ---------------------------------------------------------
def get_logger(name: str = "cold_mailer", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                              datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


# --- Column schemas for each CSV --------------------------------------------
_SCHEMAS: dict[str, list[str]] = {
    "sent": ["timestamp", "email", "company", "person", "designation",
             "subject", "template_category", "template_id", "source",
             "provider", "message_id", "status"],
    "failed": ["timestamp", "email", "company", "person", "subject",
               "error", "attempts"],
    "verified": ["timestamp", "email", "result", "strategy", "score"],
    "duplicates": ["timestamp", "email", "company", "person",
                   "first_contacted"],
    "replies": ["timestamp", "email", "company", "person", "replied",
                "reply_date", "notes"],
}


class CsvLogger:
    """Manages the five tracking CSV files defined in ``config.yaml``."""

    def __init__(self, directory: str | Path, files: dict[str, str]):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        # Map logical name -> resolved path, e.g. "sent" -> logs/emails_sent.csv
        self.paths: dict[str, Path] = {
            key: self.dir / files.get(key, f"{key}.csv") for key in _SCHEMAS
        }
        for key, path in self.paths.items():
            if not path.exists():
                self._write_header(path, _SCHEMAS[key])

    # -- low-level helpers --------------------------------------------------
    @staticmethod
    def _write_header(path: Path, columns: list[str]) -> None:
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow(columns)

    def _append(self, key: str, row: dict[str, Any]) -> None:
        columns = _SCHEMAS[key]
        record = {col: row.get(col, "") for col in columns}
        record.setdefault("timestamp", utc_now_iso())
        record["timestamp"] = record["timestamp"] or utc_now_iso()
        with self.paths[key].open("a", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=columns).writerow(record)

    # -- public append methods ---------------------------------------------
    def log_sent(self, **row: Any) -> None:
        self._append("sent", row)

    def log_failed(self, **row: Any) -> None:
        self._append("failed", row)

    def log_verified(self, **row: Any) -> None:
        self._append("verified", row)

    def log_duplicate(self, **row: Any) -> None:
        self._append("duplicates", row)

    def log_reply(self, **row: Any) -> None:
        self._append("replies", row)

    # -- de-duplication (Step 11) ------------------------------------------
    def already_contacted(self, email: str) -> bool:
        """True if ``email`` appears in the sent log."""
        return email.strip().lower() in self._sent_emails()

    def _sent_emails(self) -> set[str]:
        path = self.paths["sent"]
        if not path.exists():
            return set()
        emails: set[str] = set()
        with path.open("r", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                addr = (row.get("email") or "").strip().lower()
                if addr:
                    emails.add(addr)
        return emails

    # -- reporting ----------------------------------------------------------
    def load(self, key: str):
        """Return a DataFrame (or list of dicts) for the given log."""
        path = self.paths[key]
        if pd is not None:
            return pd.read_csv(path) if path.exists() else pd.DataFrame(
                columns=_SCHEMAS[key])
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
