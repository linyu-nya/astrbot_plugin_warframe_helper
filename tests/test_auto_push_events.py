from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"


@pytest.fixture
def push_events_module(worldstate_module, monkeypatch: pytest.MonkeyPatch):
    module_name = f"{PACKAGE}.services.push_events"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "services" / "push_events.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _fissure(module, **overrides):
    values = {
        "node": "Kappa (塞德娜)",
        "mission_type": "中断",
        "tier": "全能",
        "enemy": None,
        "is_storm": False,
        "is_hard": True,
        "eta": "1小时20分",
        "event_id": "fissure-target",
    }
    values.update(overrides)
    return module.FissureInfo(**values)


def test_special_fissure_requires_all_four_conditions(
    worldstate_module,
    push_events_module,
) -> None:
    target = _fissure(worldstate_module)
    assert push_events_module.is_target_fissure(target) is True

    assert (
        push_events_module.is_target_fissure(
            _fissure(worldstate_module, is_hard=False)
        )
        is False
    )
    assert (
        push_events_module.is_target_fissure(
            _fissure(worldstate_module, node="Kappa (火星)")
        )
        is False
    )
    assert (
        push_events_module.is_target_fissure(
            _fissure(worldstate_module, mission_type="生存")
        )
        is False
    )
    assert (
        push_events_module.is_target_fissure(
            _fissure(worldstate_module, tier="后纪")
        )
        is False
    )


@pytest.mark.asyncio
async def test_collector_builds_stable_text_push_events(
    worldstate_module,
    push_events_module,
) -> None:
    client_module = worldstate_module

    class _Client:
        async def fetch_fissures(self, **_kwargs):
            return [_fissure(client_module)]

        async def fetch_alerts(self, **_kwargs):
            return []

        async def fetch_world_events(self, **_kwargs):
            return [
                client_module.WorldEventInfo(
                    event_id="event-1",
                    title="热美亚裂缝",
                    node="奥布山谷（金星）",
                    reward="奥提克光子枪破坏者",
                    eta="2天",
                )
            ]

        async def fetch_news(self, **_kwargs):
            return [
                client_module.NewsInfo(
                    event_id="news-1",
                    message="更新 43.1.0",
                    link="https://example.test/update",
                    is_update=True,
                ),
                client_module.NewsInfo(
                    event_id="news-2",
                    message="普通社区新闻",
                    link="https://example.test/community",
                    is_update=False,
                )
            ]

        async def fetch_sortie(self, **_kwargs):
            return client_module.SortieInfo(
                boss="Ambulas",
                faction="Corpus",
                eta="6小时",
                stages=(),
                event_id="sortie-1",
            )

        async def fetch_archon_hunt(self, **_kwargs):
            return client_module.ArchonHuntInfo(
                boss="Boreal",
                faction="Narmer",
                eta="5天",
                stages=(),
                event_id="archon-1",
            )

        async def fetch_void_trader(self, **_kwargs):
            return client_module.VoidTraderInfo(
                active=True,
                location="水星中继站",
                eta="1天20小时",
                inventory=(
                    client_module.VoidTraderItem(
                        item="Primed Test", ducats=350, credits=200000
                    ),
                ),
                event_id="baro-1",
            )

    events = await push_events_module.collect_push_events(_Client(), platform="pc")
    by_kind = {event.kind: event for event in events}

    assert set(by_kind) == {
        "fissure",
        "world_event",
        "news",
        "sortie",
        "archon_hunt",
        "void_trader",
    }
    assert by_kind["fissure"].signature == "fissure-target"
    assert "钢铁全能中断" in by_kind["fissure"].text
    assert "剩余时间：1小时20分" in by_kind["fissure"].text
    assert "https://example.test/update" in by_kind["news"].text
    assert all("普通社区新闻" not in event.text for event in events)
    assert "Primed Test" in by_kind["void_trader"].text
    assert "剩余时间：1天20小时" in by_kind["void_trader"].text


def test_void_trader_signature_changes_only_with_visit_or_inventory(
    worldstate_module,
    push_events_module,
) -> None:
    first = worldstate_module.VoidTraderInfo(
        active=True,
        location="水星中继站",
        eta="1天",
        inventory=(worldstate_module.VoidTraderItem("A", 100, 1000),),
        event_id="baro-1",
    )
    same_visit_new_eta = worldstate_module.VoidTraderInfo(
        active=True,
        location="水星中继站",
        eta="20小时",
        inventory=(worldstate_module.VoidTraderItem("A", 100, 1000),),
        event_id="baro-1",
    )
    changed_inventory = worldstate_module.VoidTraderInfo(
        active=True,
        location="水星中继站",
        eta="20小时",
        inventory=(worldstate_module.VoidTraderItem("B", 100, 1000),),
        event_id="baro-1",
    )

    assert push_events_module.void_trader_signature(first) == (
        push_events_module.void_trader_signature(same_visit_new_eta)
    )
    assert push_events_module.void_trader_signature(first) != (
        push_events_module.void_trader_signature(changed_inventory)
    )
