from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

_EXPECTED = {
    "enabled": ("bool", False),
    "default_source": ("string", ""),
    "fissure_source": ("string", ""),
    "market_source": ("string", ""),
    "worldstate_source": ("string", ""),
    "background_fit": ("string", "cover"),
    "background_position": ("string", "center center"),
    "overlay_enabled": ("bool", True),
    "overlay_color": ("string", "#0f172a"),
    "overlay_opacity": ("int", 42),
    "panel_color": ("string", "#0f172a"),
    "panel_opacity": ("int", 58),
    "glass_enabled": ("bool", True),
    "blur_px": ("int", 6),
    "text_mode": ("string", "light"),
}


def _background_schema() -> dict:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    return schema["render_background"]


def test_background_schema_exposes_every_configurable_field():
    background = _background_schema()

    assert background["type"] == "object"
    assert set(background["items"]) == set(_EXPECTED)
    for name, (expected_type, expected_default) in _EXPECTED.items():
        field = background["items"][name]
        assert field["type"] == expected_type
        assert field["default"] == expected_default
        assert field["description"].strip()
        assert field["hint"].strip()


def test_glass_switch_and_blur_are_independent_fields():
    items = _background_schema()["items"]

    assert items["glass_enabled"] == {
        "type": "bool",
        "default": True,
        "description": items["glass_enabled"]["description"],
        "hint": items["glass_enabled"]["hint"],
    }
    assert items["blur_px"]["type"] == "int"
    assert items["blur_px"]["default"] == 6
