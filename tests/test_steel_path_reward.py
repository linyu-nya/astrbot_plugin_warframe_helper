from __future__ import annotations

import pytest


class _LocalizationSource:
    async def translate_unique_name_loose(self, name: str, *, language: str):
        return name

    async def translate_display_name(self, name: str, *, language: str):
        return name


@pytest.mark.asyncio
async def test_fetch_steel_path_reward_parses_warframestat_shape(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _LocalizationSource()

    async def fake_worldstate(**_kwargs):
        return {
            "steelPath": {
                "currentReward": {
                    "name": "Umbra Forma Blueprint",
                    "cost": 150,
                },
                "expiry": "2099-01-01T00:00:00.000Z",
            }
        }

    monkeypatch.setattr(client, "_get_worldstate", fake_worldstate)

    result = await client.fetch_steel_path_reward(platform="pc", language="zh")

    assert result is not None
    assert result.reward == "Umbra Forma Blueprint"
    assert result.eta != "未知"


@pytest.mark.asyncio
async def test_fetch_steel_path_reward_falls_back_to_direct_endpoint(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _LocalizationSource()

    async def fake_worldstate(**_kwargs):
        return {"Time": 4070822400}

    async def fake_fetch(urls, **_kwargs):
        assert any("/pc/steelPath" in url for url in urls)
        return {
            "currentReward": {
                "name": "50,000 Kuva",
                "cost": 55,
            },
            "expiry": "2099-01-01T00:00:00.000Z",
        }

    monkeypatch.setattr(client, "_get_worldstate", fake_worldstate)
    monkeypatch.setattr(client, "_fetch_json_resilient", fake_fetch)

    result = await client.fetch_steel_path_reward(platform="pc", language="zh")

    assert result is not None
    assert result.reward == "50,000 Kuva"
