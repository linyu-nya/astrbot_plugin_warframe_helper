from __future__ import annotations

import re
from dataclasses import dataclass


_COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\Z")
_PERCENTAGE_PATTERN = re.compile(r"\d+(?:\.\d+)?%\Z")
_POSITION_KEYWORDS = frozenset({"left", "center", "right", "top", "bottom"})
_BACKGROUND_FITS = frozenset({"cover", "contain", "width", "repeat-y"})
_TEXT_MODES = frozenset({"light", "dark"})


@dataclass(frozen=True, slots=True)
class RenderBackgroundConfig:
    enabled: bool = False
    default_source: str = ""
    fissure_source: str = ""
    market_source: str = ""
    worldstate_source: str = ""
    background_fit: str = "cover"
    background_position: str = "center center"
    overlay_enabled: bool = True
    overlay_color: str = "#0f172a"
    overlay_opacity: int = 42
    panel_color: str = "#0f172a"
    panel_opacity: int = 58
    glass_enabled: bool = True
    blur_px: int = 6
    text_mode: str = "light"


def _parse_bool(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _parse_source(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_bounded_int(value: object, default: int, maximum: int) -> int:
    if type(value) is not int:
        return default
    return max(0, min(value, maximum))


def _parse_color(value: object, default: str) -> str:
    if isinstance(value, str) and _COLOR_PATTERN.fullmatch(value):
        return value
    return default


def _is_position_token(token: str) -> bool:
    if token in _POSITION_KEYWORDS:
        return True
    if not _PERCENTAGE_PATTERN.fullmatch(token):
        return False
    return 0 <= float(token[:-1]) <= 100


def _parse_position(value: object, default: str) -> str:
    if not isinstance(value, str):
        return default
    tokens = value.split()
    if len(tokens) not in (1, 2) or not all(map(_is_position_token, tokens)):
        return default
    return " ".join(tokens)


def _parse_choice(value: object, allowed: frozenset[str], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def parse_render_background_config(
    config: dict | None,
) -> RenderBackgroundConfig:
    raw: object = config.get("render_background") if isinstance(config, dict) else {}
    if not isinstance(raw, dict):
        raw = {}

    defaults = RenderBackgroundConfig()
    return RenderBackgroundConfig(
        enabled=_parse_bool(raw.get("enabled"), defaults.enabled),
        default_source=_parse_source(raw.get("default_source")),
        fissure_source=_parse_source(raw.get("fissure_source")),
        market_source=_parse_source(raw.get("market_source")),
        worldstate_source=_parse_source(raw.get("worldstate_source")),
        background_fit=_parse_choice(
            raw.get("background_fit"), _BACKGROUND_FITS, defaults.background_fit
        ),
        background_position=_parse_position(
            raw.get("background_position"), defaults.background_position
        ),
        overlay_enabled=_parse_bool(
            raw.get("overlay_enabled"), defaults.overlay_enabled
        ),
        overlay_color=_parse_color(
            raw.get("overlay_color"), defaults.overlay_color
        ),
        overlay_opacity=_parse_bounded_int(
            raw.get("overlay_opacity"), defaults.overlay_opacity, 100
        ),
        panel_color=_parse_color(raw.get("panel_color"), defaults.panel_color),
        panel_opacity=_parse_bounded_int(
            raw.get("panel_opacity"), defaults.panel_opacity, 100
        ),
        glass_enabled=_parse_bool(raw.get("glass_enabled"), defaults.glass_enabled),
        blur_px=_parse_bounded_int(raw.get("blur_px"), defaults.blur_px, 30),
        text_mode=_parse_choice(
            raw.get("text_mode"), _TEXT_MODES, defaults.text_mode
        ),
    )
