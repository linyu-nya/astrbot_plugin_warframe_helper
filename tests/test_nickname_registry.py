from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"


class _Logger:
    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None


package = sys.modules.setdefault(PACKAGE, types.ModuleType(PACKAGE))
package.__path__ = [str(ROOT)]
astrbot = sys.modules.setdefault("astrbot", types.ModuleType("astrbot"))
astrbot_api = sys.modules.setdefault("astrbot.api", types.ModuleType("astrbot.api"))
astrbot_api.logger = _Logger()
astrbot.api = astrbot_api


async def _fetch_json(*_args, **_kwargs):
    return None


http_utils = sys.modules.setdefault(
    f"{PACKAGE}.http_utils", types.ModuleType(f"{PACKAGE}.http_utils")
)
http_utils.fetch_json = _fetch_json


def _unexpected_plugin_data_path() -> str:
    raise AssertionError("tests must not access the real AstrBot plugin data path")


astrbot_core = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
astrbot_core_utils = sys.modules.setdefault(
    "astrbot.core.utils", types.ModuleType("astrbot.core.utils")
)
astrbot_path = types.ModuleType("astrbot.core.utils.astrbot_path")
astrbot_path.get_astrbot_plugin_data_path = _unexpected_plugin_data_path
astrbot_core.utils = astrbot_core_utils
astrbot_core_utils.astrbot_path = astrbot_path
sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path

from astrbot_plugin_warframe_helper.mappers import (  # noqa: E402
    nickname_registry as nickname_registry_module,
)
from astrbot_plugin_warframe_helper.mappers.nickname_registry import (  # noqa: E402
    SOURCE_BASE,
    SOURCE_RIVEN_WEAPON,
    SOURCE_USER,
    SYM_BASE_NICKNAMES,
    SYM_RIVEN_STAT_NICKNAMES,
    SYM_RIVEN_WEAPON_NICKNAMES,
    USER_ALIASES,
    NicknameRegistry,
)


def _payload(
    *,
    version: int = 1,
    base: dict[str, str] | None = None,
    riven_weapon: dict[str, str] | None = None,
    riven_stat: dict[str, str] | None = None,
    user: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "version": version,
        SYM_BASE_NICKNAMES: base or {},
        SYM_RIVEN_WEAPON_NICKNAMES: riven_weapon or {},
        SYM_RIVEN_STAT_NICKNAMES: riven_stat or {},
        USER_ALIASES: user or {},
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _registry(
    tmp_path: Path,
    *,
    default: dict[str, Any] | None = None,
    runtime: dict[str, Any] | None = None,
) -> tuple[NicknameRegistry, Path, Path]:
    default_path = tmp_path / "warframe_nicknames.default.json"
    data_path = tmp_path / "warframe_nicknames.json"
    _write_json(default_path, default or _payload())
    if runtime is not None:
        _write_json(data_path, runtime)
    return (
        NicknameRegistry(data_path=data_path, default_path=default_path),
        data_path,
        default_path,
    )


def test_upsert_user_alias_uses_injected_data_path(tmp_path: Path) -> None:
    registry, data_path, default_path = _registry(tmp_path)
    original_default = default_path.read_text(encoding="utf-8")

    assert registry.upsert_alias(alias="  咖 喱  ", full_name="  Excalibur  ") == (
        "咖喱",
        "Excalibur",
    )

    saved = json.loads(data_path.read_text(encoding="utf-8"))
    assert saved[USER_ALIASES] == {"咖喱": "Excalibur"}
    assert default_path.read_text(encoding="utf-8") == original_default


def test_delete_user_alias_distinguishes_deleted_builtin_and_missing(
    tmp_path: Path,
) -> None:
    registry, _, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Builtin"}),
        runtime=_payload(
            version=2,
            base={"内置": "Builtin"},
            user={"用户": "Custom"},
        ),
    )
    original_default = default_path.read_text(encoding="utf-8")

    assert registry.delete_user_alias("用户") == "deleted"
    assert registry.delete_user_alias("内置") == "builtin_only"
    assert registry.delete_user_alias("不存在") == "not_found"
    assert registry.get_alias_map(SYM_BASE_NICKNAMES) == {"内置": "Builtin"}
    assert default_path.read_text(encoding="utf-8") == original_default


def test_schema_migration_moves_only_runtime_base_differences_and_restores_defaults(
    tmp_path: Path,
) -> None:
    default = _payload(
        base={"未修改": "Same", "被覆盖": "Default"},
        riven_weapon={"紫卡武器": "Default Weapon"},
        riven_stat={"紫卡词条": "Default Stat"},
    )
    runtime = _payload(
        base={
            "未修改": "Same",
            "被覆盖": "Legacy Override",
            "运行时新增": "Legacy Added",
        },
        riven_weapon={"旧武器": "Legacy Weapon"},
        riven_stat={"旧词条": "Legacy Stat"},
        user={"已有用户项": "Existing"},
    )
    registry, data_path, _ = _registry(tmp_path, default=default, runtime=runtime)

    loaded = registry.load()

    assert loaded["version"] == 2
    assert loaded[USER_ALIASES] == {
        "已有用户项": "Existing",
        "被覆盖": "Legacy Override",
        "运行时新增": "Legacy Added",
    }
    assert "未修改" not in loaded[USER_ALIASES]
    assert loaded[SYM_BASE_NICKNAMES] == default[SYM_BASE_NICKNAMES]
    assert loaded[SYM_RIVEN_WEAPON_NICKNAMES] == default[
        SYM_RIVEN_WEAPON_NICKNAMES
    ]
    assert loaded[SYM_RIVEN_STAT_NICKNAMES] == default[SYM_RIVEN_STAT_NICKNAMES]
    assert json.loads(data_path.read_text(encoding="utf-8")) == loaded


def test_schema_migration_normalizes_existing_user_alias_before_conflict(
    tmp_path: Path,
) -> None:
    registry, _, _ = _registry(
        tmp_path,
        default=_payload(base={"a": "Default"}),
        runtime=_payload(
            base={"a": "Legacy Override"},
            user={" A ": "  User Value  "},
        ),
    )

    loaded = registry.load()

    assert loaded[USER_ALIASES] == {"a": "User Value"}


@pytest.mark.parametrize("default_state", ["missing", "invalid_json"])
def test_schema_migration_aborts_when_default_file_is_unavailable(
    tmp_path: Path,
    default_state: str,
) -> None:
    registry, data_path, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Default"}),
        runtime=_payload(base={"内置": "Legacy Override"}),
    )
    if default_state == "missing":
        default_path.unlink()
    else:
        default_path.write_text("{not valid json", encoding="utf-8")
    original_runtime = data_path.read_bytes()

    with pytest.raises(RuntimeError, match="valid default nickname file"):
        registry.load()

    assert data_path.read_bytes() == original_runtime
    assert json.loads(data_path.read_text(encoding="utf-8"))["version"] == 1


@pytest.mark.parametrize("default_state", ["missing", "invalid_json"])
def test_schema_v2_sync_aborts_when_default_file_is_unavailable(
    tmp_path: Path,
    default_state: str,
) -> None:
    registry, data_path, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Default"}),
        runtime=_payload(
            version=2,
            base={"内置": "Runtime"},
            user={"用户": "Persistent"},
        ),
    )
    if default_state == "missing":
        default_path.unlink()
    else:
        default_path.write_text("{not valid json", encoding="utf-8")
    original_runtime = data_path.read_bytes()

    with pytest.raises(RuntimeError, match="valid default nickname file"):
        registry.sync_default_to_data()

    assert data_path.read_bytes() == original_runtime


@pytest.mark.parametrize("default_state", ["missing", "invalid_json"])
def test_schema_v2_load_aborts_when_default_file_is_unavailable(
    tmp_path: Path,
    default_state: str,
) -> None:
    registry, data_path, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Default"}),
        runtime=_payload(
            version=2,
            base={"内置": "Runtime"},
            user={"用户": "Persistent"},
        ),
    )
    if default_state == "missing":
        default_path.unlink()
    else:
        default_path.write_text("{not valid json", encoding="utf-8")
    original_runtime = data_path.read_bytes()

    with pytest.raises(RuntimeError, match="valid default nickname file"):
        registry.load()

    assert data_path.read_bytes() == original_runtime


@pytest.mark.parametrize(
    ("default_marker", "runtime_marker"),
    [("new", "old"), ("old", "new")],
    ids=["default-committed-first", "runtime-committed-first"],
)
def test_schema_v2_load_recovers_half_commit_from_authoritative_default(
    tmp_path: Path,
    default_marker: str,
    runtime_marker: str,
) -> None:
    default = _payload(
        version=2,
        base={"base": f"{default_marker} base"},
        riven_weapon={"weapon": f"{default_marker} weapon"},
        riven_stat={"stat": f"{default_marker} stat"},
    )
    runtime = _payload(
        version=2,
        base={"base": f"{runtime_marker} base"},
        riven_weapon={"weapon": f"{runtime_marker} weapon"},
        riven_stat={"stat": f"{runtime_marker} stat"},
        user={"用户": "Persistent"},
    )
    registry, data_path, _ = _registry(tmp_path, default=default, runtime=runtime)

    loaded = registry.load()

    assert loaded[SYM_BASE_NICKNAMES] == default[SYM_BASE_NICKNAMES]
    assert loaded[SYM_RIVEN_WEAPON_NICKNAMES] == default[
        SYM_RIVEN_WEAPON_NICKNAMES
    ]
    assert loaded[SYM_RIVEN_STAT_NICKNAMES] == default[SYM_RIVEN_STAT_NICKNAMES]
    assert loaded[USER_ALIASES] == {"用户": "Persistent"}
    assert json.loads(data_path.read_text(encoding="utf-8")) == loaded


@pytest.mark.parametrize(
    "invalid_default",
    [
        {
            SYM_BASE_NICKNAMES: {},
            SYM_RIVEN_WEAPON_NICKNAMES: {},
            SYM_RIVEN_STAT_NICKNAMES: {},
        },
        _payload(version="1"),
        {
            "version": 1,
            SYM_BASE_NICKNAMES: {},
            SYM_RIVEN_WEAPON_NICKNAMES: {},
        },
        _payload(base=["invalid"]),
        _payload(riven_weapon=["invalid"]),
        _payload(riven_stat=["invalid"]),
        _payload(base={"alias": 1}),
    ],
    ids=[
        "missing-version",
        "invalid-version",
        "missing-section",
        "invalid-base-section",
        "invalid-riven-weapon-section",
        "invalid-riven-stat-section",
        "invalid-full-name-type",
    ],
)
def test_schema_migration_rejects_invalid_default_structure(
    tmp_path: Path,
    invalid_default: dict[str, Any],
) -> None:
    registry, data_path, _ = _registry(
        tmp_path,
        default=invalid_default,
        runtime=_payload(base={"内置": "Legacy"}),
    )
    original_runtime = data_path.read_bytes()

    with pytest.raises(RuntimeError, match="valid default nickname file"):
        registry.load()

    assert data_path.read_bytes() == original_runtime


def test_schema_migration_rejects_non_string_default_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry, data_path, default_path = _registry(
        tmp_path,
        default=_payload(),
        runtime=_payload(base={"内置": "Legacy"}),
    )
    default_path.write_text("{}", encoding="utf-8")
    original_runtime = data_path.read_bytes()
    real_json_loads = json.loads

    def load_with_non_string_alias(raw: str):
        if raw == "{}":
            return _payload(base={1: "Value"})
        return real_json_loads(raw)

    monkeypatch.setattr(nickname_registry_module.json, "loads", load_with_non_string_alias)

    with pytest.raises(RuntimeError, match="valid default nickname file"):
        registry.load()

    assert data_path.read_bytes() == original_runtime


def test_migration_runs_before_default_sync_and_is_idempotent(tmp_path: Path) -> None:
    default = _payload(base={"内置": "Default"})
    runtime = _payload(base={"内置": "Default", "旧管理项": "Legacy Admin"})
    registry, data_path, _ = _registry(tmp_path, default=default, runtime=runtime)

    registry.sync_default_to_data(preserve_user_aliases=True)
    first = data_path.read_text(encoding="utf-8")
    registry.sync_default_to_data(preserve_user_aliases=True)

    synced = json.loads(data_path.read_text(encoding="utf-8"))
    assert synced["version"] == 2
    assert synced[USER_ALIASES] == {"旧管理项": "Legacy Admin"}
    assert synced[SYM_BASE_NICKNAMES] == {"内置": "Default"}
    assert data_path.read_text(encoding="utf-8") == first


def test_sync_rejects_disabled_user_alias_preservation_without_changing_file(
    tmp_path: Path,
) -> None:
    registry, data_path, _ = _registry(
        tmp_path,
        default=_payload(base={"被覆盖": "Default"}),
        runtime=_payload(base={"被覆盖": "Legacy Override"}),
    )
    original_runtime = data_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="preserve_user_aliases=False"):
        registry.sync_default_to_data(preserve_user_aliases=False)

    assert data_path.read_text(encoding="utf-8") == original_runtime


def test_default_upsert_migrates_runtime_before_replacing_old_default(
    tmp_path: Path,
) -> None:
    registry, data_path, _ = _registry(
        tmp_path,
        default=_payload(base={"内置": "Old Default"}),
        runtime=_payload(base={"内置": "Old Default"}),
    )

    registry.upsert_default_alias(
        alias="内置",
        full_name="New Default",
        sync_to_data=True,
    )

    synced = json.loads(data_path.read_text(encoding="utf-8"))
    assert synced[SYM_BASE_NICKNAMES] == {"内置": "New Default"}
    assert synced[USER_ALIASES] == {}


async def test_remote_refresh_migrates_runtime_before_replacing_old_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry, data_path, _ = _registry(
        tmp_path,
        default=_payload(base={"内置": "Old Default"}),
        runtime=_payload(base={"内置": "Old Default"}),
    )

    async def fetch_new_default(*_args, **_kwargs):
        return _payload(base={"内置": "New Remote Default"})

    monkeypatch.setattr(nickname_registry_module, "fetch_json", fetch_new_default)

    result = await registry.refresh_default_from_url(
        url="https://example.invalid/nicknames.json",
        merge_builtins=False,
    )

    synced = json.loads(data_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert synced[SYM_BASE_NICKNAMES] == {"内置": "New Remote Default"}
    assert synced[USER_ALIASES] == {}


def test_default_upsert_aborts_if_runtime_migration_cannot_persist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry, _, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Old Default"}),
        runtime=_payload(base={"内置": "Legacy Override"}),
    )
    original_default = default_path.read_text(encoding="utf-8")

    def fail_save(_data):
        raise OSError("disk full")

    monkeypatch.setattr(registry, "save", fail_save)

    with pytest.raises(RuntimeError, match="persist migrated nickname data"):
        registry.upsert_default_alias(alias="内置", full_name="New Default")

    assert default_path.read_text(encoding="utf-8") == original_default


def test_default_upsert_rolls_back_default_and_runtime_when_sync_save_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry, data_path, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Old Default"}),
        runtime=_payload(version=2, base={"内置": "Old Default"}),
    )
    original_default = default_path.read_bytes()
    original_runtime = data_path.read_bytes()

    def fail_runtime_save(_data):
        data_path.write_bytes(b"partial runtime write")
        raise OSError("runtime save failed")

    monkeypatch.setattr(registry, "save", fail_runtime_save)

    with pytest.raises(OSError, match="runtime save failed"):
        registry.upsert_default_alias(alias="内置", full_name="New Default")

    assert default_path.read_bytes() == original_default
    assert data_path.read_bytes() == original_runtime


async def test_remote_refresh_aborts_if_runtime_migration_cannot_persist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry, _, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Old Default"}),
        runtime=_payload(base={"内置": "Legacy Override"}),
    )
    original_default = default_path.read_text(encoding="utf-8")

    async def fetch_new_default(*_args, **_kwargs):
        return _payload(base={"内置": "New Remote Default"})

    def fail_save(_data):
        raise OSError("disk full")

    monkeypatch.setattr(nickname_registry_module, "fetch_json", fetch_new_default)
    monkeypatch.setattr(registry, "save", fail_save)

    with pytest.raises(RuntimeError, match="persist migrated nickname data"):
        await registry.refresh_default_from_url(
            url="https://example.invalid/nicknames.json",
            merge_builtins=False,
        )

    assert default_path.read_text(encoding="utf-8") == original_default


async def test_remote_refresh_rolls_back_default_and_runtime_when_sync_save_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry, data_path, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Old Default"}),
        runtime=_payload(version=2, base={"内置": "Old Default"}),
    )
    original_default = default_path.read_bytes()
    original_runtime = data_path.read_bytes()

    async def fetch_new_default(*_args, **_kwargs):
        return _payload(base={"内置": "New Remote Default"})

    def fail_runtime_save(_data):
        data_path.write_bytes(b"partial runtime write")
        raise OSError("runtime save failed")

    monkeypatch.setattr(nickname_registry_module, "fetch_json", fetch_new_default)
    monkeypatch.setattr(registry, "save", fail_runtime_save)

    result = await registry.refresh_default_from_url(
        url="https://example.invalid/nicknames.json",
        merge_builtins=False,
    )

    assert result["ok"] is False
    assert "runtime save failed" in result["reason"]
    assert default_path.read_bytes() == original_default
    assert data_path.read_bytes() == original_runtime


@pytest.mark.parametrize("target_kind", ["runtime", "default"])
def test_atomic_json_write_replace_failure_preserves_original_file(
    tmp_path: Path,
    monkeypatch,
    target_kind: str,
) -> None:
    registry, data_path, default_path = _registry(
        tmp_path,
        default=_payload(base={"内置": "Default"}),
        runtime=_payload(version=2, base={"内置": "Runtime"}),
    )
    target_path = data_path if target_kind == "runtime" else default_path
    original_bytes = target_path.read_bytes()
    original_files = {path.name for path in tmp_path.iterdir()}

    def fail_replace(_source, _destination):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        if target_kind == "runtime":
            registry.save(_payload(version=2, base={"内置": "Changed Runtime"}))
        else:
            registry.save_default(_payload(base={"内置": "Changed Default"}))

    assert target_path.read_bytes() == original_bytes
    assert {path.name for path in tmp_path.iterdir()} == original_files


def test_migrated_admin_alias_can_be_deleted_without_resurrection(
    tmp_path: Path,
) -> None:
    registry, _, _ = _registry(
        tmp_path,
        default=_payload(base={"内置": "Default"}),
        runtime=_payload(base={"内置": "Default", "旧管理项": "Legacy Admin"}),
    )
    registry.load()

    assert registry.delete_user_alias("旧管理项") == "deleted"
    assert registry.load()[USER_ALIASES] == {}
    assert registry.delete_user_alias("旧管理项") == "not_found"


def test_registry_instances_share_lock_and_sequential_upserts_preserve_both(
    tmp_path: Path,
) -> None:
    first, data_path, default_path = _registry(
        tmp_path,
        default=_payload(version=2),
        runtime=_payload(version=2),
    )
    second = NicknameRegistry(data_path=data_path, default_path=default_path)

    assert first._lock is second._lock

    first.upsert_alias(alias="first", full_name="First Value")
    second.upsert_alias(alias="second", full_name="Second Value")

    assert first.load()[USER_ALIASES] == {
        "first": "First Value",
        "second": "Second Value",
    }


def test_effective_alias_entries_report_winning_source_and_exclude_riven_stats(
    tmp_path: Path,
) -> None:
    base = {"仅基础": "Base", "覆盖项": "Base Value"}
    riven_weapon = {"仅武器": "Weapon", "覆盖项": "Weapon Value"}
    riven_stat = {"不应出现": "Stat"}
    registry, _, _ = _registry(
        tmp_path,
        default=_payload(
            version=2,
            base=base,
            riven_weapon=riven_weapon,
            riven_stat=riven_stat,
        ),
        runtime=_payload(
            version=2,
            base=base,
            riven_weapon=riven_weapon,
            riven_stat=riven_stat,
            user={"仅用户": "User", "覆盖项": "User Value"},
        ),
    )

    assert registry.get_effective_alias_entries() == [
        {"alias": "仅基础", "full_name": "Base", "source": SOURCE_BASE},
        {"alias": "仅武器", "full_name": "Weapon", "source": SOURCE_RIVEN_WEAPON},
        {"alias": "仅用户", "full_name": "User", "source": SOURCE_USER},
        {"alias": "覆盖项", "full_name": "User Value", "source": SOURCE_USER},
    ]
