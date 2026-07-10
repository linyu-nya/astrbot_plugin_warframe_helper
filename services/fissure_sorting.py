from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol, TypeVar

from ..helpers import eta_key_zh


class FissureLike(Protocol):
    @property
    def tier(self) -> str:
        ...

    @property
    def eta(self) -> str:
        ...


FissureT = TypeVar("FissureT", bound=FissureLike)

_TIER_ORDER = (
    ("古纪", "lith", "voidt1"),
    ("前纪", "meso", "voidt2"),
    ("中纪", "neo", "voidt3"),
    ("后纪", "axi", "voidt4"),
    ("安魂", "requiem", "voidt5"),
    ("全能", "omnia", "voidt6"),
)
_TIER_RANK = {
    alias.casefold(): rank
    for rank, aliases in enumerate(_TIER_ORDER)
    for alias in aliases
}


def fissure_tier_sort_enabled(config: object) -> bool:
    if not isinstance(config, Mapping):
        return True
    value = config.get("fissure_tier_sort_enabled")
    return value if isinstance(value, bool) else True


def sort_fissures(
    fissures: Iterable[FissureT], *, tier_first: bool
) -> list[FissureT]:
    if not tier_first:
        return sorted(fissures, key=lambda fissure: eta_key_zh(fissure.eta))
    return sorted(
        fissures,
        key=lambda fissure: (
            _TIER_RANK.get(fissure.tier.strip().casefold(), len(_TIER_ORDER)),
            eta_key_zh(fissure.eta),
        ),
    )
