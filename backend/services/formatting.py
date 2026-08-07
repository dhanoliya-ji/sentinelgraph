"""Plain-language helpers.

The brief is that a non-technical analyst should be able to use this app. Every
detection result therefore ships with a `summary` sentence generated here, so
the UI can lead with English and keep the raw IDs in a collapsible section.
"""

from __future__ import annotations


def money(amount: float | int | None, currency: str = "USD") -> str:
    if amount is None:
        return "an unknown amount"
    symbol = "$" if currency == "USD" else ""
    return f"{symbol}{amount:,.0f}" if float(amount).is_integer() else f"{symbol}{amount:,.2f}"


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


def join_names(items: list[str], limit: int = 3) -> str:
    """'A, B and 4 others' -- keeps long lists readable in a sentence."""
    if not items:
        return "no accounts"
    if len(items) <= limit:
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + " and " + items[-1]
    shown = ", ".join(items[:limit])
    return f"{shown} and {len(items) - limit} others"


def describe_days(days: float | None) -> str:
    if days is None:
        return "an unknown period"
    if days < 1:
        return "under a day"
    if days < 2:
        return "about a day"
    return f"{days:.0f} days"
