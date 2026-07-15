from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_aiops_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test runs against a throwaway ~/.aiops directory and starts
    with no AIOPS_* env vars set — never touches the real user config."""
    home = tmp_path / "aiops-home"
    monkeypatch.setenv("AIOPS_HOME", str(home))
    for var in (
        "AIOPS_KEY_ID",
        "AIOPS_SECRET",
        "AIOPS_BASE_URL",
        "AIOPS_CATEGORY",
        "AIOPS_HEARTBEAT_INTERVAL_SECONDS",
        "AIOPS_ENABLED",
    ):
        monkeypatch.delenv(var, raising=False)
    return home
