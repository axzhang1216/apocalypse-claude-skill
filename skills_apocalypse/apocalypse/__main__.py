"""Entry point. argparse dispatch and headless detection.

This file starts as a stub; the real argparse + launcher delegation
arrives in Task 2.
"""
import sys


def main() -> int:
    print("apocalypse: package skeleton (no menu yet — see Task 2)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())