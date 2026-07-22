from __future__ import annotations

import pytest


class _LocalizationSource:
    async def get_mission_type_map(self, *, language: str):
        return {}


def test_archimedea_modifier_translation_uses_research_kind(
    worldstate_module,
) -> None:
    translate = worldstate_module._localize_archimedea_modifier

    assert translate(
        "Reinforcements",
        language="zh",
        modifier_type="deviation",
        kind_code="CT_LAB",
    ) == "协调阵线"
    assert translate(
        "Reinforcements",
        language="zh",
        modifier_type="deviation",
        kind_code="CT_HEX",
    ) == "敌军增援"


@pytest.mark.asyncio
async def test_fetch_archimedeas_parses_official_conquests(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _LocalizationSource()
    payload = {
        "Conquests": [
            {
                "Activation": {"$date": {"$numberLong": "1784505600000"}},
                "Expiry": {"$date": {"$numberLong": "1785110400000"}},
                "Type": "CT_LAB",
                "RandomSeed": 123,
                "Missions": [
                    {
                        "faction": "FC_MITW",
                        "missionType": "MT_ARTIFACT",
                        "difficulties": [
                            {
                                "type": "CD_NORMAL",
                                "deviation": "StickyFingers",
                                "risks": ["Deflectors"],
                            },
                            {
                                "type": "CD_HARD",
                                "deviation": "StickyFingers",
                                "risks": ["Deflectors", "ExplosiveCrawlers"],
                            },
                        ],
                    },
                    {
                        "faction": "FC_MITW",
                        "missionType": "MT_EXTERMINATION",
                        "difficulties": [
                            {
                                "type": "CD_HARD",
                                "deviation": "FortifiedFoes",
                                "risks": ["Voidburst", "AntiMaterialWeapons"],
                            }
                        ],
                    },
                    {
                        "faction": "FC_MITW",
                        "missionType": "MT_ASSASSINATION",
                        "difficulties": [
                            {
                                "type": "CD_HARD",
                                "deviation": "Reinforcements",
                                "risks": ["ShieldedFoes", "EMPBlackHole"],
                            }
                        ],
                    },
                ],
                "Variables": ["Withering", "Framecurse"],
            }
        ]
    }

    async def fake_worldstate(**_kwargs):
        return payload

    monkeypatch.setattr(client, "_get_worldstate", fake_worldstate)

    result = await client.fetch_archimedeas(platform="pc", language="zh")

    assert len(result) == 1
    assert result[0].kind == "深层科研"
    assert result[0].event_id == "CT_LAB:1784505600:123"
    assert result[0].missions[0].mission_type == "中断"
    assert result[0].missions[0].faction == "墙中人"
    assert [
        (mission.deviation, mission.risks) for mission in result[0].missions
    ] == [
        ("暴食贪囤", ("坚不可摧", "易爆潜能")),
        ("密闭装甲", ("死后冲击", "指挥型重型炮兵")),
        ("协调阵线", ("强化好战", "迷人弧犬")),
    ]
    assert result[0].personal_modifiers == ("Withering", "Framecurse")
    assert result[0].expiry_utc is not None


@pytest.mark.asyncio
async def test_fetch_archimedeas_parses_warframestat_aggregate(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _LocalizationSource()
    payload = {
        "archimedeas": [
            {
                "type": "C T_ H E X",
                "typeKey": "C T_ H E X",
                "activation": "2026-07-20T00:00:00.000Z",
                "expiry": "2026-07-27T00:00:00.000Z",
                "missions": [
                    {
                        "faction": "Scaldra",
                        "missionType": "Legacyte Harvest",
                        "deviation": {
                            "key": "ExplosiveEnergy",
                            "name": "Miasmite Mash",
                        },
                        "risks": [
                            {
                                "key": "FactionSwarm_Scaldra",
                                "name": "Scaldra Speed Run",
                                "isHard": False,
                            },
                            {
                                "key": "BalloonFest",
                                "name": "Balloonfest",
                                "isHard": True,
                            },
                        ],
                    },
                    {
                        "faction": "Techrot",
                        "missionType": "Legacyte Harvest",
                        "deviation": {
                            "key": "HighScalingLegacyte",
                            "name": "Growth Hormones",
                        },
                        "risks": [
                            {
                                "key": "InfectedTechrot",
                                "name": "Corrupted Flesh",
                            },
                            {
                                "key": "HostileOvergrowth",
                                "name": "It's Alive",
                            },
                        ],
                    },
                    {
                        "faction": "Scaldra",
                        "missionType": "Assassination",
                        "deviation": {
                            "key": "TankStrongArmor",
                            "name": "Thermian Plating",
                        },
                        "risks": [
                            {
                                "key": "RegeneratingEnemies",
                                "name": "Hostile Regeneration",
                            },
                            {
                                "key": "PointBlank",
                                "name": "Myopic Munitions",
                            },
                        ],
                    },
                ],
                "personalModifiers": [
                    {"name": "Transference Distortion"},
                    {"name": "Undersupplied"},
                ],
            }
        ]
    }

    async def fake_worldstate(**_kwargs):
        return payload

    monkeypatch.setattr(client, "_get_worldstate", fake_worldstate)

    result = await client.fetch_archimedeas(platform="pc", language="zh")

    assert len(result) == 1
    assert result[0].kind == "时光科研"
    assert result[0].missions[0].mission_type == "传承收割"
    assert result[0].missions[0].faction == "炽蛇军"
    assert [
        (mission.deviation, mission.risks) for mission in result[0].missions
    ] == [
        ("爆发能量", ("炽蛇军竞速", "气球嘉年华")),
        ("阿尔法传承种", ("腐朽之躯", "它是活的")),
        ("装甲护板", ("敌军再生", "短视弹药")),
    ]
    assert result[0].personal_modifiers == (
        "Transference Distortion",
        "Undersupplied",
    )
