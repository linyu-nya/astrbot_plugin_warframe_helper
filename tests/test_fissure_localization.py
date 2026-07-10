from __future__ import annotations

import pytest


class _EmptyLocalizationSource:
    async def translate_region(self, _node: str, *, language: str):
        return None

    async def get_mission_type_map(self, *, language: str):
        return {}

    async def get_fissure_tier_map(self, *, language: str):
        return {}


@pytest.mark.asyncio
async def test_warframestat_fissures_localize_english_display_fields(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _EmptyLocalizationSource()
    payload = {
        "fissures": [
            {
                "node": "Cambria (Earth)",
                "missionType": "Spy",
                "tier": "Lith",
                "expiry": "2099-01-01T00:00:00.000Z",
                "isHard": False,
                "isStorm": False,
            },
            {
                "node": "Cambire (Deimos)",
                "missionType": "Alchemy",
                "tier": "Omnia",
                "expiry": "2099-01-01T00:00:00.000Z",
                "isHard": False,
                "isStorm": False,
            },
        ]
    }

    async def fake_worldstate(**_kwargs):
        return payload

    monkeypatch.setattr(client, "_get_worldstate", fake_worldstate)

    fissures = await client.fetch_fissures(platform="pc", language="zh")

    assert fissures is not None
    assert [(row.tier, row.mission_type, row.node) for row in fissures] == [
        ("古纪", "间谍", "Cambria (地球)"),
        ("全能", "炼金", "Cambire (火卫二)"),
    ]
