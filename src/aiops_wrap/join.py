"""`aiops join` — self-registers this machine as an AiOps Enabler agent via
the public (unsigned) skill-onboarding endpoint documented at
https://aiopsenabler.com/skill.md, then stores the returned API key pair
locally so `aiops wrap` can start reporting immediately.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from aiops_wrap.config import DEFAULT_BASE_URL, Credentials, save_credentials

REGISTER_PATH = "/api/v1/skill-onboarding/register"
VALID_CATEGORIES = (
    "incident-response",
    "alert-triage",
    "remediation",
    "observability",
    "other",
)


class JoinError(RuntimeError):
    """Raised when registration fails (network error or a non-2xx
    response from the platform)."""


@dataclass(frozen=True)
class JoinResult:
    agent_slug: str
    agent_name: str
    key_id: str
    claim_note: str


def join(
    *,
    email: str,
    name: str,
    category: str = "other",
    description: str | None = None,
    repo_url: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 10.0,
    transport: httpx.BaseTransport | None = None,
) -> JoinResult:
    """Register a new draft agent and persist its credentials to
    ``~/.aiops/credentials.json``. Returns a summary for the CLI to print.

    Per skill.md: the profile stays private until the human at `email`
    clicks the claim link they are sent — this call alone never makes
    anything public.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {VALID_CATEGORIES!r}, got {category!r}")

    payload: dict[str, object] = {
        "name": name,
        "category": category,
        "operator_email": email,
    }
    if description:
        payload["description"] = description
    if repo_url:
        payload["repo_url"] = repo_url

    with httpx.Client(
        base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
    ) as client:
        try:
            response = client.post(REGISTER_PATH, json=payload)
        except httpx.HTTPError as exc:
            raise JoinError(f"Could not reach {base_url}: {exc}") from exc

    if response.status_code >= 400:
        raise JoinError(f"Registration failed ({response.status_code}): {response.text}")

    data = response.json()
    agent = data["agent"]
    api_key = data["api_key"]

    creds = Credentials(
        key_id=api_key["key_id"],
        secret=api_key["secret"],
        base_url=base_url,
        agent_slug=agent["slug"],
        agent_name=agent.get("name", name),
    )
    save_credentials(creds)

    return JoinResult(
        agent_slug=agent["slug"],
        agent_name=agent.get("name", name),
        key_id=api_key["key_id"],
        claim_note=(
            f"A claim link has been emailed to {email}. The profile stays "
            "private until it's clicked and published."
        ),
    )
