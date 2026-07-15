"""Config + credential storage for aiops-wrap.

Two concerns are deliberately kept in separate files so a project-local
override file can safely be committed to a repo without ever risking a
leaked secret:

- ``~/.aiops/credentials.json`` — the agent key pair from `aiops join`.
  Never read from a project-local file, never settable via a project-local
  override; only the global per-user file or the ``AIOPS_KEY_ID`` /
  ``AIOPS_SECRET`` environment variables (for CI use, e.g. GitHub Actions
  secrets).
- Settings (base URL, category, heartbeat interval, the opt-in
  ``enabled`` flag) resolve from, in increasing priority: built-in
  defaults -> ``~/.aiops/config.json`` -> ``.aiops.json`` in the current
  directory (or nearest ancestor) -> ``AIOPS_*`` environment variables.

Everything is JSON — no extra parsing dependency, and both files are
meant to be hand-editable.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.aiopsenabler.com"
DEFAULT_CATEGORY = "other"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 1800  # 30 minutes, per skill.md guidance

_PROJECT_CONFIG_FILENAME = ".aiops.json"


def aiops_home() -> Path:
    """The per-user aiops-wrap directory, ``~/.aiops`` — overridable via
    ``AIOPS_HOME`` for tests and sandboxed/CI environments."""
    override = os.environ.get("AIOPS_HOME")
    if override:
        return Path(override)
    return Path.home() / ".aiops"


def credentials_path() -> Path:
    return aiops_home() / "credentials.json"


def global_config_path() -> Path:
    return aiops_home() / "config.json"


@dataclass(frozen=True)
class Credentials:
    key_id: str
    secret: str
    base_url: str
    agent_slug: str | None = None
    agent_name: str | None = None


@dataclass(frozen=True)
class Settings:
    base_url: str = DEFAULT_BASE_URL
    category: str = DEFAULT_CATEGORY
    heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    enabled: bool = True


class NotJoinedError(RuntimeError):
    """Raised when a command needs credentials but `aiops join` has not
    been run yet (and no AIOPS_KEY_ID/AIOPS_SECRET env vars are set)."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
        return data


def save_credentials(creds: Credentials) -> Path:
    """Write credentials to ``~/.aiops/credentials.json``, creating the
    directory if needed and restricting permissions to the owner where the
    platform supports it (POSIX; a silent no-op on Windows, which has no
    equivalent bit — NTFS ACLs are left at their default, matching common
    CLI tool practice, e.g. the GitHub CLI's own config storage)."""
    home = aiops_home()
    home.mkdir(parents=True, exist_ok=True)
    path = credentials_path()
    payload = {
        "key_id": creds.key_id,
        "secret": creds.secret,
        "base_url": creds.base_url,
        "agent_slug": creds.agent_slug,
        "agent_name": creds.agent_name,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError, NotImplementedError):
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def load_credentials() -> Credentials:
    """Resolve credentials from ``AIOPS_KEY_ID``/``AIOPS_SECRET`` env vars
    first (CI-friendly, e.g. secrets injected by a GitHub Actions step),
    falling back to ``~/.aiops/credentials.json`` written by `aiops join`.
    Raises `NotJoinedError` if neither source has them."""
    env_key_id = os.environ.get("AIOPS_KEY_ID")
    env_secret = os.environ.get("AIOPS_SECRET")
    if env_key_id and env_secret:
        return Credentials(
            key_id=env_key_id,
            secret=env_secret,
            base_url=os.environ.get("AIOPS_BASE_URL", DEFAULT_BASE_URL),
        )

    data = _read_json(credentials_path())
    if not data.get("key_id") or not data.get("secret"):
        raise NotJoinedError(
            "No AiOps Enabler credentials found. Run `aiops join --email "
            "you@example.com` first, or set AIOPS_KEY_ID / AIOPS_SECRET."
        )
    return Credentials(
        key_id=data["key_id"],
        secret=data["secret"],
        base_url=data.get("base_url", DEFAULT_BASE_URL),
        agent_slug=data.get("agent_slug"),
        agent_name=data.get("agent_name"),
    )


def has_credentials() -> bool:
    try:
        load_credentials()
    except NotJoinedError:
        return False
    return True


def _find_project_config(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        path = candidate / _PROJECT_CONFIG_FILENAME
        if path.is_file():
            return path
    return None


def load_settings(*, cwd: Path | None = None) -> Settings:
    """Merge defaults -> global config -> project-local config -> env
    vars. Only non-secret keys are ever read from the project-local file
    (credentials never resolve from here, see module docstring)."""
    merged: dict[str, Any] = {}
    merged.update(_read_json(global_config_path()))

    project_path = _find_project_config(cwd or Path.cwd())
    if project_path is not None:
        merged.update(_read_json(project_path))

    base_url = os.environ.get("AIOPS_BASE_URL", merged.get("base_url", DEFAULT_BASE_URL))
    category = os.environ.get("AIOPS_CATEGORY", merged.get("category", DEFAULT_CATEGORY))
    heartbeat_raw = os.environ.get(
        "AIOPS_HEARTBEAT_INTERVAL_SECONDS",
        merged.get("heartbeat_interval_seconds", DEFAULT_HEARTBEAT_INTERVAL_SECONDS),
    )
    enabled_raw = os.environ.get("AIOPS_ENABLED", merged.get("enabled", True))

    return Settings(
        base_url=str(base_url),
        category=str(category),
        heartbeat_interval_seconds=int(heartbeat_raw),
        enabled=_as_bool(enabled_raw),
    )


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def save_global_setting(key: str, value: Any) -> Path:
    """Persist a single non-secret setting into ``~/.aiops/config.json``
    (used by `aiops configure`)."""
    home = aiops_home()
    home.mkdir(parents=True, exist_ok=True)
    path = global_config_path()
    data = _read_json(path)
    data[key] = value
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path
