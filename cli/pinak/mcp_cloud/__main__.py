"""Operator-only provisioning and explicit cloud startup."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sqlite3
import sys

from .registry import Registry
from .settings import Settings


def main() -> int:
    parser = argparse.ArgumentParser(prog="pinak-mcp-cloud")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Serve private remote MCP; HTTPS proxy required")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    users = commands.add_parser("users", help="Operator-only user management; no remote admin API")
    user_commands = users.add_subparsers(dest="action", required=True)
    for action in ("add", "rotate", "revoke"):
        user_commands.add_parser(action).add_argument("name")
    user_commands.add_parser("list")
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        if args.command == "serve":
            try:
                if importlib.metadata.version("mcp") != "2.3.0":
                    raise ValueError(
                        "This build requires MCP SDK 2.3.0; install the supplied locked dependencies."
                    )
                import uvicorn

                from .app import create_app
            except (ModuleNotFoundError, importlib.metadata.PackageNotFoundError):
                print(
                    "Install this bundle's wheel with its [cloud] extra in this interpreter.",
                    file=sys.stderr,
                )
                return 2

            uvicorn.run(
                create_app(settings),
                host=args.host,
                port=args.port,
                access_log=False,
                proxy_headers=False,
                timeout_graceful_shutdown=30,
            )
        else:
            registry = Registry(settings)
            if args.action == "list":
                print(json.dumps(registry.list_users(), indent=2))
            elif args.action == "add":
                print(json.dumps({"user": args.name, "token": registry.create(args.name)}))
            else:
                token = registry.rotate(args.name, revoke=args.action == "revoke")
                print(
                    json.dumps(
                        {"user": args.name, "token": token, "revoked": args.action == "revoke"}
                    )
                )
        return 0
    except (ValueError, OSError) as exc:
        print(f"Pinak cloud: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error:
        print(
            "Pinak cloud: registry operation failed; check duplicate names, permissions and disk space.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
