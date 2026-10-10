from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from astrbot_plugin_warframe_helper.clients.weekly_activities import current_rotation, fetch_calendar, fetch_descent
from astrbot_plugin_warframe_helper.utils.bounty_push import eligible_bounties


def period(offset=0):
    now = datetime.now(timezone.utc)
    return {"Activation": (now + timedelta(days=offset, hours=-1)).isoformat(),
            "Expiry": (now + timedelta(days=offset, hours=1)).isoformat()}


def test_current_rotation_ignores_future_expired_and_missing_dates(worldstate_module):
    live = period()
    assert current_rotation([period(7), {}, live, period(-7)]) == live


@pytest.mark.asyncio
async def test_descent_selects_current_week_and_sorts_floors(worldstate_module):
    async def state(**kwargs):
        return {"Descents": [{**period(7), "Challenges": []}, {**period(), "Challenges": [
            {"Index": 21, "Type": "DT_PROTOFRAME", "Challenge": "Devil"},
            {"Index": 1, "Type": "DT_UNIQUE", "Challenge": "HorseCombatOnly"}]}]}
    report = await fetch_descent(SimpleNamespace(_get_worldstate=state))
    assert report.rows == (("第 01 层 · 特殊任务", "绝灵骥战斗"), ("第 21 层 · 战甲祈运", "罗瑟的遗忘"))


@pytest.mark.asyncio
async def test_calendar_uses_1999_day_of_year_and_all_choices(worldstate_module):
    async def state(**kwargs):
        return {"KnownCalendarSeasons": [{**period(), "Season": "CST_FALL", "Days": [
            {"day": 278, "events": [{"type": "CET_CHALLENGE", "challenge": "/Test"}]},
            {"day": 365, "events": [{"type": "CET_REWARD", "reward": "/Test"}]},
            {"day": 400, "events": [{"type": "CET_REWARD", "reward": "/Test"}]}]}]}
    client = SimpleNamespace(_get_worldstate=state, _calendar_localization=({}, {}, {"/Test": {"value": "测试", "desc": "任务说明"}}))
    report = await fetch_calendar(client)
    assert report.rows[0] == ("1999-10-05", "待办事项 · 测试：任务说明")
    assert report.rows[1][0] == "1999-12-31"
    assert len(report.rows) == 2


@pytest.mark.asyncio
async def test_calendar_prefers_game_chinese_and_removes_internal_markup(worldstate_module):
    async def state(**kwargs):
        return {"KnownCalendarSeasons": [{**period(), "Season": "CST_WINTER", "Days": [
            {"day": 13, "events": [
                {"type": "CET_CHALLENGE", "challenge": "/TestChallenge"},
                {"type": "CET_REWARD", "reward": "/Lotus/StoreItems/Types/Recipes/Components/OrokinReactorBlueprint"},
            ]}]}]}

    client = SimpleNamespace(_get_worldstate=state, _calendar_localization=(
        {"/Name": "逝去卓越者", "/Description": "击杀 |COUNT| 名卓越者"},
        {"/TestChallenge": {"name": "/Name", "description": "/Description", "requiredCount": 10}},
        {},
    ))
    report = await fetch_calendar(client)
    assert report.title == "1999 日历 · 冬季"
    assert report.rows == (("1999-01-13", "待办事项 · 逝去卓越者：击杀 10 名卓越者\n奖励选项 · 奥罗金反应堆蓝图"),)


def job(level, kind="歼灭", tier=None, reward=""):
    return SimpleNamespace(mission_type="赏金", max_level=level, min_level=level - 5 if level else None,
                           task_type=kind, tier=tier, reward_table=reward, reward_pool=(), title="任务")


def board(name, jobs):
    return SimpleNamespace(tag=name, name=name, jobs=jobs, expiry_utc=datetime.now(timezone.utc) + timedelta(hours=1))


def test_push_does_not_pick_lower_exterminate_when_highest_is_other_mission():
    assert eligible_bounties([board("ZarimanSyndicate", [job(60), job(115, "生存")])]) == []
    high = job(115)
    result = eligible_bounties([board("EntratiLabSyndicate", [job(60), high])])
    assert len(result) == 1 and result[0][2] is high


def test_hex_uses_tier_not_list_index_and_excludes_antivirus():
    wanted = job(95, tier=6, reward="/Hex/TierFTableARewards")
    result = eligible_bounties([board("HexSyndicate", [
        job(100, tier=7, reward="/Antivirus"), wanted,
        job(100, tier=6, reward="/Antivirus"), job(95), job(95, tier=6)])])
    assert [item[2] for item in result] == [wanted]


def test_push_skips_expired_and_missing_levels():
    stale = board("ZarimanSyndicate", [job(115)])
    stale.expiry_utc = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert eligible_bounties([stale, board("EntratiLabSyndicate", [job(None)])]) == []


@pytest.mark.asyncio
async def test_circuit_accepts_official_schedule_array(worldstate_module, monkeypatch):
    client = worldstate_module.WarframeWorldstateClient()
    async def state(**kwargs):
        return {"EndlessXpSchedule": [{**period(7), "CategoryChoices": []}, {**period(), "CategoryChoices": [
            {"Category": "EXC_NORMAL", "Choices": ["Ember"]},
            {"Category": "EXC_HARD", "Choices": ["Bo", "Latron"]}]}]}
    monkeypatch.setattr(client, "_get_worldstate", state)
    result = await client.fetch_duviri_circuit_rewards(language="en")
    assert result.normal_choices == ("Ember",)
    assert result.steel_choices == ("Bo", "Latron")
