from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path


_SERVICES_PACKAGE = "astrbot_plugin_warframe_helper.services"
_existing_services_package = sys.modules.get(_SERVICES_PACKAGE)
_services_package = types.ModuleType(_SERVICES_PACKAGE)
_services_package.__path__ = [str(Path(__file__).resolve().parents[1] / "services")]
sys.modules[_SERVICES_PACKAGE] = _services_package
try:
    from astrbot_plugin_warframe_helper.services.fissure_sorting import (
        FissureLike,
        sort_fissures,
    )
finally:
    if _existing_services_package is None:
        sys.modules.pop(_SERVICES_PACKAGE, None)
    else:
        sys.modules[_SERVICES_PACKAGE] = _existing_services_package


@dataclass(frozen=True)
class _Fissure:
    tier: str
    eta: str


def test_fissure_protocol_attributes_are_read_only_properties() -> None:
    tier_property = FissureLike.__dict__.get("tier")
    eta_property = FissureLike.__dict__.get("eta")

    assert isinstance(tier_property, property)
    assert tier_property.fset is None
    assert isinstance(eta_property, property)
    assert eta_property.fset is None


def test_tier_first_sorts_all_chinese_tiers_in_progression_order() -> None:
    fissures = [
        _Fissure("全能", "1分"),
        _Fissure("安魂", "1分"),
        _Fissure("后纪", "1分"),
        _Fissure("中纪", "1分"),
        _Fissure("前纪", "1分"),
        _Fissure("古纪", "1分"),
    ]

    result = sort_fissures(fissures, tier_first=True)

    assert [fissure.tier for fissure in result] == [
        "古纪",
        "前纪",
        "中纪",
        "后纪",
        "安魂",
        "全能",
    ]


def test_tier_first_sorts_matching_tiers_by_eta() -> None:
    fissures = [
        _Fissure("古纪", "30分"),
        _Fissure("Lith", "5分"),
        _Fissure("VoidT1", "12分"),
    ]

    result = sort_fissures(fissures, tier_first=True)

    assert [fissure.eta for fissure in result] == ["5分", "12分", "30分"]


def test_tier_first_recognizes_case_insensitive_english_and_code_aliases() -> None:
    fissures = [
        _Fissure("VOIDt6", "12分"),
        _Fissure("oMNia", "6分"),
        _Fissure("voidT5", "11分"),
        _Fissure("rEQuiem", "5分"),
        _Fissure("VOIDt4", "10分"),
        _Fissure("aXI", "4分"),
        _Fissure("voidT3", "9分"),
        _Fissure("nEO", "3分"),
        _Fissure("VOIDt2", "8分"),
        _Fissure("mESo", "2分"),
        _Fissure("voidT1", "7分"),
        _Fissure("lITh", "1分"),
    ]

    result = sort_fissures(fissures, tier_first=True)

    assert [fissure.tier for fissure in result] == [
        "lITh",
        "voidT1",
        "mESo",
        "VOIDt2",
        "nEO",
        "voidT3",
        "aXI",
        "VOIDt4",
        "rEQuiem",
        "voidT5",
        "oMNia",
        "VOIDt6",
    ]


def test_tier_first_keeps_unknown_tiers_after_known_tiers_and_sorts_their_eta() -> None:
    fissures = [
        _Fissure("未知甲", "20分"),
        _Fissure("后纪", "40分"),
        _Fissure("UnknownBeta", "5分"),
    ]

    result = sort_fissures(fissures, tier_first=True)

    assert [(fissure.tier, fissure.eta) for fissure in result] == [
        ("后纪", "40分"),
        ("UnknownBeta", "5分"),
        ("未知甲", "20分"),
    ]


def test_tier_first_keeps_input_order_for_identical_sort_keys() -> None:
    first = _Fissure("古纪", "10分")
    second = _Fissure("古纪", "10分")

    result = sort_fissures([first, second], tier_first=True)

    assert result[0] is first
    assert result[1] is second


def test_tier_first_treats_empty_and_blank_tiers_as_unknown() -> None:
    fissures = [
        _Fissure("", "20分"),
        _Fissure("古纪", "30分"),
        _Fissure("   ", "5分"),
    ]

    result = sort_fissures(fissures, tier_first=True)

    assert [(fissure.tier, fissure.eta) for fissure in result] == [
        ("古纪", "30分"),
        ("   ", "5分"),
        ("", "20分"),
    ]


def test_disabled_tier_sorting_sorts_only_by_eta() -> None:
    fissures = [
        _Fissure("古纪", "30分"),
        _Fissure("未知", "10分"),
        _Fissure("全能", "20分"),
    ]

    result = sort_fissures(fissures, tier_first=False)

    assert [fissure.eta for fissure in result] == ["10分", "20分", "30分"]


def test_sort_fissures_returns_a_new_list() -> None:
    fissures = [_Fissure("古纪", "10分")]

    result = sort_fissures(fissures, tier_first=True)

    assert result == fissures
    assert result is not fissures
