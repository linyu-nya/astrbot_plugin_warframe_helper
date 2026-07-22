from __future__ import annotations

from collections.abc import Iterable


def has_explicit_at_component(components: Iterable[object]) -> bool:
    return any(type(component).__name__.casefold() == "at" for component in components)


def no_prefix_skip_reason(
    text: str,
    *,
    wake_or_command: bool,
    has_explicit_at: bool,
) -> str | None:
    """Return why a message must stay in AstrBot's regular command flow.

    AstrBot may set ``is_at_or_wake_command`` on ordinary group messages, so
    that flag alone is not evidence that another command handler will reply.
    """

    _ = wake_or_command
    normalized = (text or "").strip()
    if not normalized or normalized.startswith("/"):
        return "empty_or_slash"
    if has_explicit_at:
        return "explicit_at"
    return None
