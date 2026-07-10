from __future__ import annotations

import pytest


def test_official_worldstate_prioritizes_live_cdn(worldstate_module) -> None:
    assert worldstate_module.OFFICIAL_WORLDSTATE_URLS[0] == (
        "https://api.warframe.com/cdn/worldState.php"
    )


@pytest.mark.asyncio
async def test_worldstate_falls_back_to_warframestat_aggregate(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient(
        warframestat_api_bases=["https://status.example.test"],
        warframestat_proxy_bases=[],
    )
    fallback_payload = {"fissures": [{"id": "fallback-fissure"}]}
    calls: list[list[str]] = []

    async def fake_fetch(urls, **_kwargs):
        calls.append(list(urls))
        return None if len(calls) == 1 else fallback_payload

    monkeypatch.setattr(client, "_fetch_json_resilient", fake_fetch)

    payload = await client._get_worldstate(platform="pc", language="zh")

    assert payload == fallback_payload
    assert len(calls) == 2
    assert calls[0][0] == "https://api.warframe.com/cdn/worldState.php"
    assert calls[1][0] == "https://status.example.test/pc?language=zh"
