from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from astrbot_plugin_warframe_helper.renderers.background_runtime import (
    BackgroundThemeRuntime,
)
from astrbot_plugin_warframe_helper.renderers.render_theme import RenderTheme


def _write_png(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (2, 2), color)
    output = BytesIO()
    image.save(output, format="PNG")
    path.write_bytes(output.getvalue())


async def test_runtime_resolves_category_override_and_global_default(tmp_path: Path):
    _write_png(tmp_path / "global.png", (20, 40, 60))
    _write_png(tmp_path / "fissure.png", (180, 40, 60))
    runtime = BackgroundThemeRuntime.from_config(
        {
            "render_background": {
                "enabled": True,
                "default_source": "global.png",
                "fissure_source": "fissure.png",
            }
        },
        plugin_root=tmp_path,
    )

    await runtime.initialize()
    fissure = runtime.resolve("crack.html", "裂缝")
    default = runtime.resolve("guide.html", "wf")

    assert isinstance(fissure, RenderTheme)
    assert fissure.enabled is True
    assert fissure.scope == "fissure"
    assert default.enabled is True
    assert default.scope == "default"
    assert fissure.css != default.css


async def test_runtime_failed_category_uses_global_resource(tmp_path: Path):
    _write_png(tmp_path / "global.png", (20, 40, 60))
    warnings: list[str] = []
    runtime = BackgroundThemeRuntime.from_config(
        {
            "render_background": {
                "enabled": True,
                "default_source": "global.png",
                "market_source": "missing.png",
            }
        },
        plugin_root=tmp_path,
        warning=warnings.append,
    )

    await runtime.initialize()
    market = runtime.resolve("wm.html", "wm")
    default = runtime.resolve("guide.html", "wf")

    assert market.enabled is True
    assert market.scope == "market"
    assert default.enabled is True
    assert "background-image" in market.css
    assert market.css == default.css
    assert len(warnings) == 1


async def test_disabled_runtime_performs_zero_network_io(tmp_path: Path):
    calls: list[str] = []

    async def fetcher(url: str, **_kwargs: object) -> bytes:
        calls.append(url)
        return b"unused"

    runtime = BackgroundThemeRuntime.from_config(
        {
            "render_background": {
                "enabled": False,
                "default_source": "missing.png",
                "fissure_source": "https://example.test/fissure.png",
            }
        },
        plugin_root=tmp_path,
        fetcher=fetcher,
    )

    await runtime.initialize()
    theme = runtime.resolve("crack.html", "裂缝")

    assert theme == RenderTheme(enabled=False, css="", scope="fissure")
    assert calls == []
