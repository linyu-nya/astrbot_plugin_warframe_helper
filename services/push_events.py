from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

from ..clients.worldstate_client import (
    AlertInfo,
    ArchonHuntInfo,
    FissureInfo,
    NewsInfo,
    Platform,
    SortieInfo,
    VoidTraderInfo,
    WarframeWorldstateClient,
    WorldEventInfo,
)


@dataclass(frozen=True, slots=True)
class PushEvent:
    kind: str
    signature: str
    text: str


T = TypeVar("T")


async def _safe_fetch(call: Callable[[], Awaitable[T]]) -> T | None:
    try:
        return await call()
    except Exception:
        return None


def _fallback_signature(*parts: object) -> str:
    stable = "\x1f".join(str(part or "").strip() for part in parts)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]


def is_target_fissure(fissure: FissureInfo) -> bool:
    node = str(fissure.node or "").casefold()
    mission = str(fissure.mission_type or "").casefold()
    tier = str(fissure.tier or "").casefold()
    return bool(
        fissure.is_hard
        and ("塞德娜" in node or "sedna" in node)
        and (mission == "中断" or "disruption" in mission)
        and (tier == "全能" or "omnia" in tier)
    )


def void_trader_signature(info: VoidTraderInfo) -> str:
    inventory = sorted(
        (item.item, item.ducats, item.credits) for item in info.inventory
    )
    return _fallback_signature(info.event_id, info.location, repr(inventory))


def _fissure_event(info: FissureInfo) -> PushEvent:
    signature = info.event_id or _fallback_signature(
        info.node, info.mission_type, info.tier, info.expiry_utc
    )
    return PushEvent(
        kind="fissure",
        signature=signature,
        text="\n".join(
            [
                "【特殊裂缝】钢铁全能中断",
                f"节点：{info.node}",
                f"剩余时间：{info.eta}",
            ]
        ),
    )


def _alert_event(info: AlertInfo) -> PushEvent:
    signature = info.event_id or _fallback_signature(
        info.node, info.mission_type, info.reward, info.expiry_utc
    )
    lines = ["【Lotus 的礼物】", f"{info.node} | {info.mission_type}"]
    if info.reward:
        lines.append(f"奖励：{info.reward}")
    lines.append(f"剩余时间：{info.eta}")
    return PushEvent(kind="alert", signature=signature, text="\n".join(lines))


def _world_event(info: WorldEventInfo) -> PushEvent:
    lines = ["【特殊活动】", info.title]
    if info.node:
        lines.append(f"地点：{info.node}")
    if info.reward:
        lines.append(f"奖励：{info.reward}")
    lines.append(f"剩余时间：{info.eta}")
    return PushEvent(kind="world_event", signature=info.event_id, text="\n".join(lines))


def _news_event(info: NewsInfo) -> PushEvent:
    lines = ["【Warframe 官方更新】", info.message]
    if info.link:
        lines.append(info.link)
    return PushEvent(kind="news", signature=info.event_id, text="\n".join(lines))


def _sortie_event(info: SortieInfo) -> PushEvent:
    signature = info.event_id or _fallback_signature(
        info.activation_utc, info.boss, info.stages
    )
    head = " | ".join(part for part in (info.boss, info.faction) if part)
    lines = ["【每日突击】", head or "任务已更新"]
    for index, stage in enumerate(info.stages, start=1):
        modifier = f" | {stage.modifier}" if stage.modifier else ""
        lines.append(f"{index}. {stage.mission_type} | {stage.node}{modifier}")
    lines.append(f"剩余时间：{info.eta}")
    return PushEvent(kind="sortie", signature=signature, text="\n".join(lines))


def _archon_event(info: ArchonHuntInfo) -> PushEvent:
    signature = info.event_id or _fallback_signature(
        info.activation_utc, info.boss, info.stages
    )
    head = " | ".join(part for part in (info.boss, info.faction) if part)
    lines = ["【每周执刑官】", head or "任务已更新"]
    for index, stage in enumerate(info.stages, start=1):
        modifier = f" | {stage.modifier}" if stage.modifier else ""
        lines.append(f"{index}. {stage.mission_type} | {stage.node}{modifier}")
    lines.append(f"剩余时间：{info.eta}")
    return PushEvent(kind="archon_hunt", signature=signature, text="\n".join(lines))


def _void_trader_event(info: VoidTraderInfo) -> PushEvent:
    lines = ["【奸商新商品】"]
    if info.location:
        lines.append(f"地点：{info.location}")
    lines.append(f"剩余时间：{info.eta}")
    lines.append("商品：")
    for item in info.inventory:
        prices: list[str] = []
        if item.ducats is not None:
            prices.append(f"{item.ducats}杜卡德金币")
        if item.credits is not None:
            prices.append(f"{item.credits}现金")
        suffix = f" | {' + '.join(prices)}" if prices else ""
        lines.append(f"- {item.item}{suffix}")
    return PushEvent(
        kind="void_trader",
        signature=void_trader_signature(info),
        text="\n".join(lines),
    )


async def collect_push_events(
    client: WarframeWorldstateClient,
    *,
    platform: Platform = "pc",
) -> list[PushEvent]:
    events: list[PushEvent] = []

    fissures = await _safe_fetch(
        lambda: client.fetch_fissures(platform=platform, language="zh")
    )
    for fissure in fissures or []:
        if is_target_fissure(fissure):
            events.append(_fissure_event(fissure))

    alerts = await _safe_fetch(
        lambda: client.fetch_alerts(platform=platform, language="zh")
    )
    events.extend(_alert_event(alert) for alert in alerts or [])

    world_events = await _safe_fetch(
        lambda: client.fetch_world_events(platform=platform, language="zh")
    )
    events.extend(_world_event(event) for event in world_events or [])

    news = await _safe_fetch(lambda: client.fetch_news(platform=platform, language="zh"))
    events.extend(_news_event(item) for item in news or [] if item.is_update)

    sortie = await _safe_fetch(
        lambda: client.fetch_sortie(platform=platform, language="zh")
    )
    if sortie:
        events.append(_sortie_event(sortie))

    archon = await _safe_fetch(
        lambda: client.fetch_archon_hunt(platform=platform, language="zh")
    )
    if archon:
        events.append(_archon_event(archon))

    trader = await _safe_fetch(
        lambda: client.fetch_void_trader(platform=platform, language="zh")
    )
    if trader and trader.active and trader.inventory:
        events.append(_void_trader_event(trader))

    return events
