"""`aiops wrap -- <command>` — runs an arbitrary command as a child
process and reports it to AiOps Enabler as a task event (task_started /
task_completed with duration + exit-code-derived outcome), with periodic
heartbeats for long-running processes.

Reporting is always best-effort: a network failure, missing credentials,
or an opted-out config must never change the wrapped command's exit code,
block it, or crash this process. The child's own stdout/stderr/stdin are
inherited untouched — from the wrapped program's point of view, nothing
about how it runs has changed (CLAUDE.md/E1's "zero code changes" promise).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Literal

import httpx
from aiops_enabler import AiOpsClient

from aiops_wrap.config import NotJoinedError, Settings, load_credentials, load_settings


def _warn(message: str) -> None:
    print(f"aiops-wrap: {message}", file=sys.stderr)


@dataclass(frozen=True)
class WrapResult:
    exit_code: int
    task_id: str
    reported: bool


class _HeartbeatThread(threading.Thread):
    """Calls `client.heartbeat()` every `interval_seconds` until stopped.
    Any failure is swallowed (best-effort) and logged once per failure."""

    def __init__(self, client: AiOpsClient, interval_seconds: int) -> None:
        super().__init__(daemon=True)
        self._client = client
        self._interval = max(interval_seconds, 30)
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._client.heartbeat()
            except Exception as exc:  # best-effort, never fatal
                _warn(f"heartbeat failed (will retry): {exc}")

    def stop(self) -> None:
        self._stop_event.set()


def run_wrapped(
    command: list[str],
    *,
    settings: Settings | None = None,
    quiet: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> WrapResult:
    """Run `command` as a child process; report it if reporting is
    configured and enabled. Always returns the child's real exit code.

    `transport` is exposed purely for tests (injected into the
    `AiOpsClient`, matching the SDK's own testability pattern) — real
    callers never need it.
    """
    if not command:
        raise ValueError("command must be non-empty")

    resolved_settings = settings or load_settings()
    task_id = uuid.uuid4().hex
    client: AiOpsClient | None = None

    if not resolved_settings.enabled:
        if not quiet:
            _warn("reporting disabled (enabled=false in config) - running without reporting")
    else:
        try:
            creds = load_credentials()
            client = AiOpsClient(
                agent_key_id=creds.key_id,
                agent_secret=creds.secret,
                base_url=creds.base_url or resolved_settings.base_url,
                transport=transport,
            )
        except NotJoinedError as exc:
            if not quiet:
                _warn(f"{exc} - running without reporting")

    heartbeat_thread: _HeartbeatThread | None = None
    start = time.monotonic()

    if client is not None:
        try:
            client.task_started(task_id=task_id)
        except Exception as exc:  # best-effort: never block the wrapped command
            if not quiet:
                _warn(f"could not report task_started: {exc}")
        else:
            heartbeat_thread = _HeartbeatThread(
                client, resolved_settings.heartbeat_interval_seconds
            )
            heartbeat_thread.start()

    process = subprocess.run(command)
    duration_ms = int((time.monotonic() - start) * 1000)
    exit_code = process.returncode

    if heartbeat_thread is not None:
        heartbeat_thread.stop()
        heartbeat_thread.join(timeout=5)

    reported = False
    if client is not None:
        outcome: Literal["success", "failure"] = "success" if exit_code == 0 else "failure"
        try:
            client.task_completed(
                task_id=task_id,
                outcome=outcome,
                duration_ms=duration_ms,
                category=resolved_settings.category,
            )
            reported = True
        except Exception as exc:  # best-effort: never change the exit code
            if not quiet:
                _warn(f"could not report task_completed: {exc}")
        finally:
            client.close()

    return WrapResult(exit_code=exit_code, task_id=task_id, reported=reported)
