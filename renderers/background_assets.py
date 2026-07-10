from __future__ import annotations

import asyncio
import base64
import logging
import warnings
from collections.abc import Awaitable, Callable
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .background_config import RenderBackgroundConfig

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000

_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
_IMAGE_HEADERS = {"Accept": "image/png,image/jpeg,image/webp"}

Fetcher = Callable[..., Awaitable[bytes | None]]
WarningHandler = Callable[[str], None]


class BackgroundAssetLoader:
    def __init__(
        self,
        settings: RenderBackgroundConfig,
        *,
        plugin_root: Path,
        fetcher: Fetcher | None = None,
        warning: WarningHandler | None = None,
    ) -> None:
        self._settings = settings
        self._plugin_root = Path(plugin_root)
        self._fetcher = fetcher
        self._warning = warning or logging.getLogger(__name__).warning
        self._uris: dict[str, str] = {}
        self._warned_sources: set[str] = set()
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        if not self._settings.enabled:
            return

        sources = {
            "default": self._settings.default_source,
            "fissure": self._settings.fissure_source,
            "market": self._settings.market_source,
            "worldstate": self._settings.worldstate_source,
        }
        for scope, source in sources.items():
            if not source:
                continue
            uri = await self._load_source(scope, source)
            if uri:
                self._uris[scope] = uri

    def uri_for(self, scope: str) -> str:
        return self._uris.get(scope) or self._uris.get("default", "")

    async def _load_source(self, scope: str, source: str) -> str:
        try:
            if source.lower().startswith(("http://", "https://")):
                data = await self._fetch_remote(source)
            else:
                data = await asyncio.to_thread(self._read_local, source)
        except Exception as exc:
            self._warn_once(source, f"{scope} background load failed: {exc!s}")
            return ""

        if not data:
            self._warn_once(source, f"{scope} background returned no data")
            return ""
        if len(data) > MAX_IMAGE_BYTES:
            self._warn_once(source, f"{scope} background exceeds 15 MiB")
            return ""

        uri = _validated_data_uri(data)
        if not uri:
            self._warn_once(source, f"{scope} background format or dimensions invalid")
        return uri

    def _read_local(self, source: str) -> bytes:
        path = Path(source).expanduser()
        if not path.is_absolute():
            path = self._plugin_root / path
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise ValueError("file exceeds 15 MiB")
        return path.read_bytes()

    async def _fetch_remote(self, source: str) -> bytes | None:
        fetcher = self._fetcher
        if fetcher is None:
            from ..http_utils import fetch_bytes

            fetcher = fetch_bytes
        return await fetcher(
            source,
            timeout_sec=10.0,
            headers=_IMAGE_HEADERS,
            max_bytes=MAX_IMAGE_BYTES,
        )

    def _warn_once(self, source: str, message: str) -> None:
        if source in self._warned_sources:
            return
        self._warned_sources.add(source)
        self._warning(message)


def _validated_data_uri(data: bytes) -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_format = str(image.format or "").upper()
                mime = _MIME_BY_FORMAT.get(image_format)
                if not mime:
                    return ""
                width, height = image.size
                if width * height > MAX_IMAGE_PIXELS:
                    return ""
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        return ""

    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"
