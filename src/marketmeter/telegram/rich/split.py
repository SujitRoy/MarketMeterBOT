"""
telegram/rich/split — split Rich Markdown into chunks under Telegram limits.
"""
from __future__ import annotations

import re
from typing import Optional

from marketmeter.core.config import (
    REPORT_CHUNK_MAX_CHARS,
    TELEGRAM_MAX_CHARS,
)

# A table separator row, e.g. "|:-:|:------|------:|". Used to locate the
# two-line header that must be repeated when a table spans chunks.
_TABLE_SEP_RE = re.compile(r'^\|[\s:\-|]+\|$')


def _split_rich_markdown(
    text: str,
    max_chars: int = REPORT_CHUNK_MAX_CHARS
) -> list[str]:
    """
    Split Rich Markdown into chunks under Telegram's 4096-char cap.

    Splitting on length alone corrupts structure, so this keeps two invariants:

    * A <details> block is never cut open. A chunk ending mid-block would leave
      an unclosed tag and the next chunk would start with orphaned content.
    * A table that spans a boundary gets its header and separator rows repeated
      at the top of the continuation chunk. Without them the server sees plain
      pipe text and renders no table.
    """
    lines = text.split('\n')
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    details_depth = 0
    tbl_header: Optional[tuple[str, str]] = None

    def flush() -> None:
        nonlocal cur, cur_len
        body = '\n'.join(cur).strip()
        if body:
            chunks.append(body)
        cur = []
        cur_len = 0

    for line in lines:
        stripped = line.strip()

        # Remember the active table header (previous line + this separator).
        if _TABLE_SEP_RE.match(stripped) and cur and cur[-1].lstrip().startswith('|'):
            tbl_header = (cur[-1], line)
        elif stripped and not stripped.startswith('|'):
            tbl_header = None  # non-table content ends the table

        cost = len(line) + 1

        # A <details> block must travel whole. Break *before* one starts if the
        # current chunk is already large, rather than discovering mid-block that
        # the hard ceiling has been hit and cutting the tag open.
        if (stripped.startswith('<details') and details_depth == 0 and cur
                and cur_len + cost > max_chars // 2):
            flush()

        over = cur_len + cost > max_chars
        # Only force a break inside <details> as an absolute last resort, when a
        # single block cannot fit a message on its own.
        hard_over = cur_len + cost > TELEGRAM_MAX_CHARS - 256

        if cur and (over or hard_over) and (details_depth == 0 or hard_over):
            resume_table = stripped.startswith('|') and tbl_header is not None
            flush()
            if resume_table:
                cur = [tbl_header[0], tbl_header[1]]
                cur_len = sum(len(x) + 1 for x in cur)

        cur.append(line)
        cur_len += cost

        if '<details' in line:
            details_depth += 1
        if '</details>' in line:
            details_depth = max(0, details_depth - 1)

    flush()

    # Last-resort guard so a chunk can never exceed the hard cap.
    safe: list[str] = []
    for ch in chunks:
        while len(ch) > TELEGRAM_MAX_CHARS:
            safe.append(ch[:TELEGRAM_MAX_CHARS])
            ch = ch[TELEGRAM_MAX_CHARS:]
        if ch:
            safe.append(ch)
    return safe or [text[:TELEGRAM_MAX_CHARS]]


__all__ = ["_split_rich_markdown"]