"""CLI launch boundary; no optional SDK import before serve is requested."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sqlite3
import sys
from collections.abc import Sequence

from .. import __version__
from . import CONTRACT_VERSION


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pinak-mcp", description="Pinak-MCP local media tools")
    parser.add_argument(
        "--version",
        action="version",
        version=f"Pinak-MCP {__version__} (contract {CONTRACT_VERSION})",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Serve local MCP over stdio")
    serve.add_argument("--transport", choices=["stdio"], default="stdio")
    doctor = commands.add_parser("doctor", help="Check local readiness without repair side effects")
    doctor.add_argument("--json", action="store_true")
    commands.add_parser(
        "prepare-update", help="Refuse active runs and back up local state; never install updates"
    )
    configure = commands.add_parser("configure", help="Preview a desktop client configuration")
    configure.add_argument("--client", choices=["stdio", "claude-desktop"], default="stdio")
    configure.add_argument("--apply", action="store_true")
    configure.add_argument("--target", help="Override the client config file location")
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            try:
                sdk = importlib.metadata.version("mcp")
            except importlib.metadata.PackageNotFoundError:
                sdk = None
            if sdk != "2.3.0":
                print(
                    'Pinak-MCP requires SDK 2.3.0 in this interpreter. Install with: python -m pip install "pinak-cli[mcp]"',
                    file=sys.stderr,
                )
                return 2
            try:
                from .server import serve_stdio
            except ModuleNotFoundError as exc:
                if not (exc.name or "").startswith("pinak"):
                    print(
                        'Install the MCP extra in this interpreter: python -m pip install "pinak-cli[mcp]"',
                        file=sys.stderr,
                    )
                    return 2
                raise
            serve_stdio()
        elif args.command == "doctor":
            from .setup import diagnose

            result = diagnose()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready"] else 1
        elif args.command == "prepare-update":
            from .updates import prepare_update

            print(json.dumps(prepare_update(), ensure_ascii=False, indent=2))
        else:
            from .setup import configure_client, connection_profile

            if args.client == "stdio":
                if args.apply or args.target:
                    raise ValueError(
                        "Generic stdio prints launch fields only; use your AI client's MCP settings to register them. --apply/--target require --client claude-desktop."
                    )
                print(
                    json.dumps(
                        {
                            "applied": False,
                            "launch": connection_profile(),
                            "next_step": "Register these launch fields using your client's local stdio MCP settings. Host configuration formats differ; this is not a universal config file.",
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0
            print(
                json.dumps(
                    configure_client(args.target, apply=args.apply), ensure_ascii=False, indent=2
                )
            )
        return 0
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        from .policy import clean

        print(f"Pinak-MCP: {clean(str(exc))}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(
            f"Pinak-MCP stopped after {type(exc).__name__}; run pinak-mcp doctor for local diagnostics.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
