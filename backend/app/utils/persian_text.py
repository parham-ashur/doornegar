"""Utilities for Persian text processing."""

import re
import unicodedata


def normalize_persian(text: str) -> str:
    """Normalize Persian text for consistent storage and comparison.

    - Converts Arabic characters to Persian equivalents
    - Normalizes whitespace
    - Removes zero-width characters except ZWNJ (U+200C)
    """
    if not text:
        return text

    # Arabic -> Persian character mappings
    replacements = {
        "\u0643": "\u06A9",  # Arabic kaf -> Persian kaf
        "\u064A": "\u06CC",  # Arabic yeh -> Persian yeh
        "\u0649": "\u06CC",  # Arabic alef maksura -> Persian yeh
        "\u0624": "\u0648",  # Arabic waw with hamza -> waw
        "\u0626": "\u06CC",  # Arabic yeh with hamza -> yeh
    }
    for arabic, persian in replacements.items():
        text = text.replace(arabic, persian)

    # Normalize Unicode (NFC form)
    text = unicodedata.normalize("NFC", text)

    # Remove zero-width chars except ZWNJ
    text = re.sub(r"[\u200B\u200D\u200E\u200F\uFEFF]", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def truncate_persian(text: str, max_chars: int = 200) -> str:
    """Truncate text at word boundary, respecting Persian text."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.5:
        truncated = truncated[:last_space]
    return truncated + "..."
