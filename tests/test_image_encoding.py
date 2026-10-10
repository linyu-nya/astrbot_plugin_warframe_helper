from pathlib import Path
import sys
import types

from PIL import Image

core = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
utils = sys.modules.setdefault("astrbot.core.utils", types.ModuleType("astrbot.core.utils"))
path_module = sys.modules.setdefault("astrbot.core.utils.astrbot_path", types.ModuleType("astrbot.core.utils.astrbot_path"))
path_module.get_astrbot_temp_path = lambda: ""
core.utils = utils
utils.astrbot_path = path_module

from astrbot_plugin_warframe_helper.renderers import html_snapshot  # noqa: E402


def test_lossless_webp_preserves_pixels_and_shrinks_image(tmp_path: Path):
    path = tmp_path / "wm_card.png"
    image = Image.new("RGB", (480, 320))
    image.putdata([((x * 3 + y) % 256, (y * 2) % 256, (x + y * 7) % 256)
                   for y in range(320) for x in range(480)])
    image.save(path, "PNG")
    original = path.stat().st_size
    html_snapshot.configure_image_format("webp")
    converted = html_snapshot._prefer_lossless_webp(path)
    assert converted.suffix == ".webp"
    assert converted.stat().st_size < original
    with Image.open(converted) as actual:
        assert actual.convert("RGB").tobytes() == image.tobytes()
    assert not path.exists()


def test_png_option_keeps_original(tmp_path: Path):
    path = tmp_path / "wm_card.png"
    path.write_bytes(b"not an image")
    html_snapshot.configure_image_format("png")
    assert html_snapshot._prefer_lossless_webp(path) == path
    assert path.read_bytes() == b"not an image"
    html_snapshot.configure_image_format("webp")
