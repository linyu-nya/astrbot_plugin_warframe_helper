from __future__ import annotations

from datetime import datetime, timezone

import pytest


class _LocalizationSource:
    async def translate_region(self, node: str, *, language: str):
        return {
            "SolNode195": "Kappa (塞德娜)",
            "SolNode1": "E Prime (地球)",
        }.get(node, node)

    async def get_mission_type_map(self, *, language: str):
        return {}

    async def get_fissure_tier_map(self, *, language: str):
        return {}

    async def translate_unique_name(self, name: str, *, language: str):
        return name.split("/")[-1]

    async def translate_unique_name_loose(self, name: str, *, language: str):
        return name.split("/")[-1]


@pytest.mark.asyncio
async def test_existing_worldstate_models_keep_stable_ids_and_expiry(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _LocalizationSource()
    payload = {
        "ActiveMissions": [
            {
                "_id": {"$oid": "fissure-1"},
                "Expiry": {"$date": {"$numberLong": "4070908800000"}},
                "Node": "SolNode195",
                "MissionType": "MT_ARTIFACT",
                "Modifier": "VoidT6",
                "Hard": True,
            }
        ],
        "Sorties": [
            {
                "_id": {"$oid": "sortie-1"},
                "Activation": {"$date": {"$numberLong": "4070822400000"}},
                "Expiry": {"$date": {"$numberLong": "4070908800000"}},
                "Boss": "SORTIE_BOSS_AMBULAS",
                "Variants": [],
            }
        ],
        "LiteSorties": [
            {
                "_id": {"$oid": "archon-1"},
                "Activation": {"$date": {"$numberLong": "4070822400000"}},
                "Expiry": {"$date": {"$numberLong": "4071427200000"}},
                "Boss": "SORTIE_BOSS_BOREAL",
                "Missions": [],
            }
        ],
        "VoidTraders": [
            {
                "_id": {"$oid": "baro-1"},
                "Activation": {"$date": {"$numberLong": "946684800000"}},
                "Expiry": {"$date": {"$numberLong": "4071427200000"}},
                "Node": "MercuryHUB",
                "Manifest": [
                    {
                        "ItemType": "/Lotus/StoreItems/TestItem",
                        "PrimePrice": 350,
                        "RegularPrice": 200000,
                    }
                ],
            }
        ],
    }

    async def fake_worldstate(**_kwargs):
        return payload

    monkeypatch.setattr(client, "_get_worldstate", fake_worldstate)

    fissures = await client.fetch_fissures(platform="pc", language="zh")
    sortie = await client.fetch_sortie(platform="pc", language="zh")
    archon = await client.fetch_archon_hunt(platform="pc", language="zh")
    trader = await client.fetch_void_trader(platform="pc", language="zh")

    assert fissures and fissures[0].event_id == "fissure-1"
    assert fissures[0].expiry_utc == datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert sortie and sortie.event_id == "sortie-1"
    assert sortie.expiry_utc == datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert archon and archon.event_id == "archon-1"
    assert archon.expiry_utc is not None
    assert trader and trader.event_id == "baro-1"
    assert trader.active is True
    assert trader.expiry_utc is not None


@pytest.mark.asyncio
async def test_fetch_news_and_world_events_use_normalized_endpoints(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _LocalizationSource()

    async def fake_fetch(urls, **_kwargs):
        endpoint = " ".join(urls)
        if "/news" in endpoint:
            return [
                {
                    "id": "news-1",
                    "message": "Hotfix 1.2.3",
                    "link": "https://example.test/news",
                    "date": "2026-07-21T00:00:00.000Z",
                    "update": True,
                }
            ]
        if "/events" in endpoint:
            return [
                {
                    "id": "event-1",
                    "description": "Thermia Fractures",
                    "node": "Orb Vallis (Venus)",
                    "expiry": "2099-01-01T00:00:00.000Z",
                    "rewards": [{"items": ["Opticor Vandal"]}],
                }
            ]
        raise AssertionError(endpoint)

    monkeypatch.setattr(client, "_fetch_json_resilient", fake_fetch)

    news = await client.fetch_news(platform="pc", language="zh")
    events = await client.fetch_world_events(platform="pc", language="zh")

    assert news and news[0].event_id == "news-1"
    assert news[0].message == "Hotfix 1.2.3"
    assert news[0].link == "https://example.test/news"
    assert events and events[0].event_id == "event-1"
    assert events[0].title == "Thermia Fractures"
    assert events[0].reward == "Opticor Vandal"
    assert events[0].expiry_utc == datetime(2099, 1, 1, tzinfo=timezone.utc)

