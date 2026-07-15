from __future__ import annotations

import sys

import httpx
import pytest

from aiops_wrap import cli
from aiops_wrap.config import load_credentials, load_settings


def test_join_command_end_to_end(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "agent": {"slug": "cli-agent", "name": "CLI Agent"},
                "api_key": {"key_id": "ak_cli", "secret": "cli-secret"},
            },
        )

    # Patch httpx.Client construction so `join()`'s internal client uses
    # our mock transport without threading a transport param through argparse.
    real_client_cls = httpx.Client

    def patched_client(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(fake_handler)
        return real_client_cls(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", patched_client)

    exit_code = cli.main(["join", "--email", "op@example.com", "--name", "CLI Agent"])

    assert exit_code == 0
    creds = load_credentials()
    assert creds.key_id == "ak_cli"
    out = capsys.readouterr().out
    assert "CLI Agent" in out
    assert "cli-agent" in out


def test_join_command_reports_failure_with_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fake_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="operator_email is required")

    real_client_cls = httpx.Client

    def patched_client(*args: object, **kwargs: object) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(fake_handler)
        return real_client_cls(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", patched_client)

    exit_code = cli.main(["join", "--email", "bad"])

    assert exit_code == 1
    assert "failed" in capsys.readouterr().err


def test_wrap_command_with_double_dash_runs_and_returns_exit_code() -> None:
    exit_code = cli.main(["wrap", "--", sys.executable, "-c", "print('hi')"])
    assert exit_code == 0


def test_wrap_command_without_double_dash_runs_and_returns_exit_code() -> None:
    exit_code = cli.main(["wrap", sys.executable, "-c", "import sys; sys.exit(7)"])
    assert exit_code == 7


def test_wrap_command_with_no_command_prints_usage_and_exits_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main(["wrap"])
    assert exit_code == 2
    assert "no command given" in capsys.readouterr().err


def test_configure_sets_category(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["configure", "category", "observability"])
    assert exit_code == 0
    assert load_settings().category == "observability"


def test_configure_sets_enabled_boolean() -> None:
    cli.main(["configure", "enabled", "false"])
    assert load_settings().enabled is False


def test_configure_sets_heartbeat_interval_as_int() -> None:
    cli.main(["configure", "heartbeat_interval_seconds", "60"])
    assert load_settings().heartbeat_interval_seconds == 60


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])
    assert exc_info.value.code == 0
    assert "aiops-wrap" in capsys.readouterr().out


def test_no_subcommand_is_required_error() -> None:
    with pytest.raises(SystemExit):
        cli.main([])
