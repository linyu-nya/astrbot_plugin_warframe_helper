from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"
WORLDSTATE_MODULE = f"{PACKAGE}.clients.worldstate_client"


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


package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules.setdefault(PACKAGE, package)

astrbot = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
astrbot_api.logger = _Logger()
astrbot.api = astrbot_api
sys.modules.setdefault("astrbot", astrbot)
sys.modules.setdefault("astrbot.api", astrbot_api)


@pytest.fixture
def worldstate_module(monkeypatch: pytest.MonkeyPatch):
    isolated_package = types.ModuleType(PACKAGE)
    isolated_package.__path__ = [str(ROOT)]
    clients_package = types.ModuleType(f"{PACKAGE}.clients")
    clients_package.__path__ = [str(ROOT / "clients")]
    utils_package = types.ModuleType(f"{PACKAGE}.utils")
    utils_package.__path__ = [str(ROOT / "utils")]

    isolated_astrbot = types.ModuleType("astrbot")
    isolated_astrbot_api = types.ModuleType("astrbot.api")
    isolated_astrbot_api.logger = _Logger()
    isolated_astrbot.api = isolated_astrbot_api

    hanziconv = types.ModuleType("hanziconv")
    hanziconv.HanziConv = _HanziConv

    async def fetch_bytes(*_args, **_kwargs):
        return None

    http_utils = types.ModuleType(f"{PACKAGE}.http_utils")
    http_utils.fetch_bytes = fetch_bytes

    public_export = types.ModuleType(f"{PACKAGE}.clients.public_export_client")
    public_export.PublicExportClient = _PublicExportClient

    wegame_sign = types.ModuleType(f"{PACKAGE}.utils.wegame_sign")
    wegame_sign.build_signed_wegame_url = lambda url, **_kwargs: url

    stubs = {
        "aiohttp": types.ModuleType("aiohttp"),
        "astrbot": isolated_astrbot,
        "astrbot.api": isolated_astrbot_api,
        "hanziconv": hanziconv,
        PACKAGE: isolated_package,
        f"{PACKAGE}.clients": clients_package,
        f"{PACKAGE}.utils": utils_package,
        f"{PACKAGE}.http_utils": http_utils,
        f"{PACKAGE}.clients.public_export_client": public_export,
        f"{PACKAGE}.utils.wegame_sign": wegame_sign,
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)

    sys.modules.pop(WORLDSTATE_MODULE, None)
    spec = importlib.util.spec_from_file_location(
        WORLDSTATE_MODULE,
        ROOT / "clients" / "worldstate_client.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, WORLDSTATE_MODULE, module)
    spec.loader.exec_module(module)
    return module
