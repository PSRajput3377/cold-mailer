"""Configuration loading.

Reads ``config.yaml``, expands ``${ENV_VAR}`` references against the process
environment (after loading a local ``.env`` if present), and exposes the result
as a lightweight, attribute-and-dict accessible object.

Usage::

    from config import load_config
    cfg = load_config()              # default: ./config.yaml
    cfg.provider                     # "gmail"
    cfg["rate_limit"]["max_per_run"] # 100
    cfg.get("dry_run", False)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

try:  # optional dependency — fall back gracefully if not installed
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_a, **_k):  # type: ignore
        return False


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` tokens in strings with env values.

    Missing variables expand to an empty string so the app can still start and
    fail loudly only when that specific provider/secret is actually used.
    """
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


class Config:
    """Thin wrapper over the parsed YAML dict supporting both ``cfg.key`` and
    ``cfg["key"]`` access. Nested dicts are returned as plain dicts."""

    def __init__(self, data: dict[str, Any], path: Path | None = None):
        self._data = data
        self.path = path

    # -- dict-style access --------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    # -- attribute-style access --------------------------------------------
    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails.
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def as_dict(self) -> dict[str, Any]:
        return self._data

    # -- convenience --------------------------------------------------------
    def provider_config(self) -> dict[str, Any]:
        """Return the connection block for the currently-selected provider."""
        name = self._data["provider"]
        try:
            return self._data["providers"][name]
        except KeyError as exc:
            raise KeyError(f"No provider config for {name!r} in config.yaml") from exc

    def resolve_path(self, value: str | None) -> Path | None:
        """Resolve a config path relative to the config file's directory."""
        if not value:
            return None
        p = Path(value)
        if p.is_absolute() or self.path is None:
            return p
        return (self.path.parent / p).resolve()


def load_config(path: str | os.PathLike[str] = "config.yaml") -> Config:
    """Load and return the application configuration."""
    load_dotenv()  # populate os.environ from .env if present (no-op otherwise)

    cfg_path = Path(path)
    if not cfg_path.exists():
        # Allow running from anywhere: look next to this module too.
        alt = Path(__file__).parent / "config.yaml"
        cfg_path = alt if alt.exists() else cfg_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"config file not found: {path}")

    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    return Config(_expand_env(raw), path=cfg_path.resolve())
