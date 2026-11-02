from __future__ import annotations


def plural(value: int, one: str, few: str, many: str) -> str:
    """Return a Russian noun form for an integer (1 глава, 2 главы, 5 глав)."""
    value = abs(value)
    if 11 <= value % 100 <= 14:
        return many
    last = value % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many
