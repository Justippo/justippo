"""Lightweight terminal colour utilities — zero backend dependencies.

Safe for any script to import (no httpx, no D1, no Cloudflare config).
Exposes ANSI escape codes that gracefully degrade to empty strings
when stdout is not a TTY (CI logs, pipes, redirects).
"""

from __future__ import annotations

import sys

_IS_TTY: bool = sys.stdout.isatty()

if _IS_TTY:
    RESET = "\033[0m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
else:
    RESET = GREEN = RED = BOLD = DIM = CYAN = YELLOW = ""


def hr() -> None:
    print("-" * 72)
