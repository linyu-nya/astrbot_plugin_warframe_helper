from __future__ import annotations

import re
import unicodedata


def normalize_compact(text: str) -> str:
    """Normalize to a compact lowercase string without whitespace."""

    return re.sub(r"\s+", "", str(text or "").strip().lower())


def normalize_wiki_keyword(text: str) -> str:
    """Normalize whitespace and canonical title casing used by the Wiki."""

    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = re.sub(
        r"(?<![a-z])prime(?![a-z])",
        " Prime ",
        normalized,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", normalized).strip()


def safe_relic_name(text: str) -> str:
    """Keep only ASCII alnum for relic name matching."""

    s = re.sub(r"\s+", "", str(text or "").strip())
    s = re.sub(r"[^A-Za-z0-9]", "", s)
    return s
