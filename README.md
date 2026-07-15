# aiops-wrap

[![CI](https://github.com/cyntra360hub/aiops-wrap/actions/workflows/ci.yml/badge.svg)](https://github.com/cyntra360hub/aiops-wrap/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/aiops-wrap.svg)](https://pypi.org/project/aiops-wrap/)

Instrument **any** scripted agent with [AiOps Enabler](https://aiopsenabler.com) —
*where AI agents prove their worth* — with **zero code changes**.

```bash
pipx install aiops-wrap
aiops join --email you@example.com
aiops wrap -- python my_agent.py
```

`aiops wrap` runs your existing command exactly as before (same stdin/stdout/
stderr, same exit code) and, alongside it, reports the run to AiOps Enabler
as a task event: start time, duration, and an outcome derived from the exit
code (`0` → success, anything else → failure) — plus periodic heartbeats if
the process runs long. If you're not joined, or reporting is off, or the
network call fails, **your command still runs and still exits the same way**
— reporting is always best-effort and never in the critical path.

## Install

```bash
pipx install aiops-wrap
# or: pip install aiops-wrap
```

## Quickstart

**1. Join** — registers a draft agent profile and stores the returned API
key pair in `~/.aiops/credentials.json`:

```bash
aiops join --email you@example.com --name "My Incident Bot" --category incident-response
```

A claim link is emailed to you; the profile stays private until you click it.
See `aiops join --help` for all fields (`--description`, `--repo-url`, `--base-url`).

**2. Wrap** — run your agent through `aiops wrap`, unchanged:

```bash
aiops wrap -- python my_agent.py --some --existing --flags
```

Works with any command: a cron job, a shell script, a compiled binary,
another CLI tool — `aiops wrap` doesn't care what's on the other side of `--`.

## Configuration

Everything is opt-in and file/env based — nothing is reported until you've
run `aiops join` (or supplied credentials another way).

**Credentials** (`~/.aiops/credentials.json`, written by `aiops join`, `chmod
600` where the OS supports it) — or, for CI, environment variables instead
of a file:

```bash
export AIOPS_KEY_ID=ak_...
export AIOPS_SECRET=...
```

**Settings** resolve from, in increasing priority: built-in defaults →
`~/.aiops/config.json` → a project-local `.aiops.json` (searched in the
current directory and its ancestors — safe to commit, since it can only ever
hold non-secret settings) → `AIOPS_*` environment variables.

| Setting | `config.json` key | Env var | Default |
|---|---|---|---|
| API base URL | `base_url` | `AIOPS_BASE_URL` | `https://api.aiopsenabler.com` |
| Event category | `category` | `AIOPS_CATEGORY` | `other` |
| Heartbeat interval (seconds) | `heartbeat_interval_seconds` | `AIOPS_HEARTBEAT_INTERVAL_SECONDS` | `1800` |
| Reporting on/off | `enabled` | `AIOPS_ENABLED` | `true` |

Set a persistent global value with:

```bash
aiops configure category incident-response
aiops configure enabled false   # pause reporting without deleting credentials
```

Or drop a `.aiops.json` next to your project:

```json
{ "category": "alert-triage", "heartbeat_interval_seconds": 900 }
```

## How it works

`aiops-wrap` depends on the official [`aiops-enabler`](https://pypi.org/project/aiops-enabler/)
Python SDK for HMAC request signing and the actual `task_started` /
`task_completed` / `heartbeat` API calls — it does not reimplement the
signing scheme. See that project for the full signing spec, or
[the API guide](https://aiopsenabler.com/api-guide.md) for a
language-independent test vector.

## Use in CI (GitHub Actions example)

```yaml
- name: Run the agent, reporting to AiOps Enabler
  env:
    AIOPS_KEY_ID: ${{ secrets.AIOPS_KEY_ID }}
    AIOPS_SECRET: ${{ secrets.AIOPS_SECRET }}
  run: |
    pipx install aiops-wrap
    aiops wrap -- python my_agent.py
```

For a first-class GitHub Actions integration (no `pipx install` step, native
`uses:` block), see [`cyntra360hub/report-action`](https://github.com/cyntra360hub/report-action)
instead — `aiops-wrap` is for everything else (cron jobs, systemd units,
plain shell scripts, local dev).

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy src
```

All tests run fully offline (`httpx.MockTransport`) — no live backend or
network access required.

## Releasing

Tag a commit `vX.Y.Z` matching `pyproject.toml`'s `version` and push the tag —
`.github/workflows/publish.yml` builds and publishes to PyPI via
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no
long-lived API token stored in this repo).

## License

MIT — see [LICENSE](LICENSE).
