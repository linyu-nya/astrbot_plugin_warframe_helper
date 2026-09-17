from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path

import pytest

from astrbot_plugin_warframe_helper.clients.huiji_wiki_client import (
    HuijiWikiResult,
    HuijiWikiStatus,
)

services_package = ModuleType("services")
services_package.__path__ = [str(Path(__file__).parents[1] / "services")]
sys.modules.setdefault("services", services_package)

from services import mapping_commands, no_prefix_routing, wiki_commands  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class Event:
    def __init__(self, admin: bool):
        self.admin = admin
        self.messages: list[str] = []

    def is_admin(self) -> bool:
        return self.admin

    async def plain_result(self, text: str):
        self.messages.append(text)


class Mapper:
    def __init__(self):
        self.upserts: list[tuple[str, str]] = []
        self.lookups: list[str] = []

    async def upsert_user_alias(self, *, alias: str, full_name: str):
        self.upserts.append((alias, full_name))
        return alias, full_name

    async def find_effective_aliases(self, full_name: str):
        self.lookups.append(full_name)
        return [{"alias": "猴p", "source": "user"}]


class WikiClient:
    def __init__(self):
        self.lookups: list[str] = []

    async def lookup(self, keyword: str):
        self.lookups.append(keyword)
        return HuijiWikiResult(HuijiWikiStatus.FOUND, url="https://wiki.test/page")

    def build_search_url(self, keyword: str) -> str:
        return "https://wiki.test/search?q=" + keyword


def _method_source(name: str) -> str:
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))
    plugin = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "WarframeHelperPlugin")
    method = next(
        (
            node
            for node in plugin.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ),
        None,
    )
    if method is None:
        return ""
    return ast.unparse(method)


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_wfmap_route_preserves_admin_gate_and_calls_mapper_only_for_admin(admin: bool):
    event = Event(admin)
    mapper = Mapper()

    await mapping_commands.wfmap(event, ["猴p", "Wukong", "Prime"], mapper)

    if admin:
        assert mapper.upserts == [("猴p", "Wukong Prime")]
    else:
        assert mapper.upserts == []
        assert event.messages == ["无权限：仅管理员可执行此操作"]
    assert "mapping_commands.wfmap" in _method_source("wfmap")


@pytest.mark.asyncio
async def test_no_prefix_wfmap_route_has_the_same_admin_gate():
    event = Event(False)
    mapper = Mapper()
    await mapping_commands.wfmap(event, ["猴p", "Wukong"], mapper)
    assert mapper.upserts == []

    event = Event(True)
    await mapping_commands.wfmap(event, ["猴p", "Wukong"], mapper)
    assert mapper.upserts == [("猴p", "Wukong")]
    router_source = _method_source("_no_prefix_handler_map")
    assert '"wfmap": self.wfmap' in router_source


@pytest.mark.asyncio
async def test_wk_slash_and_no_prefix_routes_call_wiki_service():
    mapper = Mapper()
    client = WikiClient()
    for route_args in (("/wk", ["Volt"]), ("wk", ["Volt"])):
        event = Event(False)
        await wiki_commands.wk(event, route_args[1], mapper, client)
        assert client.lookups[-1] == "Volt"
    assert "wiki_commands.wk" in _method_source("wk")
    assert '"wk": self.wk' in _method_source("_no_prefix_handler_map")


@pytest.mark.asyncio
async def test_wfmapq_is_public_and_reaches_mapper_for_non_admin():
    event = Event(False)
    mapper = Mapper()
    await mapping_commands.wfmapq(event, ["Wukong", "Prime"], mapper)
    assert mapper.lookups == ["Wukong Prime"]
    assert event.messages
    assert "mapping_commands.wfmapq" in _method_source("wfmapq")


def test_route_wrappers_are_async_generators_or_async_functions():
    for name in ("wfmap", "wfmapdel", "wfmapq", "wk"):
        source = _method_source(name)
        assert "async" in source


def _load_main_handlers(monkeypatch: pytest.MonkeyPatch):
    """Load main.py with decorators that preserve the original handler bodies."""

    package = "astrbot_plugin_warframe_helper"

    def module(name: str, **attrs):
        value = ModuleType(name)
        for key, item in attrs.items():
            setattr(value, key, item)
        monkeypatch.setitem(sys.modules, name, value)
        return value

    def decorator(*_args, **_kwargs):
        return lambda func: func

    class Filter:
        command = staticmethod(decorator)
        regex = staticmethod(decorator)

        @staticmethod
        def command_group(*_args, **_kwargs):
            def decorate(func):
                func.command = decorator
                return func

            return decorate

    class Star:
        pass

    astrbot = module("astrbot")
    api = module("astrbot.api", logger=SimpleNamespace(debug=lambda *_args, **_kwargs: None))
    astrbot.api = api
    module("astrbot.api.event", AstrMessageEvent=object, filter=Filter())
    module("astrbot.api.message_components", Image=object, Plain=object)
    module("astrbot.api.star", Context=object, Star=Star)
    module("astrbot.core")
    module("astrbot.core.star")
    module("astrbot.core.star.filter")
    class GreedyStr(str):
        pass

    module("astrbot.core.star.filter.command", GreedyStr=GreedyStr)
    module("astrbot.core.utils")
    module("astrbot.core.utils.astrbot_path", get_astrbot_temp_path=lambda: "")

    def empty_module(name: str, **attrs):
        return module(f"{package}.{name}", **attrs)

    empty_module("clients", __path__=[])
    empty_module("clients.huiji_wiki_client", HuijiWikiClient=object)
    empty_module("clients.market_client", WarframeMarketClient=object)
    empty_module("clients.public_export_client", PublicExportClient=object)
    empty_module("clients.worldstate_client", WarframeWorldstateClient=object)
    empty_module("components", __path__=[])
    empty_module("components.event_ttl_cache", EventScopedTTLCache=object)
    empty_module("components.qq_official_webhook", QQOfficialWebhookPager=object)
    empty_module("handlers", __path__=[])
    empty_module("handlers.qq_interaction", handle_qq_interaction_create=lambda *_args, **_kwargs: None)
    empty_module("handlers.wm_pick", handle_wm_pick_number=lambda *_args, **_kwargs: None)
    empty_module("helpers", split_tokens=lambda value: str(value).split())
    empty_module("http_utils", set_direct_domains=lambda *_args, **_kwargs: None, set_proxy_url=lambda *_args, **_kwargs: None)
    empty_module("mappers", __path__=[])
    empty_module("mappers.riven_mapping", WarframeRivenWeaponMapper=object)
    empty_module("mappers.riven_stats_mapping", WarframeRivenStatMapper=object)
    empty_module("mappers.term_mapping", WarframeTermMapper=object)
    empty_module("renderers", __path__=[])
    empty_module("renderers.html_snapshot", configure_image_cache=lambda **_kwargs: None, start_playwright_runtime_prepare=lambda: None)
    empty_module("renderers.background_runtime", BackgroundThemeRuntime=object)
    empty_module("renderers.template_loader", has_render_template_name=lambda *_args: False, list_available_render_template_names=lambda: [], set_current_render_command=lambda *_args: None, set_current_render_template_name=lambda *_args: None, set_render_template_name=lambda *_args: None, set_render_theme_resolver=lambda *_args: None)
    empty_module("renderers.worldstate_render", WorldstateRow=object, render_worldstate_rows_image_to_file=lambda **_kwargs: None)
    services = empty_module("services", __path__=[])
    services.mapping_commands = mapping_commands
    services.wiki_commands = wiki_commands
    services.worldstate_commands = SimpleNamespace()
    empty_module("services.auto_push", AutoPushService=object)
    empty_module("services.fissure_sorting", fissure_tier_sort_enabled=lambda *_args: False)
    empty_module(
        "services.no_prefix_routing",
        has_explicit_at_component=no_prefix_routing.has_explicit_at_component,
        no_prefix_skip_reason=no_prefix_routing.no_prefix_skip_reason,
    )
    empty_module("services.subscriptions", SubscriptionService=object)
    empty_module("services.market", __path__=[])
    empty_module("services.market.pager", cmd_wfp=lambda **_kwargs: None)
    empty_module("services.market.wm", cmd_wm=lambda **_kwargs: None)
    empty_module("services.market.wmr", cmd_wmr=lambda **_kwargs: None)
    empty_module("utils", __path__=[])
    empty_module("utils.platforms", worldstate_platform_from_tokens=lambda _tokens: "pc")

    module_name = f"{package}.main_handler_test"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "main.py")
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, loaded)
    spec.loader.exec_module(loaded)
    return loaded


class HandlerEvent(Event):
    def __init__(self, admin: bool, text: str = "", *, private: bool = False):
        super().__init__(admin)
        self.text = text
        self.is_at_or_wake_command = False
        self.private = private

    def get_message_str(self) -> str:
        return self.text

    def get_messages(self):
        return []

    def is_private_chat(self) -> bool:
        return self.private

    def should_call_llm(self, _disabled: bool) -> None:
        pass

    async def plain_result(self, text: str):
        self.messages.append(text)
        return ("plain", text)


def _handler_plugin(module, mapper: Mapper, client: WikiClient):
    plugin = module.WarframeHelperPlugin.__new__(module.WarframeHelperPlugin)
    plugin.term_mapper = mapper
    plugin.huiji_wiki_client = client
    plugin._enable_no_prefix_commands = True
    plugin._no_prefix_head_regex = None
    plugin._debug_log = lambda *_args, **_kwargs: None
    return plugin


async def _collect(generator):
    return [result async for result in generator]


@pytest.mark.asyncio
async def test_main_wfmap_handlers_execute_admin_gate_for_slash_and_no_prefix(monkeypatch):
    module = _load_main_handlers(monkeypatch)
    mapper = Mapper()
    plugin = _handler_plugin(module, mapper, WikiClient())

    denied = HandlerEvent(False)
    assert await _collect(plugin.wfmap(denied, "猴p Wukong Prime")) == [
        ("plain", "无权限：仅管理员可执行此操作")
    ]
    assert mapper.upserts == []

    allowed = HandlerEvent(True, "wfmap 猴p Wukong Prime")
    assert await _collect(plugin.no_prefix_command_router(allowed)) == [
        ("plain", "已添加映射：猴p -> Wukong Prime")
    ]
    assert mapper.upserts == [("猴p", "Wukong Prime")]


@pytest.mark.asyncio
async def test_main_wfmap_handler_keeps_the_complete_greedy_command_text(monkeypatch):
    module = _load_main_handlers(monkeypatch)
    mapper = Mapper()
    plugin = _handler_plugin(module, mapper, WikiClient())

    parameter = inspect.signature(module.WarframeHelperPlugin.wfmap).parameters["args"]
    assert parameter.annotation is module.GreedyStr
    assert parameter.default is inspect.Parameter.empty

    event = HandlerEvent(True)
    assert await _collect(
        plugin.wfmap(event, "圣英p总图 圣英 PRIME 蓝图")
    ) == [("plain", "已添加映射：圣英p总图 -> 圣英 PRIME 蓝图")]
    assert mapper.upserts == [("圣英p总图", "圣英 PRIME 蓝图")]


def test_main_wiki_mapping_command_family_uses_real_greedy_parameters(monkeypatch):
    module = _load_main_handlers(monkeypatch)

    for handler_name in ("wk", "wfmap", "wfmapdel", "wfmapq", "wf_add_alias"):
        parameter = inspect.signature(
            getattr(module.WarframeHelperPlugin, handler_name)
        ).parameters["args"]
        assert parameter.annotation is module.GreedyStr
        assert parameter.default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_main_wk_handlers_execute_slash_and_no_prefix_and_yield_reply(monkeypatch):
    module = _load_main_handlers(monkeypatch)
    client = WikiClient()
    plugin = _handler_plugin(module, Mapper(), client)

    slash = HandlerEvent(False)
    assert await _collect(plugin.wk(slash, "Volt Prime")) == [
        ("plain", "以下是“Volt Prime”的 Wiki 页面：\nhttps://wiki.test/page")
    ]

    no_prefix = HandlerEvent(False, "wk Volt")
    assert await _collect(plugin.no_prefix_command_router(no_prefix)) == [
        ("plain", "以下是“Volt”的 Wiki 页面：\nhttps://wiki.test/page")
    ]
    assert client.lookups == ["Volt Prime", "Volt"]


@pytest.mark.asyncio
async def test_private_wk_wake_command_is_not_replied_by_no_prefix_router(monkeypatch):
    module = _load_main_handlers(monkeypatch)
    client = WikiClient()
    plugin = _handler_plugin(module, Mapper(), client)
    event = HandlerEvent(False, "wk 圣英 prime", private=True)
    event.is_at_or_wake_command = True

    assert await _collect(plugin.no_prefix_command_router(event)) == []
    assert client.lookups == []


@pytest.mark.asyncio
async def test_main_wfmapq_handler_is_public_and_yields_reply(monkeypatch):
    module = _load_main_handlers(monkeypatch)
    mapper = Mapper()
    plugin = _handler_plugin(module, mapper, WikiClient())

    event = HandlerEvent(False)
    assert await _collect(plugin.wfmapq(event, "Wukong Prime")) == [
        ("plain", "Wukong Prime 的别名：\n- 猴p（用户自定义）")
    ]
    assert mapper.lookups == ["Wukong Prime"]
