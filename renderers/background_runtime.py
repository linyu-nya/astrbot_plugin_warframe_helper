from __future__ import annotations

from pathlib import Path

from .background_assets import BackgroundAssetLoader, Fetcher, WarningHandler
from .background_config import RenderBackgroundConfig, parse_render_background_config
from .render_theme import RenderTheme, build_render_theme_context


class BackgroundThemeRuntime:
    def __init__(
        self,
        settings: RenderBackgroundConfig,
        assets: BackgroundAssetLoader,
    ) -> None:
        self._settings = settings
        self._assets = assets

    @classmethod
    def from_config(
        cls,
        config: dict | None,
        *,
        plugin_root: Path,
        fetcher: Fetcher | None = None,
        warning: WarningHandler | None = None,
    ) -> BackgroundThemeRuntime:
        settings = parse_render_background_config(config)
        assets = BackgroundAssetLoader(
            settings,
            plugin_root=plugin_root,
            fetcher=fetcher,
            warning=warning,
        )
        return cls(settings, assets)

    async def initialize(self) -> None:
        await self._assets.initialize()

    def resolve(self, filename: str, command_key: str) -> RenderTheme:
        return build_render_theme_context(
            self._settings,
            self._assets,
            filename=filename,
            command_key=command_key,
        )
