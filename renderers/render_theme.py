from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .background_config import RenderBackgroundConfig

_FISSURE_COMMANDS = frozenset({"裂缝", "普通裂缝", "钢铁裂缝", "九重天裂缝"})
_MARKET_COMMANDS = frozenset({"wm", "wmr", "wfp"})
_WORLDSTATE_COMMANDS = frozenset(
    {
        "平原",
        "夜灵平原",
        "地球昼夜",
        "奥布山谷",
        "魔胎之境",
        "双衍王境",
        "轮回奖励",
        "突击",
        "执行官猎杀",
        "警报",
        "入侵",
        "奸商",
        "仲裁",
        "电波",
        "钢铁奖励",
        "集团",
        "赏金",
    }
)
_MARKET_TEMPLATES = frozenset({"wm.html", "wmr.html", "wfp.html"})
_WORLDSTATE_TEMPLATES = frozenset(
    {"status_list.html", "cycle_status.html", "event.html", "赏金.html"}
)


class BackgroundAssets(Protocol):
    def uri_for(self, scope: str) -> str: ...


@dataclass(frozen=True, slots=True)
class RenderTheme:
    enabled: bool
    css: str
    scope: str


def classify_render_scope(filename: str, command_key: str) -> str:
    name = str(filename or "").strip().lower()
    command = str(command_key or "").strip().removeprefix("/").strip().lower()
    if name == "crack.html" or command in _FISSURE_COMMANDS:
        return "fissure"
    if name in _MARKET_TEMPLATES or command in _MARKET_COMMANDS:
        return "market"
    if name in _WORLDSTATE_TEMPLATES or command in _WORLDSTATE_COMMANDS:
        return "worldstate"
    return "default"


def build_render_theme_context(
    settings: RenderBackgroundConfig,
    assets: BackgroundAssets,
    *,
    filename: str,
    command_key: str,
) -> RenderTheme:
    scope = classify_render_scope(filename, command_key)
    if not settings.enabled:
        return RenderTheme(enabled=False, css="", scope=scope)

    image_uri = assets.uri_for(scope)
    if not image_uri:
        return RenderTheme(enabled=False, css="", scope=scope)

    size, repeat = _background_fit_css(settings.background_fit)
    panel = _rgba_css(settings.panel_color, settings.panel_opacity)
    text, muted, border, tag = _text_palette(settings.text_mode)
    glass = ""
    if settings.glass_enabled:
        glass = (
            f"  -webkit-backdrop-filter: blur({settings.blur_px}px);\n"
            f"  backdrop-filter: blur({settings.blur_px}px);\n"
        )

    overlay = ""
    if settings.overlay_enabled:
        overlay_color = _rgba_css(settings.overlay_color, settings.overlay_opacity)
        overlay = f"""
.wf-custom-background::before {{
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: {overlay_color};
}}
.wf-custom-background > * {{
  position: relative;
  z-index: 1;
}}
"""

    css = f"""
.wf-custom-background {{
  --wf-theme-text: {text};
  --wf-theme-muted: {muted};
  --wf-theme-border: {border};
  --wf-theme-tag: {tag};
  min-height: 100vh;
  position: relative;
  isolation: isolate;
  background-image: url("{image_uri}") !important;
  background-size: {size};
  background-position: {settings.background_position};
  background-repeat: {repeat};
  color: var(--wf-theme-text) !important;
}}
{overlay}
.wf-custom-background .row-card,
.wf-custom-background .row,
.wf-custom-background .header,
.wf-custom-background .head {{
  background: {panel} !important;
  border-color: var(--wf-theme-border) !important;
{glass}}}
.wf-custom-background .title,
.wf-custom-background .row-title,
.wf-custom-background .name,
.wf-custom-background .price,
.wf-custom-background .row-right {{
  color: var(--wf-theme-text) !important;
}}
.wf-custom-background .header-line,
.wf-custom-background .row-subtitle,
.wf-custom-background .sub,
.wf-custom-background .qty,
.wf-custom-background .mini {{
  color: var(--wf-theme-muted) !important;
}}
.wf-custom-background .row-tag,
.wf-custom-background .status-pill {{
  color: var(--wf-theme-text) !important;
  background: var(--wf-theme-tag) !important;
  border-color: var(--wf-theme-border) !important;
}}
""".strip()
    return RenderTheme(enabled=True, css=css, scope=scope)


def _background_fit_css(fit: str) -> tuple[str, str]:
    if fit == "contain":
        return "contain", "no-repeat"
    if fit == "width":
        return "100% auto", "no-repeat"
    if fit == "repeat-y":
        return "100% auto", "repeat-y"
    return "cover", "no-repeat"


def _rgba_css(color: str, opacity: int) -> str:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    red = int(value[0:2], 16)
    green = int(value[2:4], 16)
    blue = int(value[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity / 100:.2f})"


def _text_palette(mode: str) -> tuple[str, str, str, str]:
    if mode == "dark":
        return "#0f172a", "#475569", "rgba(15, 23, 42, 0.20)", "rgba(255, 255, 255, 0.42)"
    return "#f8fafc", "#cbd5e1", "rgba(255, 255, 255, 0.24)", "rgba(15, 23, 42, 0.42)"
