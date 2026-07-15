from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from aiops_wrap.config import load_credentials
from aiops_wrap.join import JoinError, join

Handler = Callable[[httpx.Request], httpx.Response]


def _transport(handler: Handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_join_posts_registration_and_saves_credentials() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            201,
            json={
                "agent": {"id": "agt_1", "slug": "my-incident-bot", "name": "My Incident Bot"},
                "api_key": {"key_id": "ak_new", "secret": "brand-new-secret"},
            },
        )

    result = join(
        email="op@example.com",
        name="My Incident Bot",
        category="incident-response",
        base_url="https://example.test",
        transport=_transport(handler),
    )

    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/skill-onboarding/register"
    body = json.loads(request.content)
    assert body == {
        "name": "My Incident Bot",
        "category": "incident-response",
        "operator_email": "op@example.com",
    }

    assert result.agent_slug == "my-incident-bot"
    assert result.key_id == "ak_new"
    assert "op@example.com" in result.claim_note

    creds = load_credentials()
    assert creds.key_id == "ak_new"
    assert creds.secret == "brand-new-secret"
    assert creds.agent_slug == "my-incident-bot"


def test_join_includes_optional_fields_when_provided() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            201,
            json={
                "agent": {"slug": "s", "name": "n"},
                "api_key": {"key_id": "k", "secret": "s"},
            },
        )

    join(
        email="op@example.com",
        name="Agent",
        description="Does things.",
        repo_url="https://github.com/x/y",
        base_url="https://example.test",
        transport=_transport(handler),
    )

    body = json.loads(captured["request"].content)
    assert body["description"] == "Does things."
    assert body["repo_url"] == "https://github.com/x/y"


def test_join_rejects_invalid_category() -> None:
    with pytest.raises(ValueError):
        join(email="op@example.com", name="Agent", category="not-a-real-category")


def test_join_raises_join_error_on_4xx_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="operator_email is required")

    with pytest.raises(JoinError):
        join(
            email="op@example.com",
            name="Agent",
            base_url="https://example.test",
            transport=_transport(handler),
        )


def test_join_raises_join_error_on_network_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(JoinError):
        join(
            email="op@example.com",
            name="Agent",
            base_url="https://example.test",
            transport=_transport(handler),
        )
