from dataclasses import FrozenInstanceError, asdict

import pytest

from astrbot_plugin_warframe_helper.renderers.background_config import (
    RenderBackgroundConfig,
    parse_render_background_config,
)


def test_background_defaults_are_complete():
    config = parse_render_background_config({})

    assert asdict(config) == {
        "enabled": False,
        "default_source": "",
        "fissure_source": "",
        "market_source": "",
        "worldstate_source": "",
        "background_fit": "cover",
        "background_position": "center center",
        "overlay_enabled": True,
        "overlay_color": "#0f172a",
        "overlay_opacity": 42,
        "panel_color": "#0f172a",
        "panel_opacity": 58,
        "glass_enabled": True,
        "blur_px": 6,
        "text_mode": "light",
    }


def test_background_config_is_frozen_and_slotted():
    config = RenderBackgroundConfig()

    assert not hasattr(config, "__dict__")
    with pytest.raises(FrozenInstanceError):
        config.enabled = True


def test_all_background_sources_are_trimmed():
    config = parse_render_background_config(
        {
            "render_background": {
                "default_source": "  default.webp  ",
                "fissure_source": "\tfissure.png\n",
                "market_source": "  https://example.test/market.jpg\t",
                "worldstate_source": "\nworldstate.webp  ",
            }
        }
    )

    assert config.default_source == "default.webp"
    assert config.fissure_source == "fissure.png"
    assert config.market_source == "https://example.test/market.jpg"
    assert config.worldstate_source == "worldstate.webp"


@pytest.mark.parametrize(
    "field",
    [
        "default_source",
        "fissure_source",
        "market_source",
        "worldstate_source",
    ],
)
def test_invalid_background_sources_use_defaults(field):
    config = parse_render_background_config(
        {"render_background": {field: 123}}
    )

    assert getattr(config, field) == ""


def test_valid_background_numeric_values_are_preserved():
    config = parse_render_background_config(
        {
            "render_background": {
                "overlay_opacity": 17,
                "panel_opacity": 73,
                "blur_px": 12,
            }
        }
    )

    assert config.overlay_opacity == 17
    assert config.panel_opacity == 73
    assert config.blur_px == 12


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("overlay_opacity", -1, 0),
        ("overlay_opacity", 101, 100),
        ("panel_opacity", -1, 0),
        ("panel_opacity", 101, 100),
        ("blur_px", -1, 0),
        ("blur_px", 31, 30),
    ],
)
def test_background_numeric_values_are_clamped(field, value, expected):
    config = parse_render_background_config(
        {"render_background": {field: value}}
    )

    assert getattr(config, field) == expected


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("overlay_opacity", "opaque", 42),
        ("panel_opacity", None, 58),
        ("blur_px", True, 6),
    ],
)
def test_invalid_numeric_values_use_defaults(field, value, expected):
    config = parse_render_background_config(
        {"render_background": {field: value}}
    )

    assert getattr(config, field) == expected


@pytest.mark.parametrize("color", ["#abc", "#ABC", "#012345", "#aBcDeF"])
def test_valid_background_colors_are_accepted(color):
    config = parse_render_background_config(
        {
            "render_background": {
                "overlay_color": color,
                "panel_color": color,
            }
        }
    )

    assert config.overlay_color == color
    assert config.panel_color == color


@pytest.mark.parametrize(
    "color",
    [
        "",
        "abc",
        "#ab",
        "#abcd",
        "#12345g",
        "#12345678",
        "rgb(0, 0, 0)",
        "red; background:url(x)",
        None,
    ],
)
def test_invalid_background_colors_use_defaults(color):
    config = parse_render_background_config(
        {
            "render_background": {
                "overlay_color": color,
                "panel_color": color,
            }
        }
    )

    assert config.overlay_color == "#0f172a"
    assert config.panel_color == "#0f172a"


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ("left", "left"),
        ("center center", "center center"),
        ("right bottom", "right bottom"),
        ("top left", "top left"),
        ("0%", "0%"),
        ("100% 50%", "100% 50%"),
        ("33.5%   12.25%", "33.5% 12.25%"),
    ],
)
def test_valid_background_positions_are_accepted(position, expected):
    config = parse_render_background_config(
        {"render_background": {"background_position": position}}
    )

    assert config.background_position == expected


@pytest.mark.parametrize(
    "position",
    [
        "",
        "middle",
        "center; color:red",
        "center top left",
        "-1% center",
        "101% center",
        "calc(50% + 1px) center",
    ],
)
def test_invalid_background_positions_use_default(position):
    config = parse_render_background_config(
        {"render_background": {"background_position": position}}
    )

    assert config.background_position == "center center"


@pytest.mark.parametrize("fit", ["cover", "contain", "width", "repeat-y"])
def test_valid_background_fit_modes_are_accepted(fit):
    config = parse_render_background_config(
        {"render_background": {"background_fit": fit}}
    )

    assert config.background_fit == fit


@pytest.mark.parametrize("fit", ["stretch", "auto", "cover; color:red", None])
def test_invalid_background_fit_modes_use_default(fit):
    config = parse_render_background_config(
        {"render_background": {"background_fit": fit}}
    )

    assert config.background_fit == "cover"


@pytest.mark.parametrize("text_mode", ["light", "dark"])
def test_valid_text_modes_are_accepted(text_mode):
    config = parse_render_background_config(
        {"render_background": {"text_mode": text_mode}}
    )

    assert config.text_mode == text_mode


@pytest.mark.parametrize("text_mode", ["auto", "LIGHT", "dark;", None])
def test_invalid_text_modes_use_default(text_mode):
    config = parse_render_background_config(
        {"render_background": {"text_mode": text_mode}}
    )

    assert config.text_mode == "light"


def test_boolean_switches_are_parsed_independently():
    config = parse_render_background_config(
        {
            "render_background": {
                "enabled": True,
                "overlay_enabled": False,
                "glass_enabled": False,
            }
        }
    )

    assert config.enabled is True
    assert config.overlay_enabled is False
    assert config.glass_enabled is False


def test_invalid_boolean_switches_use_defaults():
    config = parse_render_background_config(
        {
            "render_background": {
                "enabled": "true",
                "overlay_enabled": 0,
                "glass_enabled": None,
            }
        }
    )

    assert config.enabled is False
    assert config.overlay_enabled is True
    assert config.glass_enabled is True


@pytest.mark.parametrize("config", [None, {"render_background": None}, {"render_background": []}])
def test_missing_or_invalid_background_section_uses_defaults(config):
    assert parse_render_background_config(config) == RenderBackgroundConfig()
