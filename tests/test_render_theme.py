from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from astrbot_plugin_warframe_helper.renderers.background_config import (
    RenderBackgroundConfig,
)
from astrbot_plugin_warframe_helper.renderers.render_theme import (
    RenderTheme,
    build_render_theme_context,
    classify_render_scope,
)


class _FakeAssets:
    def __init__(self, uris: dict[str, str] | None = None) -> None:
        self.uris = uris or {}
        self.requested: list[str] = []

    def uri_for(self, scope: str) -> str:
        self.requested.append(scope)
        return self.uris.get(scope, self.uris.get("default", ""))


@pytest.mark.parametrize(
    ("filename", "command", "expected"),
    [
        ("crack.html", "裂缝", "fissure"),
        ("status_list.html", "钢铁裂缝", "fissure"),
        ("status_list.html", "/九重天裂缝", "fissure"),
        ("wm.html", "wm", "market"),
        ("wmr.html", "/wmr", "market"),
        ("wfp.html", "wfp", "market"),
        ("cycle_status.html", "平原", "worldstate"),
        ("event.html", "奸商", "worldstate"),
        ("赏金.html", "赏金", "worldstate"),
        ("status_list.html", "仲裁", "worldstate"),
        ("仲裁.html", "仲裁", "worldstate"),
        ("平原.html", "/平原", "worldstate"),
        ("guide.html", "wf", "default"),
        ("lookup.html", "武器", "default"),
    ],
)
def test_classifies_render_scope(filename: str, command: str, expected: str):
    assert classify_render_scope(filename, command) == expected


def test_render_theme_is_frozen_and_slotted():
    theme = RenderTheme(enabled=False, css="", scope="default")

    assert not hasattr(theme, "__dict__")
    with pytest.raises(FrozenInstanceError):
        theme.enabled = True


def test_disabled_settings_return_empty_theme_without_asset_lookup():
    assets = _FakeAssets({"default": "data:image/png;base64,abc"})

    theme = build_render_theme_context(
        RenderBackgroundConfig(enabled=False),
        assets,
        filename="crack.html",
        command_key="裂缝",
    )

    assert theme == RenderTheme(enabled=False, css="", scope="fissure")
    assert assets.requested == []


def test_missing_loaded_uri_returns_empty_theme():
    assets = _FakeAssets()

    theme = build_render_theme_context(
        RenderBackgroundConfig(enabled=True, default_source="missing.png"),
        assets,
        filename="guide.html",
        command_key="wf",
    )

    assert theme == RenderTheme(enabled=False, css="", scope="default")
    assert assets.requested == ["default"]


def test_theme_uses_classified_asset_and_not_configured_source():
    data_uri = "data:image/png;base64,c2FmZQ=="
    assets = _FakeAssets({"market": data_uri})
    settings = RenderBackgroundConfig(
        enabled=True,
        default_source="https://unsafe.example/default.png",
        market_source="C:/unsafe/market.png",
    )

    theme = build_render_theme_context(
        settings,
        assets,
        filename="wm.html",
        command_key="wm",
    )

    assert theme.enabled is True
    assert theme.scope == "market"
    assert assets.requested == ["market"]
    assert data_uri in theme.css
    assert "unsafe.example" not in theme.css
    assert "C:/unsafe" not in theme.css


@pytest.mark.parametrize(
    ("fit", "size", "repeat"),
    [
        ("cover", "cover", "no-repeat"),
        ("contain", "contain", "no-repeat"),
        ("width", "100% auto", "no-repeat"),
        ("repeat-y", "100% auto", "repeat-y"),
    ],
)
def test_background_fit_modes_map_to_safe_css(fit: str, size: str, repeat: str):
    settings = replace(
        RenderBackgroundConfig(enabled=True),
        background_fit=fit,
        background_position="center top",
    )

    theme = build_render_theme_context(
        settings,
        _FakeAssets({"default": "data:image/png;base64,abc"}),
        filename="guide.html",
        command_key="wf",
    )

    assert f"background-size: {size};" in theme.css
    assert f"background-repeat: {repeat};" in theme.css
    assert "background-position: center top;" in theme.css


def test_overlay_and_panel_use_configured_colors_and_opacity():
    settings = replace(
        RenderBackgroundConfig(enabled=True),
        overlay_color="#abc",
        overlay_opacity=25,
        panel_color="#123456",
        panel_opacity=70,
    )

    theme = build_render_theme_context(
        settings,
        _FakeAssets({"default": "data:image/png;base64,abc"}),
        filename="guide.html",
        command_key="wf",
    )

    assert "rgba(170, 187, 204, 0.25)" in theme.css
    assert "rgba(18, 52, 86, 0.70)" in theme.css
    assert ".wf-custom-background::before" in theme.css


def test_disabled_overlay_omits_overlay_but_keeps_background():
    settings = replace(
        RenderBackgroundConfig(enabled=True),
        overlay_enabled=False,
    )

    theme = build_render_theme_context(
        settings,
        _FakeAssets({"default": "data:image/png;base64,abc"}),
        filename="guide.html",
        command_key="wf",
    )

    assert theme.enabled is True
    assert ".wf-custom-background::before" not in theme.css
    assert "background-image: url(" in theme.css


def test_custom_background_covers_minimum_snapshot_height():
    settings = replace(RenderBackgroundConfig(enabled=True))

    theme = build_render_theme_context(
        settings,
        _FakeAssets({"default": "data:image/png;base64,abc"}),
        filename="status_list.html",
        command_key="钢铁奖励",
    )

    assert "min-height: 100vh;" in theme.css


def test_glass_uses_custom_blur_value():
    settings = replace(
        RenderBackgroundConfig(enabled=True),
        glass_enabled=True,
        blur_px=13,
    )

    theme = build_render_theme_context(
        settings,
        _FakeAssets({"default": "data:image/png;base64,abc"}),
        filename="guide.html",
        command_key="wf",
    )

    assert "backdrop-filter: blur(13px);" in theme.css
    assert "-webkit-backdrop-filter: blur(13px);" in theme.css


def test_disabled_glass_omits_both_blur_declarations():
    settings = replace(
        RenderBackgroundConfig(enabled=True),
        glass_enabled=False,
        blur_px=18,
    )

    theme = build_render_theme_context(
        settings,
        _FakeAssets({"default": "data:image/png;base64,abc"}),
        filename="guide.html",
        command_key="wf",
    )

    assert "backdrop-filter" not in theme.css
    assert "blur(18px)" not in theme.css


@pytest.mark.parametrize(
    ("text_mode", "expected_text", "expected_muted"),
    [
        ("light", "#f8fafc", "#cbd5e1"),
        ("dark", "#0f172a", "#475569"),
    ],
)
def test_text_modes_emit_controlled_color_variables(
    text_mode: str,
    expected_text: str,
    expected_muted: str,
):
    settings = replace(
        RenderBackgroundConfig(enabled=True),
        text_mode=text_mode,
    )

    theme = build_render_theme_context(
        settings,
        _FakeAssets({"default": "data:image/png;base64,abc"}),
        filename="guide.html",
        command_key="wf",
    )

    assert f"--wf-theme-text: {expected_text};" in theme.css
    assert f"--wf-theme-muted: {expected_muted};" in theme.css
