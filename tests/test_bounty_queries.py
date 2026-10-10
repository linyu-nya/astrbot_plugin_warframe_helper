from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot_plugin_warframe_helper.utils.bounty_regions import region_for


class Localization:
    async def get_syndicate_tag_map(self, **kwargs):
        return {}

    async def translate_unique_name_loose(self, name, **kwargs):
        return {"/Jobs/Test": "夺回补给"}.get(name, name)

    async def translate_region(self, name, **kwargs):
        return name


@pytest.mark.asyncio
async def test_official_jobs_preserve_title_levels_vault_and_all_rows(worldstate_module, monkeypatch):
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = Localization()

    async def state(**kwargs):
        return {"SyndicateMissions": [{"Tag": "EntratiSyndicate", "Expiry": "2099-01-01T00:00:00Z",
            "Jobs": [{"jobType": "/Jobs/Test", "minEnemyLevel": 5, "maxEnemyLevel": 15,
                      "xpAmounts": [5, 5, 5]}] * 20 + [{"isVault": True}]}]}

    monkeypatch.setattr(client, "_get_worldstate", state)
    result = await client.fetch_syndicates()
    assert len(result[0].jobs) == 21
    assert result[0].tag == "EntratiSyndicate"
    assert result[0].jobs[0].title == "夺回补给"
    assert result[0].jobs[0].node == "5-15级"
    assert result[0].jobs[-1].title == "隔离库"


@pytest.mark.asyncio
async def test_official_job_ids_are_rendered_as_chinese_task_type(worldstate_module, monkeypatch):
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = Localization()
    async def state(**kwargs):
        return {"SyndicateMissions": [{"Tag": "CetusSyndicate", "Expiry": "2099-01-01T00:00:00Z",
            "Jobs": [{"jobType": "/Lotus/Jobs/AttritionBountyCap", "minEnemyLevel": 5,
                      "maxEnemyLevel": 15, "xpAmounts": [360, 360, 360]}]}]}
    monkeypatch.setattr(client, "_get_worldstate", state)
    result = await client.fetch_syndicates()
    assert result[0].jobs[0].title == "捕获"


@pytest.mark.asyncio
async def test_seed_only_regions_are_supplemented_and_expired_rows_filtered(worldstate_module, monkeypatch):
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = Localization()
    calls = []

    async def state(**kwargs):
        return {"SyndicateMissions": [{"Tag": "ZarimanSyndicate", "Seed": 42}]}

    async def fetch(urls):
        calls.append(urls)
        return [{"syndicate": "The Holdfasts", "expiry": "2099-01-01T00:00:00Z",
                 "jobs": [{"type": "Exterminate", "enemyLevels": [50, 55], "enemy": "Grineer", "standingStages": [3000]}]},
                {"syndicate": "The Hex", "expiry": "2000-01-01T00:00:00Z", "jobs": [{"type": "Old"}]}]

    monkeypatch.setattr(client, "_get_worldstate", state)
    monkeypatch.setattr(client, "_fetch_json_resilient", fetch)
    result = await client.fetch_syndicates()
    assert len(result) == 2
    assert result[1].jobs[0].faction == "Grineer"
    assert result[1].jobs[0].node == "50-55级"
    await client.fetch_syndicates()
    assert len(calls) == 2  # aggregate + one oracle attempt; both are cached


def test_region_matching_keeps_deimos_and_labs_separate():
    assert region_for("EntratiLabSyndicate")[0] == "圣所"
    assert region_for("EntratiSyndicate")[0] == "火卫二"
    assert region_for("六人组")[0] == "1999"
    assert region_for("未来集团") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["地球", "圣所", "1999", "新集团"])
async def test_command_selects_exact_region_and_preserves_all_jobs(query):
    # Execute the real command with rendering/network replaced by local fakes.
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "services/worldstate_commands.py").read_text(encoding="utf-8"))
    fn = next(x for x in tree.body if isinstance(x, ast.AsyncFunctionDef) and x.name == "cmd_bounties")
    captures = []

    async def render(**kwargs):
        captures.append(kwargs)
        return None

    async def fetch(**kwargs):
        job = SimpleNamespace(mission_type="赏金", node="50-55级", title="当前任务", faction="Corpus", standing=(), stages=None, eta="20分钟")
        return [SimpleNamespace(tag=tag, name=name, eta="20分钟", jobs=(job,) * 21)
                for tag, name in [("CetusSyndicate", "奥斯顿"), ("EntratiLabSyndicate", "科维兽"), ("HexSyndicate", "六人组"), ("NewSyndicate", "新集团")]]

    ns = {"__package__": "astrbot_plugin_warframe_helper.services", "AstrMessageEvent": object,
          "WarframeWorldstateClient": object, "split_tokens": str.split,
          "WORLDSTATE_PLATFORM_ALIASES": {"pc": "pc"}, "worldstate_platform_from_tokens": lambda _: "pc",
          "WorldstateRow": lambda **kwargs: kwargs, "render_worldstate_rows_image_to_file": render}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(root / "services/worldstate_commands.py"), "exec"), ns)
    result = await ns["cmd_bounties"](event=SimpleNamespace(plain_result=lambda s: s), raw_args=query, worldstate_client=SimpleNamespace(fetch_syndicates=fetch))
    assert len(captures[0]["rows"]) == 21
    assert "派系：Corpus" in result
    assert query + "赏金" in result
