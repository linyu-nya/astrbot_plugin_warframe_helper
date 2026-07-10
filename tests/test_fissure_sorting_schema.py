from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVICES_PACKAGE = "astrbot_plugin_warframe_helper.services"


def _sorting_module():
    existing_services_package = sys.modules.get(SERVICES_PACKAGE)
    services_package = types.ModuleType(SERVICES_PACKAGE)
    services_package.__path__ = [str(ROOT / "services")]
    sys.modules[SERVICES_PACKAGE] = services_package
    try:
        from astrbot_plugin_warframe_helper.services import fissure_sorting

        return fissure_sorting
    finally:
        if existing_services_package is None:
            sys.modules.pop(SERVICES_PACKAGE, None)
        else:
            sys.modules[SERVICES_PACKAGE] = existing_services_package


def test_fissure_tier_sort_schema_is_enabled_by_default() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))

    field = schema["fissure_tier_sort_enabled"]
    assert field["type"] == "bool"
    assert field["default"] is True
    assert field["description"] == "裂缝按纪元排序"
    assert "古前中后安魂全能" in field["hint"]
    assert "同纪元按剩余时间" in field["hint"]
    assert "关闭后仅按剩余时间" in field["hint"]


@pytest.mark.parametrize(
    "config",
    [
        None,
        [],
        "invalid",
        {},
        {"other": False},
        {"fissure_tier_sort_enabled": None},
        {"fissure_tier_sort_enabled": 0},
        {"fissure_tier_sort_enabled": "false"},
    ],
)
def test_fissure_tier_sort_parser_uses_true_for_missing_or_invalid_values(
    config: object,
) -> None:
    parser = getattr(_sorting_module(), "fissure_tier_sort_enabled")

    assert parser(config) is True


def test_fissure_tier_sort_parser_preserves_explicit_false() -> None:
    parser = getattr(_sorting_module(), "fissure_tier_sort_enabled")

    assert parser({"fissure_tier_sort_enabled": False}) is False


def test_fissure_tier_sort_parser_preserves_explicit_true() -> None:
    parser = getattr(_sorting_module(), "fissure_tier_sort_enabled")

    assert parser({"fissure_tier_sort_enabled": True}) is True
