from __future__ import annotations

import importlib.util
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"


class _MessageChain:
    def __init__(self) -> None:
        self.text = ""

    def message(self, text: str):
        self.text = text
        return self


class _Context:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, session: str, chain: _MessageChain) -> None:
        self.sent.append((session, chain.text))


@pytest.fixture
def auto_push_module(monkeypatch: pytest.MonkeyPatch):
    event_module = types.ModuleType("astrbot.api.event")
    event_module.MessageChain = _MessageChain
    monkeypatch.setitem(sys.modules, "astrbot.api.event", event_module)

    path_module = types.ModuleType("astrbot.core.utils.astrbot_path")
    path_module.get_astrbot_plugin_data_path = lambda: str(ROOT / ".test-data")
    monkeypatch.setitem(sys.modules, "astrbot.core", types.ModuleType("astrbot.core"))
    monkeypatch.setitem(
        sys.modules, "astrbot.core.utils", types.ModuleType("astrbot.core.utils")
    )
    monkeypatch.setitem(sys.modules, "astrbot.core.utils.astrbot_path", path_module)

    client_module = types.ModuleType(f"{PACKAGE}.clients.worldstate_client")
    client_module.Platform = str
    client_module.WarframeWorldstateClient = object
    monkeypatch.setitem(
        sys.modules, f"{PACKAGE}.clients.worldstate_client", client_module
    )

    @dataclass(frozen=True, slots=True)
    class PushEvent:
        kind: str
        signature: str
        text: str

    async def unused_collector(*_args, **_kwargs):
        return []

    push_events = types.ModuleType(f"{PACKAGE}.services.push_events")
    push_events.PushEvent = PushEvent
    push_events.collect_push_events = unused_collector
    monkeypatch.setitem(sys.modules, f"{PACKAGE}.services.push_events", push_events)

    module_name = f"{PACKAGE}.services.auto_push"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "services" / "auto_push.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_first_poll_is_silent_then_only_new_event_is_sent(
    auto_push_module,
    tmp_path: Path,
) -> None:
    batches = [
        [auto_push_module.PushEvent("news", "news-1", "第一条")],
        [
            auto_push_module.PushEvent("news", "news-1", "第一条"),
            auto_push_module.PushEvent("news", "news-2", "第二条"),
        ],
        [
            auto_push_module.PushEvent("news", "news-1", "第一条"),
            auto_push_module.PushEvent("news", "news-2", "第二条"),
        ],
    ]

    async def collector(_client, *, platform):
        return batches.pop(0)

    context = _Context()
    state_path = tmp_path / "auto_push.json"
    service = auto_push_module.AutoPushService(
        context=context,
        worldstate_client=object(),
        config={"auto_push": {"poll_interval_sec": 60}},
        state_path=state_path,
        collector=collector,
    )

    assert await service.enable(session="group:1", platform="pc") is True
    await service.poll_once()
    assert context.sent == []

    await service.poll_once()
    assert context.sent == [("group:1", "第二条")]

    await service.poll_once()
    assert context.sent == [("group:1", "第二条")]
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["targets"]["group:1"]["seen"]["news"] == ["news-1", "news-2"]


@pytest.mark.asyncio
async def test_restart_keeps_seen_state_and_delivers_missed_event(
    auto_push_module,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "auto_push.json"
    state_path.write_text(
        json.dumps(
            {
                "targets": {
                    "group:1": {
                        "platform": "pc",
                        "baseline_pending": False,
                        "seen": {"sortie": ["sortie-1"]},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    async def collector(_client, *, platform):
        return [auto_push_module.PushEvent("sortie", "sortie-2", "新突击")]

    context = _Context()
    service = auto_push_module.AutoPushService(
        context=context,
        worldstate_client=object(),
        config={},
        state_path=state_path,
        collector=collector,
    )

    await service.poll_once()

    assert context.sent == [("group:1", "新突击")]


@pytest.mark.asyncio
async def test_empty_first_poll_does_not_finish_baseline(
    auto_push_module,
    tmp_path: Path,
) -> None:
    batches = [
        [],
        [auto_push_module.PushEvent("sortie", "sortie-1", "当前突击")],
    ]

    async def collector(_client, *, platform):
        return batches.pop(0)

    context = _Context()
    service = auto_push_module.AutoPushService(
        context=context,
        worldstate_client=object(),
        config={},
        state_path=tmp_path / "auto_push.json",
        collector=collector,
    )
    await service.enable(session="group:1", platform="pc")

    await service.poll_once()
    assert service.status(session="group:1")["baseline_pending"] is True

    await service.poll_once()
    assert context.sent == []
    assert service.status(session="group:1")["baseline_pending"] is False


@pytest.mark.asyncio
async def test_disable_removes_target_and_status(
    auto_push_module,
    tmp_path: Path,
) -> None:
    service = auto_push_module.AutoPushService(
        context=_Context(),
        worldstate_client=object(),
        config={},
        state_path=tmp_path / "auto_push.json",
        collector=lambda *_args, **_kwargs: None,
    )

    await service.enable(session="group:1", platform="pc")
    assert service.status(session="group:1")["enabled"] is True
    assert await service.disable(session="group:1") is True
    assert service.status(session="group:1")["enabled"] is False
    assert await service.disable(session="group:1") is False


@pytest.mark.asyncio
async def test_switching_platform_resets_seen_state_and_rebuilds_baseline(
    auto_push_module,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "auto_push.json"
    state_path.write_text(
        json.dumps(
            {
                "targets": {
                    "group:1": {
                        "platform": "pc",
                        "baseline_pending": False,
                        "seen": {"news": ["pc-news-1"]},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    async def collector(_client, *, platform):
        assert platform == "cn"
        return [auto_push_module.PushEvent("news", "cn-news-1", "国服新闻")]

    context = _Context()
    service = auto_push_module.AutoPushService(
        context=context,
        worldstate_client=object(),
        config={},
        state_path=state_path,
        collector=collector,
    )

    assert await service.enable(session="group:1", platform="cn") is False
    assert service.status(session="group:1") == {
        "enabled": True,
        "platform": "cn",
        "baseline_pending": True,
    }

    await service.poll_once()

    assert context.sent == []
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["targets"]["group:1"]["seen"] == {"news": ["cn-news-1"]}


def test_poll_interval_has_safe_minimum(auto_push_module, tmp_path: Path) -> None:
    service = auto_push_module.AutoPushService(
        context=_Context(),
        worldstate_client=object(),
        config={"auto_push": {"poll_interval_sec": 1}},
        state_path=tmp_path / "auto_push.json",
    )

    assert service.poll_interval_sec == 30
