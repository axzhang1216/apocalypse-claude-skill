#!/usr/bin/env python3
"""Apocalypse CLI entry point.

Builds the top-level argparse with proper subparser support and dispatches to
either the legacy launcher (no subcommand) or one of the new subcommand
modules (`apocalypse log`, `apocalypse workspace`).
"""
import argparse
import sys
from pathlib import Path

# Make `skills_apocalypse` importable when the wrapper script runs us.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apocalypse import launcher  # noqa: E402


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="apocalypse",
        description=(
            "Apocalypse — Claude Code / OpenAI Codex session browser.\n\n"
            "Browse recent sessions, resume them in a new terminal, and (on Linux/SSH) "
            "view full transcripts and the project map without leaving the terminal."
        ),
        epilog=(
            "Examples:\n"
            "  apocalypse                       Interactive menu (recent sessions)\n"
            "  apocalypse --list                Dump projects as JSON\n"
            "  apocalypse log <sid>             Open a session transcript in pager\n"
            "  apocalypse log <sid> --raw | less -R   Plain ANSI for piping\n"
            "  apocalypse workspace             Browse all projects (3-level tree)\n"
            "  apocalypse --codex workspace     Browse Codex sessions instead\n"
            "\n"
            "Headless mode is auto-detected from $SSH_CONNECTION and $DISPLAY.\n"
            "On SSH, the menu prints resume commands instead of opening a GUI terminal."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(
        dest="subcommand",
        title="subcommands",
        metavar="<subcommand>",
        description="Run `apocalypse <subcommand> --help` for subcommand-specific help.",
    )

    p_log = sub.add_parser(
        "log",
        help="View a session's full transcript in an interactive pager",
        description=(
            "Open a session transcript (user/assistant turns + tool calls) in a "
            "full-screen pager. Press `t` to toggle tool-block expansion, `q` to quit."
        ),
    )
    p_log.add_argument(
        "session_id",
        metavar="<session-id>",
        help="Session ID (from `apocalypse --list`)",
    )
    p_log.add_argument(
        "--raw",
        action="store_true",
        help="Print ANSI-coloured text without pager (for piping to `less -R`)",
    )
    p_log.add_argument(
        "--tail",
        action="store_true",
        help="Watch the session live (SSE-style tail)",
    )

    p_ws = sub.add_parser(
        "workspace",
        help="Browse all projects in a 3-level tree (top → project → points)",
        description=(
            "Interactive project map. Enter to drill into a project, Esc to go back, "
            "q to quit. Type `/` to filter by text."
        ),
    )
    p_ws.add_argument(
        "--search",
        metavar="<query>",
        default=None,
        help="Pre-fill the filter query",
    )

    p.add_argument(
        "--refresh",
        action="store_true",
        help="Incrementally re-analyse new sessions in the background (silent)",
    )
    p.add_argument(
        "--update",
        action="store_true",
        help="Full workspace update: analyse new sessions, assign themes, show summary",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="Print all projects and their sessions as JSON",
    )
    p.add_argument(
        "--codex",
        action="store_true",
        help="Use OpenAI Codex CLI source instead of Claude Code",
    )
    return p


def main() -> int:
    parser = _build_argparser()
    args = parser.parse_args()

    if args.subcommand == "log":
        from apocalypse import log_view
        return log_view.run(args.session_id, raw=args.raw, tail=args.tail)
    if args.subcommand == "workspace":
        from apocalypse import workspace_view
        return workspace_view.run(search=args.search, codex=args.codex)

    # No subcommand: hand off to the existing launcher (handles --list,
    # --update, --refresh, and the interactive menu).
    return launcher.run(args) or 0


if __name__ == "__main__":
    sys.exit(main())
