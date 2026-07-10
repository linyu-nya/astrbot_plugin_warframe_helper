from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "astrbot_plugin_warframe_helper.clients.worldstate_client"


class _Logger:
    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None


class _HanziConv:
    @staticmethod
    def toSimplified(value: str) -> str:
        return value


class _PublicExportClient:
    def __init__(self, **_kwargs) -> None:
        pass


@pytest.fixture
def worldstate_module(monkeypatch: pytest.MonkeyPatch):
    package = types.ModuleType("astrbot_plugin_warframe_helper")
    package.__path__ = [str(ROOT)]
    clients_package = types.ModuleType("astrbot_plugin_warframe_helper.clients")
    clients_package.__path__ = [str(ROOT / "clients")]
    utils_package = types.ModuleType("astrbot_plugin_warframe_helper.utils")
    utils_package.__path__ = [str(ROOT / "utils")]

    astrbot = types.ModuleType("astrbot")
    astrbot_api = types.ModuleType("astrbot.api")
    astrbot_api.logger = _Logger()
    astrbot.api = astrbot_api

    hanziconv = types.ModuleType("hanziconv")
    hanziconv.HanziConv = _HanziConv

    async def fetch_bytes(*_args, **_kwargs):
        return None

    http_utils = types.ModuleType("astrbot_plugin_warframe_helper.http_utils")
    http_utils.fetch_bytes = fetch_bytes

    public_export = types.ModuleType(
        "astrbot_plugin_warframe_helper.clients.public_export_client"
    )
    public_export.PublicExportClient = _PublicExportClient

    wegame_sign = types.ModuleType(
        "astrbot_plugin_warframe_helper.utils.wegame_sign"
    )
    wegame_sign.build_signed_wegame_url = lambda url, **_kwargs: url

    stubs = {
        "aiohttp": types.ModuleType("aiohttp"),
        "astrbot": astrbot,
        "astrbot.api": astrbot_api,
        "hanziconv": hanziconv,
        "astrbot_plugin_warframe_helper": package,
        "astrbot_plugin_warframe_helper.clients": clients_package,
        "astrbot_plugin_warframe_helper.utils": utils_package,
        "astrbot_plugin_warframe_helper.http_utils": http_utils,
        "astrbot_plugin_warframe_helper.clients.public_export_client": public_export,
        "astrbot_plugin_warframe_helper.utils.wegame_sign": wegame_sign,
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(MODULE_NAME, None)
    spec = importlib.util.spec_from_file_location(
        MODULE_NAME,
        ROOT / "clients" / "worldstate_client.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, MODULE_NAME, module)
    spec.loader.exec_module(module)
    return module
