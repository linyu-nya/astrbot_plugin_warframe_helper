from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest


astrbot = sys.modules["astrbot"]
astrbot_core = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
astrbot_core_utils = sys.modules.setdefault(
    "astrbot.core.utils", types.ModuleType("astrbot.core.utils")
)
astrbot_path = types.ModuleType("astrbot.core.utils.astrbot_path")
astrbot_path.get_astrbot_plugin_data_path = lambda: (_ for _ in ()).throw(
    AssertionError("tests must inject all plugin data paths")
)
astrbot.core = astrbot_core
astrbot_core.utils = astrbot_core_utils
astrbot_core_utils.astrbot_path = astrbot_path
sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path


from astrbot_plugin_warframe_helper.mappers.nickname_registry import (
    NICKNAME_SCHEMA_VERSION,
    SOURCE_BASE,
    SOURCE_RIVEN_WEAPON,
    SOURCE_USER,
    SYM_BASE_NICKNAMES,
    SYM_RIVEN_STAT_NICKNAMES,
    SYM_RIVEN_WEAPON_NICKNAMES,
    USER_ALIASES,
    NicknameRegistry,
)
from astrbot_plugin_warframe_helper.mappers.term_mapping import (
    AliasResolution,
    EffectiveAliasEntry,
    WarframeTermMapper,
)


def _payload(
    *,
    base: dict[str, str] | None = None,
    riven_weapon: dict[str, str] | None = None,
    riven_stat: dict[str, str] | None = None,
    user: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "version": NICKNAME_SCHEMA_VERSION,
        SYM_BASE_NICKNAMES: base or {},
        SYM_RIVEN_WEAPON_NICKNAMES: riven_weapon or {},
        SYM_RIVEN_STAT_NICKNAMES: riven_stat or {},
        USER_ALIASES: user or {},
    }


def _mapper(
    tmp_path: Path,
    *,
    base: dict[str, str] | None = None,
    riven_weapon: dict[str, str] | None = None,
    riven_stat: dict[str, str] | None = None,
    user: dict[str, str] | None = None,
) -> tuple[WarframeTermMapper, NicknameRegistry, Path, Path]:
    default_path = tmp_path / "warframe_nicknames.default.json"
    data_path = tmp_path / "warframe_nicknames.json"
    payload = _payload(
        base=base,
        riven_weapon=riven_weapon,
        riven_stat=riven_stat,
        user=user,
    )
    default_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    registry = NicknameRegistry(data_path=data_path, default_path=default_path)
    mapper = WarframeTermMapper(
        nickname_registry=registry,
        plugin_data_dir=tmp_path / "plugin-data",
        items_cache_path=tmp_path / "items-cache.json",
    )
    return mapper, registry, data_path, default_path


def _forbid_market_access(
    mapper: WarframeTermMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("pure alias API accessed market initialization/cache")

    monkeypatch.setattr(mapper, "initialize", fail)
    monkeypatch.setattr(mapper, "_load_items_cache", fail)
    monkeypatch.setattr(mapper, "refresh_items_cache", fail)


def test_alias_only_resolves_exact_longest_prefix_and_unknown_passthrough(
    tmp_path: Path,
) -> None:
    mapper, _, _, _ = _mapper(
        tmp_path,
        base={"咖喱": "Excalibur", "咖喱p": "Excalibur Prime"},
    )

    assert mapper.resolve_alias_only(" 咖 喱 ") == AliasResolution(
        original_query=" 咖 喱 ",
        matched=True,
        alias_key="咖喱",
        canonical_full_name="Excalibur",
    )
    assert mapper.resolve_alias_only("咖喱P蓝图") == AliasResolution(
        original_query="咖喱P蓝图",
        matched=True,
        alias_key="咖喱p",
        canonical_full_name="Excalibur Prime",
    )
    assert mapper.resolve_alias_only("未收录 词条") == AliasResolution(
        original_query="未收录 词条",
        matched=False,
        alias_key=None,
        canonical_full_name="未收录 词条",
    )


def test_first_alias_only_call_loads_only_registry_effective_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapper, registry, _, _ = _mapper(tmp_path, base={"照相机": "奥克绪罗斯"})
    calls = 0
    original = registry.get_effective_alias_entries

    def tracked_entries() -> list[dict[str, str]]:
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(registry, "get_effective_alias_entries", tracked_entries)
    _forbid_market_access(mapper, monkeypatch)

    assert calls == 0
    assert mapper.resolve_alias_only("照相机").canonical_full_name == "奥克绪罗斯"
    assert calls == 1
    assert mapper.resolve_alias_only("照相机").matched is True
    assert calls == 1
    assert mapper._loaded is False
    assert not mapper.items_cache_path.exists()


def test_user_alias_override_write_delete_and_builtin_fallback_are_immediate(
    tmp_path: Path,
) -> None:
    mapper, _, data_path, default_path = _mapper(
        tmp_path,
        base={"咖喱": "Excalibur"},
    )
    original_default = default_path.read_text(encoding="utf-8")

    assert mapper.upsert_user_alias(alias="咖喱", full_name="User Frame") == (
        "咖喱",
        "User Frame",
    )
    assert mapper.resolve_alias_only("咖喱").canonical_full_name == "User Frame"
    assert json.loads(data_path.read_text(encoding="utf-8"))[USER_ALIASES] == {
        "咖喱": "User Frame"
    }
    assert default_path.read_text(encoding="utf-8") == original_default

    assert mapper.delete_user_alias("咖喱") == "deleted"
    assert mapper.resolve_alias_only("咖喱").canonical_full_name == "Excalibur"
    assert mapper.delete_user_alias("咖喱") == "builtin_only"
    assert mapper.delete_user_alias("不存在") == "not_found"


def test_compatibility_upsert_alias_writes_user_partition(tmp_path: Path) -> None:
    mapper, _, data_path, default_path = _mapper(
        tmp_path,
        base={"内置": "Builtin Value"},
    )
    original_default = default_path.read_text(encoding="utf-8")

    assert mapper.upsert_alias(alias="内置", full_name="User Value") == (
        "内置",
        "User Value",
    )

    assert json.loads(data_path.read_text(encoding="utf-8"))[USER_ALIASES] == {
        "内置": "User Value"
    }
    assert default_path.read_text(encoding="utf-8") == original_default
    assert mapper.resolve_alias_only("内置").canonical_full_name == "User Value"


def test_effective_reverse_lookup_returns_only_winners_and_sources(
    tmp_path: Path,
) -> None:
    mapper, _, _, _ = _mapper(
        tmp_path,
        base={"基础": "Base Name", "覆盖": "Base Name", "照相机": "奥克绪罗斯"},
        riven_weapon={"武器": "Weapon Name", "覆盖": "Weapon Name"},
        riven_stat={"暴击": "Critical Chance"},
        user={"用户": "User Name", "覆盖": "User Name"},
    )

    assert mapper.find_effective_aliases("base name") == [
        EffectiveAliasEntry(alias="基础", full_name="Base Name", source=SOURCE_BASE)
    ]
    assert mapper.find_effective_aliases(" WEAPON   NAME ") == [
        EffectiveAliasEntry(
            alias="武器",
            full_name="Weapon Name",
            source=SOURCE_RIVEN_WEAPON,
        )
    ]
    assert mapper.find_effective_aliases(" user   NAME ") == [
        EffectiveAliasEntry(alias="用户", full_name="User Name", source=SOURCE_USER),
        EffectiveAliasEntry(alias="覆盖", full_name="User Name", source=SOURCE_USER),
    ]
    assert mapper.find_effective_aliases("奥克绪罗斯") == [
        EffectiveAliasEntry(alias="照相机", full_name="奥克绪罗斯", source=SOURCE_BASE)
    ]
    assert mapper.find_effective_aliases("Weapon Name") != [
        EffectiveAliasEntry(alias="覆盖", full_name="Weapon Name", source=SOURCE_RIVEN_WEAPON)
    ]
    assert mapper.find_effective_aliases("Critical Chance") == []


def test_reverse_lookup_rejects_alias_instead_of_full_name(tmp_path: Path) -> None:
    mapper, _, _, _ = _mapper(
        tmp_path,
        base={"camera": "Orokin Eye", "orokin eye": "Another Full Name"},
    )

    assert mapper.find_effective_aliases("camera") == []
    assert mapper.find_effective_aliases("  OROKIN   EYE ") == []


def test_all_pure_alias_operations_skip_market_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mapper, _, _, _ = _mapper(tmp_path, base={"内置": "Builtin"})
    _forbid_market_access(mapper, monkeypatch)

    assert mapper.resolve_alias_only("内置").matched is True
    assert mapper.upsert_user_alias(alias="用户", full_name="User Value") == (
        "用户",
        "User Value",
    )
    assert mapper.find_effective_aliases("User Value") == [
        EffectiveAliasEntry(alias="用户", full_name="User Value", source=SOURCE_USER)
    ]
    assert mapper.delete_user_alias("用户") == "deleted"
    assert mapper._loaded is False
    assert not mapper.items_cache_path.exists()
