#!/usr/bin/env python3
"""Entry point. argparse dispatch and headless detection."""
import sys
import os

# Add the parent directory to path so we can import the launcher
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apocalypse.launcher import run, _build_argparser, _dispatch, is_headless


def main() -> int:
    parser = _build_argparser()
    parser.add_argument("subcommand", nargs="?", help="Subcommand to run (log, workspace)")
    args, remaining = parser.parse_known_args()

    # Pass remaining args to subcommand
    if args.subcommand:
        sys.argv = [sys.argv[0], args.subcommand] + remaining
        _dispatch(args)
    else:
        run(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())