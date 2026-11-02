from __future__ import annotations

from html import escape
from typing import Iterable

LIMIT = 4096


def chapter_parts(title: str, verses: Iterable[str], footer: str) -> list[str]:
    """Build Telegram-safe HTML chunks, retaining complete verses whenever possible."""
    room = LIMIT - len(title) - len(footer) - 32
    chunks: list[list[str]] = [[]]
    for number, verse in enumerate(verses, 1):
        item = f"{number}. {escape(verse)}"
        if len(item) <= room:
            if chunks[-1] and len("\n".join(chunks[-1] + [item])) > room:
                chunks.append([])
            chunks[-1].append(item)
            continue
        # A pathological single long verse: split at a word boundary, then at a
        # character boundary only if one word itself exceeds Telegram's limit.
        rest = item
        while rest:
            if len(rest) <= room:
                chunks[-1].append(rest)
                break
            cut = rest.rfind(" ", 0, room)
            if cut <= 0:
                cut = room
            chunks[-1].append(rest[:cut])
            rest = rest[cut:].lstrip()
            chunks.append([])
    if not chunks[-1]: chunks.pop()
    total = len(chunks)
    return [f"{title}\n<i>Часть {index}/{total}</i>\n\n" + "\n".join(chunk) + footer for index, chunk in enumerate(chunks, 1)]
