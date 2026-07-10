from __future__ import annotations

import argparse
import asyncio
import base64
import shutil
import sys
import tempfile
import types
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"

package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules.setdefault(PACKAGE, package)

from astrbot_plugin_warframe_helper.renderers.background_runtime import (  # noqa: E402
    BackgroundThemeRuntime,
)
from astrbot_plugin_warframe_helper.renderers.template_loader import (  # noqa: E402
    load_html_template,
    set_current_render_command,
    set_render_theme_resolver,
)


def _gradient_background(
    path: Path,
    *,
    start: str,
    end: str,
    accent: str,
) -> None:
    gradient = Image.linear_gradient("L").resize((980, 720))
    image = ImageOps.colorize(gradient, black=start, white=end).convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((560, -180, 1120, 380), fill=f"{accent}70")
    draw.polygon(
        [(0, 510), (320, 310), (650, 720), (0, 720)],
        fill=f"{accent}45",
    )
    image.save(path, format="PNG")


def _image_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _worldstate_context(title: str, count: int) -> dict[str, object]:
    rows = []
    missions = ["捕获", "生存", "歼灭", "间谍", "移动防御", "炼金"]
    planets = ["地球", "金星", "火星", "木星", "月球", "虚空"]
    for index in range(count):
        rows.append(
            {
                "title": f"节点 {index + 1:02d}（{planets[index % len(planets)]}）",
                "subtitle": missions[index % len(missions)],
                "right": f"剩余 {8 + index * 3} 分钟",
                "tag": ["古纪", "前纪", "中纪", "后纪"][index % 4],
                "accent_css": "rgba(103, 232, 249, 0.95)",
            }
        )
    return {
        "page": {
            "title": title,
            "header_lines": ["平台：PC", f"共 {count} 条"],
            "rows": rows,
            "reward_rows": [],
        }
    }


def _market_context(avatar_uri: str) -> dict[str, object]:
    rows = []
    for index, price in enumerate([58, 60, 60, 61, 62], start=1):
        rows.append(
            {
                "avatar": avatar_uri,
                "name": f"TennoSeller{index}",
                "status_text": "游戏中" if index < 4 else "在线",
                "status_class": "ingame" if index < 4 else "online",
                "price_text": f"{price}p",
                "qty_text": f"x{index}" if index > 1 else "",
            }
        )
    return {
        "page": {
            "title": "Volt Prime 一套（PC）出售",
            "item_img_uri": "",
            "item_background_style": "",
            "rows": rows,
        }
    }


def _browser_candidates() -> list[str]:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    found = [str(path) for path in candidates if path.exists()]
    for command in ("msedge", "google-chrome", "chromium", "chromium-browser"):
        executable = shutil.which(command)
        if executable and executable not in found:
            found.append(executable)
    return found


async def _render_html(
    browser,
    *,
    html: str,
    width: int,
    output: Path,
) -> None:
    page = await browser.new_page(viewport={"width": width, "height": 720})
    try:
        await page.set_content(html, wait_until="load")
        await page.screenshot(path=str(output), full_page=True, type="png")
    finally:
        await page.close()

    with Image.open(output) as rendered:
        if rendered.width <= 0 or rendered.height <= 0:
            raise RuntimeError(f"invalid preview dimensions: {output}")


async def _run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wf-background-preview-") as temp:
        assets = Path(temp)
        _gradient_background(
            assets / "global.png",
            start="#0f172a",
            end="#155e75",
            accent="#67e8f9",
        )
        _gradient_background(
            assets / "fissure.png",
            start="#111827",
            end="#7c2d12",
            accent="#fb923c",
        )
        _gradient_background(
            assets / "market.png",
            start="#172554",
            end="#164e63",
            accent="#38bdf8",
        )
        _gradient_background(
            assets / "worldstate.png",
            start="#052e16",
            end="#3f6212",
            accent="#bef264",
        )

        runtime = BackgroundThemeRuntime.from_config(
            {
                "render_background": {
                    "enabled": True,
                    "default_source": "global.png",
                    "fissure_source": "fissure.png",
                    "market_source": "market.png",
                    "worldstate_source": "worldstate.png",
                    "background_fit": "cover",
                    "background_position": "center center",
                    "overlay_enabled": True,
                    "overlay_color": "#020617",
                    "overlay_opacity": 30,
                    "panel_color": "#0f172a",
                    "panel_opacity": 52,
                    "glass_enabled": True,
                    "blur_px": 8,
                    "text_mode": "light",
                }
            },
            plugin_root=assets,
        )
        await runtime.initialize()
        set_render_theme_resolver(runtime.resolve)

        set_current_render_command("裂缝")
        fissure_html = load_html_template(
            filename="crack.html",
            context=_worldstate_context("裂缝", 18),
        )
        set_current_render_command("wm")
        market_html = load_html_template(
            filename="wm.html",
            context=_market_context(_image_data_uri(assets / "market.png")),
        )
        set_current_render_command("仲裁")
        worldstate_html = load_html_template(
            filename="status_list.html",
            context=_worldstate_context("世界状态", 8),
        )

        if "blur(8px)" not in fissure_html:
            raise RuntimeError("custom blur was not emitted")

        no_glass = BackgroundThemeRuntime.from_config(
            {
                "render_background": {
                    "enabled": True,
                    "default_source": "global.png",
                    "glass_enabled": False,
                }
            },
            plugin_root=assets,
        )
        await no_glass.initialize()
        if "backdrop-filter" in no_glass.resolve("guide.html", "wf").css:
            raise RuntimeError("glass-off theme still contains blur declarations")

        executable = next(iter(_browser_candidates()), None)
        async with async_playwright() as playwright:
            launch_kwargs = {"headless": True}
            if executable:
                launch_kwargs["executable_path"] = executable
            browser = await playwright.chromium.launch(**launch_kwargs)
            try:
                await _render_html(
                    browser,
                    html=fissure_html,
                    width=980,
                    output=output_dir / "fissure-background.png",
                )
                await _render_html(
                    browser,
                    html=market_html,
                    width=920,
                    output=output_dir / "market-background.png",
                )
                await _render_html(
                    browser,
                    html=worldstate_html,
                    width=980,
                    output=output_dir / "worldstate-background.png",
                )
            finally:
                await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render custom background previews")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.output_dir.resolve()))


if __name__ == "__main__":
    main()
