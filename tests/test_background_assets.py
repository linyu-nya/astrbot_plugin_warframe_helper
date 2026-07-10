from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from astrbot_plugin_warframe_helper.renderers import background_assets
from astrbot_plugin_warframe_helper.renderers.background_assets import (
    BackgroundAssetLoader,
)
from astrbot_plugin_warframe_helper.renderers.background_config import (
    RenderBackgroundConfig,
)


def _image_bytes(format_name: str = "PNG", *, size: tuple[int, int] = (2, 2)) -> bytes:
    mode = "RGB" if format_name == "JPEG" else "RGBA"
    image = Image.new(mode, size, (20, 80, 140, 255) if mode == "RGBA" else (20, 80, 140))
    output = BytesIO()
    image.save(output, format=format_name)
    return output.getvalue()


def _write_image(path: Path, format_name: str = "PNG") -> bytes:
    data = _image_bytes(format_name)
    path.write_bytes(data)
    return data


def _settings(**changes: object) -> RenderBackgroundConfig:
    return replace(RenderBackgroundConfig(enabled=True), **changes)


async def test_loads_relative_local_image_from_plugin_root(tmp_path: Path):
    _write_image(tmp_path / "background.png")
    loader = BackgroundAssetLoader(
        _settings(default_source="background.png"),
        plugin_root=tmp_path,
    )

    await loader.initialize()

    assert loader.uri_for("default").startswith("data:image/png;base64,")


async def test_loads_absolute_local_image(tmp_path: Path):
    image_path = tmp_path / "absolute.jpg"
    _write_image(image_path, "JPEG")
    loader = BackgroundAssetLoader(
        _settings(default_source=str(image_path)),
        plugin_root=tmp_path / "unused",
    )

    await loader.initialize()

    assert loader.uri_for("default").startswith("data:image/jpeg;base64,")


@pytest.mark.parametrize(
    ("format_name", "expected_mime"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
async def test_accepts_supported_formats_by_content(
    tmp_path: Path,
    format_name: str,
    expected_mime: str,
):
    path = tmp_path / f"image-{format_name.lower()}.bin"
    _write_image(path, format_name)
    loader = BackgroundAssetLoader(
        _settings(default_source=path.name),
        plugin_root=tmp_path,
    )

    await loader.initialize()

    assert loader.uri_for("default").startswith(f"data:{expected_mime};base64,")


@pytest.mark.parametrize(
    "filename,data",
    [
        ("broken.png", b"not-an-image"),
        ("vector.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"),
        ("animated.gif", _image_bytes("GIF")),
    ],
)
async def test_rejects_invalid_or_unsupported_local_content(
    tmp_path: Path,
    filename: str,
    data: bytes,
):
    (tmp_path / filename).write_bytes(data)
    warnings: list[str] = []
    loader = BackgroundAssetLoader(
        _settings(default_source=filename),
        plugin_root=tmp_path,
        warning=warnings.append,
    )

    await loader.initialize()

    assert loader.uri_for("default") == ""
    assert len(warnings) == 1


async def test_rejects_missing_local_file_once(tmp_path: Path):
    warnings: list[str] = []
    loader = BackgroundAssetLoader(
        _settings(default_source="missing.png"),
        plugin_root=tmp_path,
        warning=warnings.append,
    )

    await loader.initialize()
    await loader.initialize()

    assert loader.uri_for("default") == ""
    assert len(warnings) == 1


async def test_rejects_local_file_above_byte_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(background_assets, "MAX_IMAGE_BYTES", 8)
    (tmp_path / "large.png").write_bytes(_image_bytes("PNG"))
    loader = BackgroundAssetLoader(
        _settings(default_source="large.png"),
        plugin_root=tmp_path,
    )

    await loader.initialize()

    assert loader.uri_for("default") == ""


async def test_rejects_decoded_image_above_pixel_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(background_assets, "MAX_IMAGE_PIXELS", 3)
    _write_image(tmp_path / "too-many-pixels.png")
    loader = BackgroundAssetLoader(
        _settings(default_source="too-many-pixels.png"),
        plugin_root=tmp_path,
    )

    await loader.initialize()

    assert loader.uri_for("default") == ""


async def test_rejects_pillow_decompression_bomb_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _write_image(tmp_path / "bomb.png")
    warnings: list[str] = []

    def raise_bomb(_stream: object):
        raise Image.DecompressionBombError("too many pixels")

    monkeypatch.setattr(background_assets.Image, "open", raise_bomb)
    loader = BackgroundAssetLoader(
        _settings(default_source="bomb.png"),
        plugin_root=tmp_path,
        warning=warnings.append,
    )

    await loader.initialize()

    assert loader.uri_for("default") == ""
    assert len(warnings) == 1


async def test_category_failure_falls_back_to_global_once(tmp_path: Path):
    _write_image(tmp_path / "global.png")
    warnings: list[str] = []
    loader = BackgroundAssetLoader(
        _settings(
            default_source="global.png",
            fissure_source="missing.png",
        ),
        plugin_root=tmp_path,
        warning=warnings.append,
    )

    await loader.initialize()
    await loader.initialize()

    assert loader.uri_for("fissure") == loader.uri_for("default")
    assert loader.uri_for("fissure").startswith("data:image/png;base64,")
    assert len(warnings) == 1


async def test_remote_source_is_downloaded_once_with_limits(tmp_path: Path):
    calls: list[tuple[str, dict[str, object]]] = []

    async def fetcher(url: str, **kwargs: object) -> bytes:
        calls.append((url, kwargs))
        return _image_bytes("WEBP")

    loader = BackgroundAssetLoader(
        _settings(default_source="https://example.test/background.webp"),
        plugin_root=tmp_path,
        fetcher=fetcher,
    )

    await loader.initialize()
    first = loader.uri_for("default")
    second = loader.uri_for("default")

    assert first == second
    assert first.startswith("data:image/webp;base64,")
    assert len(calls) == 1
    assert calls[0][0] == "https://example.test/background.webp"
    assert calls[0][1]["timeout_sec"] == 10.0
    assert calls[0][1]["max_bytes"] == background_assets.MAX_IMAGE_BYTES
    assert calls[0][1]["headers"] == {"Accept": "image/png,image/jpeg,image/webp"}


@pytest.mark.parametrize("payload", [None, b"broken", b"x" * 256])
async def test_remote_failure_uses_global_fallback_and_warns_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes | None,
):
    monkeypatch.setattr(background_assets, "MAX_IMAGE_BYTES", 128)
    _write_image(tmp_path / "global.png")
    calls: list[str] = []
    warnings: list[str] = []

    async def fetcher(url: str, **_kwargs: object) -> bytes | None:
        calls.append(url)
        return payload

    loader = BackgroundAssetLoader(
        _settings(
            default_source="global.png",
            market_source="https://example.test/market.png",
        ),
        plugin_root=tmp_path,
        fetcher=fetcher,
        warning=warnings.append,
    )

    await loader.initialize()
    await loader.initialize()

    assert loader.uri_for("market") == loader.uri_for("default")
    assert len(calls) == 1
    assert len(warnings) == 1


async def test_failed_global_resource_falls_back_to_original_template(tmp_path: Path):
    loader = BackgroundAssetLoader(
        _settings(default_source="missing.png"),
        plugin_root=tmp_path,
    )

    await loader.initialize()

    assert loader.uri_for("default") == ""
    assert loader.uri_for("worldstate") == ""


async def test_disabled_switch_performs_zero_io(tmp_path: Path):
    calls: list[str] = []
    warnings: list[str] = []

    async def fetcher(url: str, **_kwargs: object) -> bytes:
        calls.append(url)
        return _image_bytes("PNG")

    settings = RenderBackgroundConfig(
        enabled=False,
        default_source="missing.png",
        fissure_source="https://example.test/fissure.png",
    )
    loader = BackgroundAssetLoader(
        settings,
        plugin_root=tmp_path,
        fetcher=fetcher,
        warning=warnings.append,
    )

    await loader.initialize()

    assert loader.uri_for("default") == ""
    assert calls == []
    assert warnings == []
