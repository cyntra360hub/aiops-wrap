from __future__ import annotations

from pathlib import Path

import pytest

from aiops_wrap.config import (
    DEFAULT_BASE_URL,
    DEFAULT_CATEGORY,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    Credentials,
    NotJoinedError,
    has_credentials,
    load_credentials,
    load_settings,
    save_credentials,
    save_global_setting,
)


def test_load_credentials_raises_not_joined_error_when_nothing_saved() -> None:
    with pytest.raises(NotJoinedError):
        load_credentials()


def test_has_credentials_false_before_join() -> None:
    assert has_credentials() is False


def test_save_and_load_credentials_round_trip() -> None:
    save_credentials(
        Credentials(
            key_id="ak_test",
            secret="s3cret",
            base_url="https://example.test",
            agent_slug="my-agent",
            agent_name="My Agent",
        )
    )

    assert has_credentials() is True
    creds = load_credentials()
    assert creds.key_id == "ak_test"
    assert creds.secret == "s3cret"
    assert creds.base_url == "https://example.test"
    assert creds.agent_slug == "my-agent"


def test_env_vars_take_priority_over_saved_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    save_credentials(Credentials(key_id="ak_file", secret="file-secret", base_url=DEFAULT_BASE_URL))
    monkeypatch.setenv("AIOPS_KEY_ID", "ak_env")
    monkeypatch.setenv("AIOPS_SECRET", "env-secret")

    creds = load_credentials()
    assert creds.key_id == "ak_env"
    assert creds.secret == "env-secret"


def test_load_settings_defaults_when_nothing_configured() -> None:
    settings = load_settings()
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.category == DEFAULT_CATEGORY
    assert settings.heartbeat_interval_seconds == DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    assert settings.enabled is True


def test_save_global_setting_persists_and_is_read_back() -> None:
    save_global_setting("category", "incident-response")
    settings = load_settings()
    assert settings.category == "incident-response"


def test_project_local_config_overrides_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_global_setting("category", "observability")

    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".aiops.json").write_text('{"category": "alert-triage"}', encoding="utf-8")

    settings = load_settings(cwd=project_dir)
    assert settings.category == "alert-triage"


def test_project_local_config_found_in_ancestor_directory(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "myproject"
    nested = project_dir / "src" / "deep"
    nested.mkdir(parents=True)
    (project_dir / ".aiops.json").write_text('{"category": "remediation"}', encoding="utf-8")

    settings = load_settings(cwd=nested)
    assert settings.category == "remediation"


def test_env_var_overrides_project_local_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".aiops.json").write_text('{"category": "alert-triage"}', encoding="utf-8")
    monkeypatch.setenv("AIOPS_CATEGORY", "observability")

    settings = load_settings(cwd=project_dir)
    assert settings.category == "observability"


def test_enabled_false_parses_from_various_string_forms(tmp_path: Path) -> None:
    for value in ("false", "0", "no", "off", ""):
        (tmp_path / ".aiops.json").write_text(f'{{"enabled": "{value}"}}', encoding="utf-8")
        settings = load_settings(cwd=tmp_path)
        assert settings.enabled is False, f"expected enabled=False for {value!r}"


def test_project_local_config_cannot_set_credentials(tmp_path: Path) -> None:
    """Security guard: only ~/.aiops/credentials.json (or env vars) may
    ever supply key_id/secret — a project-local `.aiops.json` (which may
    be committed to a public repo) has no path to smuggle a secret in."""
    (tmp_path / ".aiops.json").write_text(
        '{"key_id": "ak_malicious", "secret": "steal-me"}', encoding="utf-8"
    )

    with pytest.raises(NotJoinedError):
        load_credentials()
