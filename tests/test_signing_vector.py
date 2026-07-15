"""aiops-wrap has no signing implementation of its own — it depends on the
official `aiops-enabler` SDK for that. This test pins the published test
vector from https://aiopsenabler.com/api-guide.md against that dependency
so a bad SDK upgrade (or a future switch away from it) is caught here too,
not just in the SDK's own test suite."""

from __future__ import annotations

from aiops_enabler.signing import compute_signature, secret_hash

SECRET = "correct-horse-battery-staple-test-secret"
TIMESTAMP = "1700000000"
BODY = b'{"event_type":"task_started","task_id":"demo-task-1"}'
EXPECTED_SECRET_HASH = "285beb7adbdb73adc3d35e65fe7d2a4b958f1e12d790e39c82703e29743034c6"
EXPECTED_SIGNATURE = "ea3906dd25d6ff6edd668e64634f1e10698a7b9b31d5160fa1a28951102e62e9"


def test_secret_hash_matches_published_test_vector() -> None:
    assert secret_hash(SECRET) == EXPECTED_SECRET_HASH


def test_signature_matches_published_test_vector() -> None:
    signature = compute_signature(secret=SECRET, timestamp=TIMESTAMP, body=BODY)
    assert signature == EXPECTED_SIGNATURE
    assert len(signature) == 64
