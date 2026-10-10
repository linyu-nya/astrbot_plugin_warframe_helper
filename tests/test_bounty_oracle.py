from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_oracle_provides_current_localized_tasks_and_excludes_antivirus(worldstate_module, monkeypatch):
    from astrbot_plugin_warframe_helper.clients.bounty_oracle import fetch_oracle_bounties
    from astrbot_plugin_warframe_helper.utils.bounty_push import eligible_bounties

    client = worldstate_module.WarframeWorldstateClient()
    expires = int((datetime.now(timezone.utc) + timedelta(minutes=25)).timestamp() * 1000)
    calls = []
    names = ("ZarimanSyndicate", "EntratiLabSyndicate", "HexSyndicate")
    nodes = {name: [f"{name}-{i}" for i in range(7 if name == "HexSyndicate" else 5)] for name in names}
    cycle = {"expiry": expires, "zarimanFaction": "FC_GRINEER",
             "bounties": {name: [{"node": node, "challenge": "/Challenge"} for node in row]
                          for name, row in nodes.items()}}
    regions = {node: {"name": "/Node", "missionName": "/Mission", "missionType":
                "MT_EXTERMINATION" if i == 4 or (name == "HexSyndicate" and i in (5, 6)) else "MT_DEFENSE"}
               for name, row in nodes.items() for i, node in enumerate(row)}
    languages = {"/Node": "测试节点", "/Mission": "歼灭", "/Description": "击杀 |COUNT| 个敌人"}
    challenges = {"/Challenge": {"description": "/Description", "requiredCount": 50}}

    async def fetch(urls):
        calls.append(urls)
        url = urls[0]
        if url.endswith("bounty-cycle"):
            return cycle
        if url.endswith("ExportRegions.json"):
            return regions
        if url.endswith("ExportChallenges.json"):
            return challenges
        if url.endswith("dict.zh.json"):
            return languages
        raise AssertionError(url)

    monkeypatch.setattr(client, "_fetch_json_resilient", fetch)
    boards = await fetch_oracle_bounties(client)
    assert len(boards) == 3
    assert boards[0].jobs[-1].title == "测试节点 · 歼灭"
    assert boards[0].jobs[-1].objective == "击杀 50 个敌人"
    assert boards[1].jobs[-1].max_level == 120
    assert boards[2].jobs[5].tier == 6
    assert boards[2].jobs[6].tier == 7
    pushed = eligible_bounties(boards)
    assert [name for name, _, _ in pushed] == ["扎里曼", "圣所", "1999"]
    assert pushed[-1][2].tier == 6
    await fetch_oracle_bounties(client)
    assert len(calls) == 4  # rotation and three static dictionaries are cached


@pytest.mark.asyncio
async def test_expired_or_partial_oracle_data_never_pushes(worldstate_module, monkeypatch):
    from astrbot_plugin_warframe_helper.clients.bounty_oracle import fetch_oracle_bounties
    client = worldstate_module.WarframeWorldstateClient()
    async def fetch(urls):
        return {"expiry": 1000, "bounties": {"HexSyndicate": [{"node": "SolNode1"}]}}
    monkeypatch.setattr(client, "_fetch_json_resilient", fetch)
    assert await fetch_oracle_bounties(client) == []
