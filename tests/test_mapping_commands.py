import sys
import json
from pathlib import Path
from types import ModuleType

import pytest

# Keep this focused test independent of optional AstrBot imports performed by
# the package initializer while still importing the target module normally.
services_package = ModuleType("services")
services_package.__path__ = [str(Path(__file__).parents[1] / "services")]
sys.modules.setdefault("services", services_package)

from services.mapping_commands import (
    compatible_alias_add,
    wfmap,
    wfmapdel,
    wfmapq,
)

import types

astrbot_core = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
astrbot_core_utils = sys.modules.setdefault(
    "astrbot.core.utils", types.ModuleType("astrbot.core.utils")
)
astrbot_path = types.ModuleType("astrbot.core.utils.astrbot_path")
astrbot_path.get_astrbot_plugin_data_path = lambda: "unused"
astrbot_core.utils = astrbot_core_utils
astrbot_core_utils.astrbot_path = astrbot_path
sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path

from astrbot_plugin_warframe_helper.mappers.nickname_registry import (  # noqa: E402
    NICKNAME_SCHEMA_VERSION,
    NicknameRegistry,
    SYM_BASE_NICKNAMES,
    SYM_RIVEN_STAT_NICKNAMES,
    SYM_RIVEN_WEAPON_NICKNAMES,
    USER_ALIASES,
)
from astrbot_plugin_warframe_helper.mappers.term_mapping import (  # noqa: E402
    WarframeTermMapper,
)


class FakeEvent:
    def __init__(self, admin=True):
        self.admin = admin
        self.results = []

    def is_admin(self):
        return self.admin

    async def plain_result(self, text):
        self.results.append(text)


class FakeMapper:
    def __init__(self):
        self.calls = []
        self.initialize_called = False
        self.market_called = False
        self.aliases = {}
        self.deleted_result = "deleted"
        self.reverse_result = []

    async def upsert_user_alias(self, alias, full_name):
        self.calls.append(("upsert", alias, full_name))
        self.aliases[alias] = full_name
        return alias, full_name

    async def delete_user_alias(self, alias):
        self.calls.append(("delete", alias))
        return self.deleted_result

    async def resolve_alias_only(self, alias):
        self.calls.append(("resolve", alias))
        return self.aliases.get(alias)

    async def find_effective_aliases(self, full_name):
        self.calls.append(("find", full_name))
        return self.reverse_result

    async def initialize(self):
        self.initialize_called = True

    async def market(self):
        self.market_called = True


class SyncFakeEvent:
    def __init__(self, admin=True):
        self.admin = admin
        self.sent = []

    def is_admin(self):
        return self.admin

    def plain_result(self, text):
        result = ("plain_result", text)
        self.sent.append(result)
        return result


class SyncFakeMapper:
    def __init__(self):
        self.calls = []

    def upsert_user_alias(self, *, alias, full_name):
        self.calls.append(("upsert", alias, full_name))
        return "normalized", "Normalized Full Name"

    def find_effective_aliases(self, full_name):
        self.calls.append(("find", full_name))
        return [{"alias": "简称", "source": "base"}]


@pytest.mark.asyncio
async def test_wfmap_requires_admin_and_maps_first_token_to_multiword_name():
    event = FakeEvent(admin=True)
    mapper = FakeMapper()

    await wfmap(event, ["月", "夜", "之", "刃"], mapper)

    assert mapper.calls == [("upsert", "月", "夜 之 刃")]
    assert event.results == ["已添加映射：月 -> 夜 之 刃"]

    denied = FakeEvent(admin=False)
    await wfmap(denied, ["月", "夜"], mapper)
    assert denied.results == ["无权限：仅管理员可执行此操作"]
    assert mapper.calls == [("upsert", "月", "夜 之 刃")]


@pytest.mark.asyncio
async def test_wfmap_returns_sync_plain_result_from_sync_mapper():
    event = SyncFakeEvent()
    mapper = SyncFakeMapper()

    result = await wfmap(event, ["输入别名", "输入", "全称"], mapper)

    expected = ("plain_result", "已添加映射：normalized -> Normalized Full Name")
    assert result == expected
    assert event.sent == [expected]
    assert mapper.calls == [("upsert", "输入别名", "输入 全称")]


@pytest.mark.asyncio
async def test_wfmap_echoes_mapper_normalized_return_value():
    class NormalizingMapper(FakeMapper):
        async def upsert_user_alias(self, alias, full_name):
            self.calls.append(("upsert", alias, full_name))
            return ("wolf", "Voruna Prime")

    event = FakeEvent()
    await wfmap(event, [" WOLF ", " voruna ", " PRIME "], NormalizingMapper())

    assert event.results == ["已添加映射：wolf -> Voruna Prime"]


@pytest.mark.asyncio
async def test_mapping_commands_report_usage_for_missing_arguments():
    mapper = FakeMapper()
    for command, expected in (
        (wfmap, "用法：/wfmap 别名 全称"),
        (wfmapdel, "用法：/wfmapdel 别名"),
        (wfmapq, "用法：/wfmapq 全称"),
    ):
        event = FakeEvent()
        await command(event, [], mapper)
        assert event.results == [expected]


@pytest.mark.asyncio
async def test_wfmapdel_reports_status_and_checks_builtin_recovery_after_delete():
    mapper = FakeMapper()
    mapper.deleted_result = "deleted"
    mapper.aliases["月"] = "内置全称"
    event = FakeEvent()

    await wfmapdel(event, ["月"], mapper)

    assert mapper.calls == [("delete", "月"), ("resolve", "月")]
    assert event.results == ["已删除映射：月 -> 内置全称（已恢复内置映射）"]

    for status, expected in (
        ("builtin_only", "该别名仅有内置映射，未删除用户映射：月"),
        ("not_found", "未找到用户映射：月"),
    ):
        mapper.calls.clear()
        mapper.deleted_result = status
        event = FakeEvent()
        await wfmapdel(event, ["月"], mapper)
        assert mapper.calls == [("delete", "月")]
        assert event.results == [expected]


@pytest.mark.asyncio
async def test_wfmapdel_rejects_multiple_args_and_non_admin_without_mapper_call():
    mapper = FakeMapper()
    event = FakeEvent()
    await wfmapdel(event, ["月", "夜"], mapper)
    assert event.results == ["用法：/wfmapdel 别名"]
    assert mapper.calls == []

    denied = FakeEvent(admin=False)
    await wfmapdel(denied, ["月"], mapper)
    assert denied.results == ["无权限：仅管理员可执行此操作"]
    assert mapper.calls == []


@pytest.mark.asyncio
async def test_wfmapq_is_public_and_lists_sources_in_chinese():
    event = FakeEvent(admin=False)
    mapper = FakeMapper()
    mapper.reverse_result = [
        {"alias": "夜刃", "source": "builtin"},
        {"alias": "小夜刃", "source": "riven_weapon"},
        {"alias": "我的夜刃", "source": "user"},
    ]

    await wfmapq(event, ["夜", "之", "刃"], mapper)

    assert mapper.calls == [("find", "夜 之 刃")]
    assert event.results == ["夜 之 刃 的别名：\n- 夜刃（内置）\n- 小夜刃（紫卡武器）\n- 我的夜刃（用户自定义）"]

    mapper.reverse_result = []
    event = FakeEvent()
    await wfmapq(event, ["不存在"], mapper)
    assert event.results == ["未找到全称‘不存在’的有效别名"]


@pytest.mark.asyncio
async def test_wfmapq_returns_sync_plain_result_from_sync_mapper():
    event = SyncFakeEvent(admin=False)
    mapper = SyncFakeMapper()

    result = await wfmapq(event, ["Full", "Name"], mapper)

    expected = ("plain_result", "Full Name 的别名：\n- 简称（内置）")
    assert result == expected
    assert event.sent == [expected]
    assert mapper.calls == [("find", "Full Name")]


@pytest.mark.asyncio
async def test_wfmapq_maps_base_source_to_builtin_label():
    event = FakeEvent(admin=False)
    mapper = FakeMapper()
    mapper.reverse_result = [{"alias": "基础", "source": "base"}]

    await wfmapq(event, ["全称"], mapper)

    assert event.results == ["全称 的别名：\n- 基础（内置）"]


@pytest.mark.asyncio
async def test_compatible_alias_add_delegates_to_wfmap():
    event = FakeEvent()
    mapper = FakeMapper()

    await compatible_alias_add(event, ["月", "夜", "之", "刃"], mapper)

    assert mapper.calls == [("upsert", "月", "夜 之 刃")]
    assert event.results == ["已添加映射：月 -> 夜 之 刃"]


@pytest.mark.asyncio
async def test_compatible_alias_add_rejects_non_admin_without_writing():
    event = FakeEvent(admin=False)
    mapper = FakeMapper()

    await compatible_alias_add(event, ["月", "夜"], mapper)

    assert event.results == ["无权限：仅管理员可执行此操作"]
    assert mapper.calls == []


@pytest.mark.asyncio
async def test_commands_turn_mapper_errors_into_user_failure_text_without_initializing_or_market():
    class BrokenMapper(FakeMapper):
        async def upsert_user_alias(self, alias, full_name):
            raise RuntimeError("db down")

    event = FakeEvent()
    mapper = BrokenMapper()

    await wfmap(event, ["月", "夜"], mapper)

    assert event.results == ["操作失败：db down"]
    assert not mapper.initialize_called
    assert not mapper.market_called


@pytest.mark.asyncio
async def test_base_exception_is_not_converted_to_failure_text():
    class InterruptedMapper(FakeMapper):
        async def upsert_user_alias(self, alias, full_name):
            raise KeyboardInterrupt()

    event = FakeEvent()
    with pytest.raises(KeyboardInterrupt):
        await wfmap(event, ["月", "夜"], InterruptedMapper())
    assert event.results == []


def _integration_mapper(tmp_path: Path):
    payload = {
        "version": NICKNAME_SCHEMA_VERSION,
        SYM_BASE_NICKNAMES: {"wolf": "Voruna Prime"},
        SYM_RIVEN_WEAPON_NICKNAMES: {},
        SYM_RIVEN_STAT_NICKNAMES: {},
        USER_ALIASES: {},
    }
    default_path = tmp_path / "warframe_nicknames.default.json"
    data_path = tmp_path / "warframe_nicknames.json"
    for path in (default_path, data_path):
        path.write_text(json.dumps(payload), encoding="utf-8")
    registry = NicknameRegistry(data_path=data_path, default_path=default_path)
    return WarframeTermMapper(
        nickname_registry=registry,
        plugin_data_dir=tmp_path / "plugin-data",
        items_cache_path=tmp_path / "items-cache.json",
    )


@pytest.mark.asyncio
async def test_wfmapq_integrates_with_real_mapper_without_initialize_or_market(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    mapper = _integration_mapper(tmp_path)
    for name in ("initialize", "_load_items_cache", "refresh_items_cache"):
        monkeypatch.setattr(
            mapper, name, lambda: (_ for _ in ()).throw(AssertionError(name))
        )

    event = FakeEvent(admin=False)
    await wfmapq(event, ["  VORUNA  ", "  prime  "], mapper)
    assert "wolf（内置）" in event.results[0]

    event = FakeEvent(admin=False)
    await wfmapq(event, ["wolf"], mapper)
    assert event.results == ["未找到全称‘wolf’的有效别名"]
