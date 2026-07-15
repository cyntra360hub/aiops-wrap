from __future__ import annotations

import json
import sys
from collections.abc import Callable

import httpx
import pytest

from aiops_wrap.config import Credentials, Settings, save_credentials
from aiops_wrap.wrap import _HeartbeatThread, run_wrapped

Handler = Callable[[httpx.Request], httpx.Response]

SUCCESS_CMD = [sys.executable, "-c", "print('ok')"]
FAILURE_CMD = [sys.executable, "-c", "import sys; sys.exit(3)"]


def _settings(**overrides: object) -> Settings:
    base = {
        "base_url": "https://example.test",
        "category": "other",
        "heartbeat_interval_seconds": 1800,
        "enabled": True,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_wrap_returns_child_exit_code_when_not_joined() -> None:
    result = run_wrapped(SUCCESS_CMD, settings=_settings(), quiet=True)
    assert result.exit_code == 0
    assert result.reported is False


def test_wrap_returns_nonzero_exit_code_when_not_joined() -> None:
    result = run_wrapped(FAILURE_CMD, settings=_settings(), quiet=True)
    assert result.exit_code == 3
    assert result.reported is False


def test_wrap_reports_task_started_and_completed_with_success_outcome() -> None:
    save_credentials(Credentials(key_id="ak", secret="sec", base_url="https://example.test"))
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={})

    result = run_wrapped(SUCCESS_CMD, settings=_settings(), transport=httpx.MockTransport(handler))

    assert result.exit_code == 0
    assert result.reported is True
    paths = [r.url.path for r in requests]
    assert paths == ["/api/v1/events", "/api/v1/events"]

    started_body = json.loads(requests[0].content)
    assert started_body["event_type"] == "task_started"
    assert started_body["task_id"] == result.task_id

    completed_body = json.loads(requests[1].content)
    assert completed_body["event_type"] == "task_completed"
    assert completed_body["task_id"] == result.task_id
    assert completed_body["outcome"] == "success"
    assert completed_body["category"] == "other"
    assert isinstance(completed_body["duration_ms"], int)


def test_wrap_reports_failure_outcome_on_nonzero_exit() -> None:
    save_credentials(Credentials(key_id="ak", secret="sec", base_url="https://example.test"))
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={})

    result = run_wrapped(FAILURE_CMD, settings=_settings(), transport=httpx.MockTransport(handler))

    assert result.exit_code == 3
    completed_body = json.loads(requests[1].content)
    assert completed_body["outcome"] == "failure"


def test_wrap_disabled_setting_skips_reporting_without_credentials_error() -> None:
    save_credentials(Credentials(key_id="ak", secret="sec", base_url="https://example.test"))

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request should be made when reporting is disabled")

    result = run_wrapped(
        SUCCESS_CMD,
        settings=_settings(enabled=False),
        transport=httpx.MockTransport(handler),
        quiet=True,
    )

    assert result.exit_code == 0
    assert result.reported is False


def test_wrap_network_failure_on_task_started_does_not_change_exit_code() -> None:
    save_credentials(Credentials(key_id="ak", secret="sec", base_url="https://example.test"))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    result = run_wrapped(
        SUCCESS_CMD, settings=_settings(), transport=httpx.MockTransport(handler), quiet=True
    )

    assert result.exit_code == 0
    assert result.reported is False


def test_wrap_network_failure_on_task_completed_does_not_change_exit_code() -> None:
    save_credentials(Credentials(key_id="ak", secret="sec", base_url="https://example.test"))
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(201, json={})
        raise httpx.ConnectError("boom", request=request)

    result = run_wrapped(
        FAILURE_CMD, settings=_settings(), transport=httpx.MockTransport(handler), quiet=True
    )

    assert result.exit_code == 3
    assert result.reported is False


def test_wrap_raises_value_error_for_empty_command() -> None:
    with pytest.raises(ValueError):
        run_wrapped([], settings=_settings())


def test_heartbeat_thread_calls_client_until_stopped() -> None:
    from aiops_enabler import AiOpsClient

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(201, json={})

    client = AiOpsClient(
        agent_key_id="ak",
        agent_secret="sec",
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    thread = _HeartbeatThread(client, interval_seconds=30)
    thread._interval = 0.01  # white-box: skip the real 30s floor for this test
    thread.start()
    thread._stop_event.wait(0.05)
    thread.stop()
    thread.join(timeout=2)
    client.close()

    assert call_count["n"] >= 1


def test_heartbeat_thread_swallows_errors_and_keeps_running() -> None:
    from aiops_enabler import AiOpsClient

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        raise httpx.ConnectError("boom", request=request)

    client = AiOpsClient(
        agent_key_id="ak",
        agent_secret="sec",
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )
    thread = _HeartbeatThread(client, interval_seconds=30)
    thread._interval = 0.01
    thread.start()
    thread._stop_event.wait(0.05)
    thread.stop()
    thread.join(timeout=2)
    client.close()

    assert call_count["n"] >= 1
    assert thread.is_alive() is False
