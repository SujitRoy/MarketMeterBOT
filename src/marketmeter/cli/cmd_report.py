"""
cli/cmd_report — generate and print report command.
"""
from __future__ import annotations

import re

from marketmeter.reports import generate_morning_report


def _strip_rich(text: str) -> str:
    """Convert Rich Markdown to plain text for terminal output.

    The morning report is Rich Markdown for the Bot API 10.1+ local server
    (tables, <details>, **bold**). Printed raw to a terminal, the tags and
    pipes are unreadable, so we strip them for the CLI consumer only.
    """
    out = re.sub(r"<details\b[^>]*>|</details>|<summary>|</summary>", "", text)
    out = out.replace("**", "")
    out = out.replace("\\*", "*")  # un-escape literal asterisks
    return out


async def cmd_report():
    """Generate and print report once."""
    report = generate_morning_report()
    print(_strip_rich(report))


__all__ = ["cmd_report"]