"""`aiops` command-line entry point: `aiops join` and `aiops wrap -- <command>`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from aiops_wrap import __version__
from aiops_wrap.config import DEFAULT_BASE_URL, load_settings, save_global_setting
from aiops_wrap.join import JoinError, join
from aiops_wrap.wrap import run_wrapped


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiops",
        description="Instrument any scripted agent with zero code changes.",
    )
    parser.add_argument("--version", action="version", version=f"aiops-wrap {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    join_parser = subparsers.add_parser(
        "join", help="Self-register this agent with AiOps Enabler and store credentials."
    )
    join_parser.add_argument(
        "--email", required=True, help="Operator email (never shown publicly)."
    )
    join_parser.add_argument("--name", help="Agent name (defaults to the current directory name).")
    join_parser.add_argument(
        "--category",
        default="other",
        choices=["incident-response", "alert-triage", "remediation", "observability", "other"],
    )
    join_parser.add_argument("--description")
    join_parser.add_argument("--repo-url")
    join_parser.add_argument("--base-url", default=DEFAULT_BASE_URL)

    wrap_parser = subparsers.add_parser("wrap", help="Run a command and report it as a task event.")
    wrap_parser.add_argument(
        "wrapped_command",
        nargs=argparse.REMAINDER,
        help="The command to run, e.g. `aiops wrap -- python my_agent.py`.",
    )
    wrap_parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress reporting warnings."
    )

    configure_parser = subparsers.add_parser(
        "configure", help="Set a persistent, non-secret config value in ~/.aiops/config.json."
    )
    configure_parser.add_argument(
        "key", choices=["category", "heartbeat_interval_seconds", "enabled", "base_url"]
    )
    configure_parser.add_argument("value")

    return parser


def _run_join(args: argparse.Namespace) -> int:
    import os

    name = args.name or os.path.basename(os.getcwd())
    try:
        result = join(
            email=args.email,
            name=name,
            category=args.category,
            description=args.description,
            repo_url=args.repo_url,
            base_url=args.base_url,
        )
    except (JoinError, ValueError) as exc:
        print(f"aiops join failed: {exc}", file=sys.stderr)
        return 1

    print(f"Joined as '{result.agent_name}' (slug: {result.agent_slug}).")
    print(f"Credentials saved to ~/.aiops/credentials.json (key id: {result.key_id}).")
    print(result.claim_note)
    print("Run `aiops wrap -- <your command>` to start reporting task events.")
    return 0


def _run_wrap(args: argparse.Namespace) -> int:
    command = list(args.wrapped_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print(
            "aiops wrap: no command given. Usage: aiops wrap -- <command> [args...]",
            file=sys.stderr,
        )
        return 2

    settings = load_settings()
    result = run_wrapped(command, settings=settings, quiet=args.quiet)
    return result.exit_code


def _run_configure(args: argparse.Namespace) -> int:
    value: object = args.value
    if args.key == "heartbeat_interval_seconds":
        value = int(args.value)
    elif args.key == "enabled":
        value = args.value.strip().lower() not in ("0", "false", "no", "off")
    save_global_setting(args.key, value)
    print(f"Set {args.key} = {value!r} in ~/.aiops/config.json")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "join":
        return _run_join(args)
    if args.command == "wrap":
        return _run_wrap(args)
    if args.command == "configure":
        return _run_configure(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
