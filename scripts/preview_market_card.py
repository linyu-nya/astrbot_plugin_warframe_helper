"""Render representative market cards offline for visual review."""
from __future__ import annotations

import argparse
import asyncio
import base64
from pathlib import Path

from render_background_preview import (
    ROOT, BackgroundThemeRuntime, _browser_candidates, async_playwright,
    load_html_template, set_current_render_command, set_render_theme_resolver,
)


async def run(background: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    runtime = BackgroundThemeRuntime.from_config(
        {"render_background": {
            "enabled": True, "default_source": str(background.resolve()),
            "overlay_opacity": 28, "panel_color": "#101d24", "panel_opacity": 82,
            "glass_enabled": True, "blur_px": 6, "text_mode": "light",
        }}, plugin_root=ROOT,
    )
    await runtime.initialize()
    set_current_render_command("wm")
    names = ["AdeptoPrime", "Brother-Yu", "CYJC0813", "Ezmoe", "InEuropeTheEmperor",
             "LUANDONGMING", "LeFail", "LoneVR", "Minatouran", "Round.Three"]
    avatar = 'data:image/svg+xml;base64,' + base64.b64encode(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><circle cx="16" cy="16" r="16" fill="#344c50"/><path d="M16 6L24 16L16 26L8 16Z" fill="none" stroke="#96b7aa"/></svg>'
    ).decode()
    rows = [{"avatar": avatar, "name": n, "qty_text": f"x{[1,1,1,2,5,2,1,1,1,1][i]}",
             "price_text": "60p", "status_class": "ingame", "status_text": "游戏中"}
            for i, n in enumerate(names)]
    async with async_playwright() as pw:
        candidates = _browser_candidates()
        browser = await pw.chromium.launch(headless=True, **({"executable_path": candidates[0]} if candidates else {}))
        try:
            for name, count, custom in [("market-dark", 10, True), ("market-default", 10, False), ("market-short", 1, True), ("market-long", 20, True)]:
                set_render_theme_resolver(runtime.resolve if custom else None)
                context = {"page": {"title": "Gauss Prime 一套（pc）出售", "item_name": "Gauss Prime 一套",
                           "platform": "pc", "action_cn": "出售", "item_img_uri": "", "rows": (rows * 2)[:count]}}
                html = load_html_template(filename="wm.html", context=context)
                font = base64.b64encode((ROOT / "fonts/NotoSansHans-Regular.otf").read_bytes()).decode()
                html = html.replace('</head>', '<style>@font-face{font-family:PreviewHan;src:url(data:font/otf;base64,' + font + ')}body{font-family:PreviewHan,sans-serif}</style></head>')
                page = await browser.new_page(viewport={"width": 920, "height": 360}, device_scale_factor=1)
                try:
                    await page.set_content(html, wait_until="load")
                    await page.evaluate("document.fonts.ready")
                    dims = await page.evaluate("({width:document.body.scrollWidth,height:document.body.scrollHeight})")
                    if dims['width'] != 920:
                        raise RuntimeError(f"Horizontal overflow: {dims}")
                    await page.screenshot(path=str(output / f"{name}.png"), full_page=True)
                    print(f"{name}: {dims}")
                finally:
                    await page.close()
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.background, args.output))
