from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import unicodedata
from functools import wraps
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..http_utils import fetch_json

NICKNAME_FILE_NAME = "warframe_nicknames.json"

SYM_BASE_NICKNAMES = "_BUILTIN_BASE_NICKNAMES"
SYM_RIVEN_WEAPON_NICKNAMES = "_BUILTIN_RIVEN_WEAPON_NICKNAMES"
SYM_RIVEN_STAT_NICKNAMES = "_BUILTIN_RIVEN_STAT_NICKNAMES"
USER_ALIASES = "aliases"

NICKNAME_SCHEMA_VERSION = 2

SOURCE_BASE = "base"
SOURCE_RIVEN_WEAPON = "riven_weapon"
SOURCE_USER = "user"

DEFAULT_NICKNAME_REMOTE_URL = "https://gh-proxy.org/https://raw.githubusercontent.com/linyu-nya/astrbot_plugin_warframe_helper/refs/heads/master/assets/warframe_nicknames.default.json"

_LEGACY_KEY_MAP: dict[str, str] = {
    "#sym:_BUILTIN_BASE_NICKNAMES": SYM_BASE_NICKNAMES,
    "#sym:_BUILTIN_RIVEN_WEAPON_NICKNAMES": SYM_RIVEN_WEAPON_NICKNAMES,
    "#sym:_BUILTIN_RIVEN_STAT_NICKNAMES": SYM_RIVEN_STAT_NICKNAMES,
}

_REGISTRY_LOCK = threading.RLock()


def _locked(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


def normalize_alias_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.strip().lower()
    text = re.sub(r"\s+", "", text)
    return text


def normalize_alias_value(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


class NicknameRegistry:
    def __init__(
        self,
        *,
        data_path: str | Path | None = None,
        default_path: str | Path | None = None,
    ) -> None:
        self._lock = _REGISTRY_LOCK
        if data_path is None:
            self._plugin_data_dir = (
                Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_warframe_helper"
            )
            self._path = self._plugin_data_dir / NICKNAME_FILE_NAME
        else:
            self._path = Path(data_path)
            self._plugin_data_dir = self._path.parent

        self._plugin_data_dir.mkdir(parents=True, exist_ok=True)
        if default_path is None:
            self._default_path = (
                Path(__file__).resolve().parents[1]
                / "assets"
                / "warframe_nicknames.default.json"
            )
        else:
            self._default_path = Path(default_path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def default_path(self) -> Path:
        return self._default_path

    def _sanitize_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        raw: dict[str, Any] = dict(payload or {})
        changed = False

        # Backward compatibility: migrate old #sym:* keys into new keys.
        for legacy_key, new_key in _LEGACY_KEY_MAP.items():
            legacy_val = raw.get(legacy_key)
            if isinstance(legacy_val, dict):
                dst = raw.get(new_key)
                if not isinstance(dst, dict):
                    dst = {}
                for k, v in legacy_val.items():
                    if k not in dst:
                        dst[k] = v
                raw[new_key] = dst
                raw.pop(legacy_key, None)
                changed = True

        if not isinstance(raw.get("version"), int):
            raw["version"] = 1
            changed = True

        for key in (
            SYM_BASE_NICKNAMES,
            SYM_RIVEN_WEAPON_NICKNAMES,
            SYM_RIVEN_STAT_NICKNAMES,
            USER_ALIASES,
        ):
            if not isinstance(raw.get(key), dict):
                raw[key] = {}
                changed = True

        return raw, changed

    def _default_payload(self) -> dict[str, Any]:
        if self._default_path.exists():
            try:
                raw = json.loads(self._default_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    normalized, _ = self._sanitize_payload(raw)
                    return normalized
            except Exception as exc:
                logger.warning(
                    f"Failed to parse default nickname json {self._default_path}: {exc!s}"
                )

        return {
            "version": NICKNAME_SCHEMA_VERSION,
            SYM_BASE_NICKNAMES: {},
            SYM_RIVEN_WEAPON_NICKNAMES: {},
            SYM_RIVEN_STAT_NICKNAMES: {},
            USER_ALIASES: {},
        }

    def _strict_default_payload(self) -> dict[str, Any]:
        try:
            raw = json.loads(self._default_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "Cannot migrate nickname data without a valid default nickname file"
            ) from exc
        if not isinstance(raw, dict) or type(raw.get("version")) is not int:
            raise RuntimeError(
                "Cannot migrate nickname data without a valid default nickname file"
            )

        for section in (
            SYM_BASE_NICKNAMES,
            SYM_RIVEN_WEAPON_NICKNAMES,
            SYM_RIVEN_STAT_NICKNAMES,
        ):
            block = raw.get(section)
            if not isinstance(block, dict) or any(
                not isinstance(alias, str) or not isinstance(full_name, str)
                for alias, full_name in block.items()
            ):
                raise RuntimeError(
                    "Cannot migrate nickname data without a valid default nickname file"
                )
        return raw

    def _migrate_runtime_payload(
        self,
        payload: dict[str, Any],
        default_data: dict[str, Any],
    ) -> bool:
        version = payload.get("version")
        if isinstance(version, int) and version >= NICKNAME_SCHEMA_VERSION:
            return False

        default_base = default_data.get(SYM_BASE_NICKNAMES)
        runtime_base = payload.get(SYM_BASE_NICKNAMES)
        aliases = payload.get(USER_ALIASES)
        if not isinstance(default_base, dict):
            default_base = {}
        if not isinstance(runtime_base, dict):
            runtime_base = {}
        if not isinstance(aliases, dict):
            aliases = {}
        else:
            normalized_aliases: dict[str, str] = {}
            for alias, full_name in aliases.items():
                if not isinstance(alias, str) or not isinstance(full_name, str):
                    continue
                key = normalize_alias_key(alias)
                value = normalize_alias_value(full_name)
                if key and value:
                    normalized_aliases[key] = value
            aliases = normalized_aliases

        for alias, full_name in runtime_base.items():
            if not isinstance(alias, str) or not isinstance(full_name, str):
                continue
            if default_base.get(alias) == full_name:
                continue
            key = normalize_alias_key(alias)
            value = normalize_alias_value(full_name)
            if key and value:
                aliases.setdefault(key, value)

        payload[USER_ALIASES] = dict(sorted(aliases.items(), key=lambda item: item[0]))
        for section in (
            SYM_BASE_NICKNAMES,
            SYM_RIVEN_WEAPON_NICKNAMES,
            SYM_RIVEN_STAT_NICKNAMES,
        ):
            block = default_data.get(section)
            payload[section] = dict(block) if isinstance(block, dict) else {}
        payload["version"] = NICKNAME_SCHEMA_VERSION
        return True

    @_locked
    def load_default(self) -> dict[str, Any]:
        data = self._default_payload()
        normalized, changed = self._sanitize_payload(data)
        if changed:
            try:
                self.save_default(normalized)
            except Exception as exc:
                logger.warning(f"Failed to persist normalized default nickname json: {exc!s}")
        return normalized

    @_locked
    def save_default(self, data: dict[str, Any]) -> None:
        payload, _ = self._sanitize_payload(dict(data or {}))
        self._write_json_atomic(self._default_path, payload)

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        NicknameRegistry._write_bytes_atomic(path, content)

    @staticmethod
    def _write_bytes_atomic(path: Path, content: bytes) -> None:
        descriptor, temp_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
            os.replace(temp_path, path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _file_snapshot(path: Path) -> bytes | None:
        return path.read_bytes() if path.exists() else None

    @staticmethod
    def _restore_snapshot(path: Path, snapshot: bytes | None) -> None:
        if snapshot is None:
            path.unlink(missing_ok=True)
            return
        if not path.exists() or path.read_bytes() != snapshot:
            NicknameRegistry._write_bytes_atomic(path, snapshot)

    @_locked
    def _save_default_and_sync(self, default_data: dict[str, Any]) -> dict[str, int]:
        default_snapshot = self._file_snapshot(self._default_path)
        runtime_snapshot = self._file_snapshot(self._path)
        try:
            self.save_default(default_data)
            return self.sync_default_to_data(preserve_user_aliases=True)
        except Exception as exc:
            rollback_errors: list[str] = []
            for label, path, snapshot in (
                ("default", self._default_path, default_snapshot),
                ("runtime", self._path, runtime_snapshot),
            ):
                try:
                    self._restore_snapshot(path, snapshot)
                except Exception as rollback_exc:
                    rollback_errors.append(f"{label}: {rollback_exc!s}")
            if rollback_errors:
                details = "; ".join(rollback_errors)
                raise RuntimeError(
                    f"Nickname update failed ({exc!s}); rollback failed ({details})"
                ) from exc
            raise

    @_locked
    def ensure_file(self) -> None:
        if self._path.exists():
            return

        payload = self._strict_default_payload()
        try:
            self.save(payload)
        except Exception as exc:
            logger.warning(f"Failed to initialize nickname json: {exc!s}")

    @_locked
    def load(self) -> dict[str, Any]:
        self.ensure_file()
        if not self._path.exists():
            return self._default_payload()

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return self._default_payload()
        except Exception as exc:
            logger.warning(f"Failed to load nickname json, fallback to default: {exc!s}")
            return self._default_payload()

        raw, changed = self._sanitize_payload(raw)
        default_data = self._strict_default_payload()
        migrated = self._migrate_runtime_payload(raw, default_data)
        reconciled = False
        if not migrated:
            for section in (
                SYM_BASE_NICKNAMES,
                SYM_RIVEN_WEAPON_NICKNAMES,
                SYM_RIVEN_STAT_NICKNAMES,
            ):
                default_block = default_data[section]
                if raw.get(section) != default_block:
                    raw[section] = dict(default_block)
                    reconciled = True

        if changed or migrated or reconciled:
            try:
                self.save(raw)
            except Exception as exc:
                if migrated:
                    raise RuntimeError(
                        "Failed to persist migrated nickname data"
                    ) from exc
                if reconciled:
                    raise
                logger.warning(f"Failed to persist migrated nickname json: {exc!s}")
        return raw

    @_locked
    def save(self, data: dict[str, Any]) -> None:
        payload, _ = self._sanitize_payload(dict(data or {}))
        self._write_json_atomic(self._path, payload)

    @_locked
    def sync_default_to_data(self, *, preserve_user_aliases: bool = True) -> dict[str, int]:
        # Deprecated compatibility parameter; default sync always preserves aliases.
        if not preserve_user_aliases:
            raise ValueError("preserve_user_aliases=False is no longer supported")
        runtime_data = self.load()
        default_data = self._strict_default_payload()
        aliases = runtime_data.get(USER_ALIASES)
        if isinstance(aliases, dict):
            default_data[USER_ALIASES] = aliases

        default_data["version"] = max(
            NICKNAME_SCHEMA_VERSION,
            int(default_data.get("version", 0)),
        )

        self.save(default_data)
        return {
            "base_aliases": len(default_data.get(SYM_BASE_NICKNAMES, {})),
            "user_aliases": len(default_data.get(USER_ALIASES, {})),
        }

    def get_alias_map(self, *sections: str) -> dict[str, str]:
        data = self.load()
        if not sections:
            sections = (
                SYM_BASE_NICKNAMES,
                SYM_RIVEN_WEAPON_NICKNAMES,
                SYM_RIVEN_STAT_NICKNAMES,
                USER_ALIASES,
            )

        out: dict[str, str] = {}
        for sec in sections:
            block = data.get(sec)
            if not isinstance(block, dict):
                continue
            for alias, full_name in block.items():
                if not isinstance(alias, str) or not isinstance(full_name, str):
                    continue
                key = normalize_alias_key(alias)
                value = normalize_alias_value(full_name)
                if not key or not value:
                    continue
                out[key] = value
        return out

    @_locked
    def upsert_alias(
        self,
        *,
        alias: str,
        full_name: str,
        section: str = USER_ALIASES,
    ) -> tuple[str, str]:
        key = normalize_alias_key(alias)
        value = normalize_alias_value(full_name)
        if not key:
            raise ValueError("alias is empty")
        if not value:
            raise ValueError("full_name is empty")

        data = self.load()
        block = data.get(section)
        if not isinstance(block, dict):
            block = {}

        block[key] = value
        data[section] = dict(sorted(block.items(), key=lambda kv: kv[0]))
        self.save(data)
        return key, value

    @_locked
    def delete_user_alias(self, alias: str) -> str:
        key = normalize_alias_key(alias)
        if not key:
            raise ValueError("alias is empty")

        data = self.load()
        aliases = data.get(USER_ALIASES)
        if isinstance(aliases, dict):
            stored_key = next(
                (item for item in aliases if normalize_alias_key(item) == key),
                None,
            )
            if stored_key is not None:
                del aliases[stored_key]
                data[USER_ALIASES] = dict(
                    sorted(aliases.items(), key=lambda item: item[0])
                )
                self.save(data)
                return "deleted"

        for section in (
            SYM_BASE_NICKNAMES,
            SYM_RIVEN_WEAPON_NICKNAMES,
            SYM_RIVEN_STAT_NICKNAMES,
        ):
            block = data.get(section)
            if isinstance(block, dict) and any(
                normalize_alias_key(item) == key for item in block
            ):
                return "builtin_only"
        return "not_found"

    def get_effective_alias_entries(self) -> list[dict[str, str]]:
        data = self.load()
        winners: dict[str, dict[str, str]] = {}
        for section, source in (
            (SYM_BASE_NICKNAMES, SOURCE_BASE),
            (SYM_RIVEN_WEAPON_NICKNAMES, SOURCE_RIVEN_WEAPON),
            (USER_ALIASES, SOURCE_USER),
        ):
            block = data.get(section)
            if not isinstance(block, dict):
                continue
            for alias, full_name in block.items():
                if not isinstance(alias, str) or not isinstance(full_name, str):
                    continue
                key = normalize_alias_key(alias)
                value = normalize_alias_value(full_name)
                if not key or not value:
                    continue
                winners[key] = {
                    "alias": key,
                    "full_name": value,
                    "source": source,
                }
        return [winners[key] for key in sorted(winners)]

    @_locked
    def upsert_default_alias(
        self,
        *,
        alias: str,
        full_name: str,
        section: str = SYM_BASE_NICKNAMES,
        sync_to_data: bool = True,
    ) -> tuple[str, str]:
        key = normalize_alias_key(alias)
        value = normalize_alias_value(full_name)
        if not key:
            raise ValueError("alias is empty")
        if not value:
            raise ValueError("full_name is empty")

        self.load()
        data = self.load_default()
        block = data.get(section)
        if not isinstance(block, dict):
            block = {}

        block[key] = value
        data[section] = dict(sorted(block.items(), key=lambda kv: kv[0]))
        if sync_to_data:
            self._save_default_and_sync(data)
        else:
            self.save_default(data)

        return key, value

    def _merge_remote_builtins(self, normalized: dict[str, Any]) -> None:
        local = self._default_payload()
        for section in (
            SYM_BASE_NICKNAMES,
            SYM_RIVEN_WEAPON_NICKNAMES,
            SYM_RIVEN_STAT_NICKNAMES,
        ):
            remote_section = normalized.get(section)
            local_section = local.get(section)
            if not isinstance(remote_section, dict):
                remote_section = {}
            if not isinstance(local_section, dict):
                local_section = {}
            merged = {
                key: value
                for key, value in remote_section.items()
                if isinstance(key, str) and isinstance(value, str)
            }
            merged.update(
                {
                    key: value
                    for key, value in local_section.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            )
            normalized[section] = merged

    async def refresh_default_from_url(
        self,
        *,
        url: str = DEFAULT_NICKNAME_REMOTE_URL,
        merge_builtins: bool = True,
    ) -> dict[str, Any]:
        """Fetch remote nickname table and save as new default.

        Args:
            url: Remote URL to fetch the JSON from.
            merge_builtins: If True, merge local _BUILTIN_* sections with the
                remote data so that local expansions are preserved. Local
                entries take priority for same-key conflicts.
        """
        src = str(url or "").strip() or DEFAULT_NICKNAME_REMOTE_URL
        data = await fetch_json(src, timeout_sec=20.0)
        if not isinstance(data, dict):
            return {
                "ok": False,
                "reason": "invalid_json",
                "url": src,
            }

        normalized, _ = self._sanitize_payload(data)

        with self._lock:
            self.load()
            if merge_builtins:
                self._merge_remote_builtins(normalized)
            try:
                sync_stats = self._save_default_and_sync(normalized)
                return {
                    "ok": True,
                    "url": src,
                    "base_aliases": int(sync_stats.get("base_aliases", 0)),
                    "user_aliases": int(sync_stats.get("user_aliases", 0)),
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "reason": f"save_failed: {exc!s}",
                    "url": src,
                }
