"""
telegram/rich/detect — detect if text needs Rich Message rendering.
"""
from __future__ import annotations

# A table separator row, e.g. "|:-:|:------|------:|". Used to locate the
# two-line header that must be repeated when a table spans chunks.
import re
_TABLE_SEP_RE = re.compile(r'^\|[\s:\-|]+\|$')


def _needs_rich(text: str) -> bool:
    """
    True when text uses syntax legacy Markdown V1 cannot render.

    V1 has no tables, no <details>, and treats ** as literal, which is why the
    report arrived with bold markers stripped and raw table pipes visible.
    """
    if '**' in text or '<details' in text:
        return True
    return any(ln.startswith('|') for ln in text.split('\n'))


__all__ = ["_needs_rich"]