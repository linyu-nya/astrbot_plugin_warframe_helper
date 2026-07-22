from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..clients.worldstate_client import Platform, WarframeWorldstateClient
from .push_events import PushEvent, collect_push_events


class AutoPushService:
    def __init__(
        self,
        *,
        context,
        worldstate_client: WarframeWorldstateClient,
        config: dict | None,
        state_path: Path | None = None,
        collector: Callable[..., Awaitable[list[PushEvent]]] = collect_push_events,
        plugin_data_dirname: str = "astrbot_plugin_warframe_helper",
    ) -> None:
        self._context = context
        self._worldstate_client = worldstate_client
        self._collector = collector
        section = config.get("auto_push") if isinstance(config, dict) else None
        section = section if isinstance(section, dict) else {}
        self.enabled = bool(section.get("enabled", True))
        try:
            interval = int(section.get("poll_interval_sec", 60))
        except (TypeError, ValueError):
            interval = 60
        self.poll_interval_sec = max(30, min(interval, 3600))
        self._state_path_override = state_path
        self._plugin_data_dirname = plugin_data_dirname
        self._targets: dict[str, dict[str, Any]] = self._load_targets()
        self._lock = asyncio.Lock()
        self._poll_task: asyncio.Task | None = None
        self._stop = False

    def _state_path(self) -> Path:
        if self._state_path_override is not None:
            return self._state_path_override
        base = Path(get_astrbot_plugin_data_path())
        return base / self._plugin_data_dirname / "auto_push_state.json"

    def _load_targets(self) -> dict[str, dict[str, Any]]:
        try:
            data = json.loads(self._state_path().read_text(encoding="utf-8"))
            targets = data.get("targets") if isinstance(data, dict) else None
            if not isinstance(targets, dict):
                return {}
            out: dict[str, dict[str, Any]] = {}
            for session, target in targets.items():
                if not isinstance(session, str) or not session or not isinstance(target, dict):
                    continue
                platform = str(target.get("platform") or "pc")
                if platform not in {"pc", "cn", "ps4", "xb1", "swi"}:
                    platform = "pc"
                seen_raw = target.get("seen")
                seen: dict[str, list[str]] = {}
                if isinstance(seen_raw, dict):
                    for kind, signatures in seen_raw.items():
                        if isinstance(kind, str) and isinstance(signatures, list):
                            seen[kind] = [
                                str(signature)
                                for signature in signatures
                                if isinstance(signature, str) and signature
                            ][-256:]
                out[session] = {
                    "platform": platform,
                    "baseline_pending": bool(target.get("baseline_pending", False)),
                    "seen": seen,
                }
            return out
        except (OSError, ValueError, TypeError):
            return {}

    def _save_targets(self) -> None:
        try:
            path = self._state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(path.suffix + ".tmp")
            temp_path.write_text(
                json.dumps({"targets": self._targets}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(path)
        except OSError as exc:
            logger.warning(f"save auto push state failed: {exc!s}")

    async def enable(self, *, session: str, platform: Platform = "pc") -> bool:
        session = str(session or "").strip()
        if not session:
            return False
        async with self._lock:
            existed = session in self._targets
            if existed:
                target = self._targets[session]
                if target.get("platform") != platform:
                    target["platform"] = platform
                    target["baseline_pending"] = True
                    target["seen"] = {}
            else:
                self._targets[session] = {
                    "platform": platform,
                    "baseline_pending": True,
                    "seen": {},
                }
            self._save_targets()
        return not existed

    async def disable(self, *, session: str) -> bool:
        session = str(session or "").strip()
        async with self._lock:
            existed = self._targets.pop(session, None) is not None
            if existed:
                self._save_targets()
        return existed

    def status(self, *, session: str) -> dict[str, Any]:
        target = self._targets.get(str(session or "").strip())
        if not isinstance(target, dict):
            return {"enabled": False, "platform": None}
        return {
            "enabled": True,
            "platform": str(target.get("platform") or "pc"),
            "baseline_pending": bool(target.get("baseline_pending", False)),
        }

    def start(self) -> None:
        if not self.enabled or self._poll_task is not None:
            return
        self._stop = False
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._stop = True
        task = self._poll_task
        self._poll_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass

    async def _poll_loop(self) -> None:
        while not self._stop:
            try:
                await self.poll_once()
            except Exception as exc:
                logger.warning(f"auto push poll failed: {exc!s}")
            await asyncio.sleep(self.poll_interval_sec)

    async def poll_once(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            targets = {
                session: dict(target)
                for session, target in self._targets.items()
                if isinstance(target, dict)
            }
        if not targets:
            return

        platform_events: dict[str, list[PushEvent]] = {}
        for target in targets.values():
            platform = str(target.get("platform") or "pc")
            if platform in platform_events:
                continue
            try:
                platform_events[platform] = await self._collector(
                    self._worldstate_client,
                    platform=cast(Platform, platform),
                )
            except Exception as exc:
                logger.warning(f"collect auto push events failed ({platform}): {exc!s}")
                platform_events[platform] = []

        changed = False
        for session, target in targets.items():
            platform = str(target.get("platform") or "pc")
            current = platform_events.get(platform, [])
            seen_raw = target.get("seen")
            seen: dict[str, list[str]] = (
                {str(kind): list(signatures) for kind, signatures in seen_raw.items()}
                if isinstance(seen_raw, dict)
                else {}
            )

            if bool(target.get("baseline_pending", False)):
                # A healthy PC world state always contains at least the daily
                # Sortie. Keep waiting when collection is empty instead of
                # treating a transient network failure as a valid baseline.
                if not current:
                    continue
                for event in current:
                    bucket = seen.setdefault(event.kind, [])
                    if event.signature not in bucket:
                        bucket.append(event.signature)
                        seen[event.kind] = bucket[-256:]
                target["seen"] = seen
                target["baseline_pending"] = False
                changed = True
            else:
                for event in current:
                    bucket = seen.setdefault(event.kind, [])
                    if event.signature in bucket:
                        continue
                    try:
                        await self._context.send_message(
                            session,
                            MessageChain().message(event.text),
                        )
                    except Exception as exc:
                        logger.warning(
                            f"auto push send failed session={session}: {exc!s}"
                        )
                        continue
                    bucket.append(event.signature)
                    seen[event.kind] = bucket[-256:]
                    changed = True
                target["seen"] = seen

            async with self._lock:
                if session in self._targets:
                    self._targets[session] = target

        if changed:
            async with self._lock:
                self._save_targets()
