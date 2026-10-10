"""Read time-bounded official rotations without guessing from array position."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import re


@dataclass(frozen=True)
class ActivityReport:
    title: str
    eta: str
    rows: tuple[tuple[str, str], ...]


def current_rotation(rows, now=None):
    from .worldstate_client import _parse_any_datetime
    now = now or datetime.now(timezone.utc)
    if isinstance(rows, dict):
        rows = [rows]
    candidates = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        start = _parse_any_datetime(row.get("Activation") or row.get("activation"))
        end = _parse_any_datetime(row.get("Expiry") or row.get("expiry"))
        if start and end and start <= now < end:
            candidates.append((start, row))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


DESCENT_TYPES = {
    "DT_UNIQUE": "特殊任务", "DT_EXTERMINATE": "歼灭", "DT_LOOT_CREATURES": "贪囤断肢劫掠",
    "DT_NETRACELLS": "消灭目标", "DT_ALCHEMY": "元素转换", "DT_BOSS": "刺杀",
    "DT_PROTOFRAME": "战甲祈运", "DT_SABOTAGE_HIVE": "清巢", "DT_INFESTED_SALVAGE": "净化",
    "DT_SABOTAGE_DEFENSE": "移动防御", "DT_PRESURE_GAUGE": "压力锅", "DT_MIMICS": "掠夺轮盘",
    "DT_DEFENSE": "防御", "DT_EXCAVATION": "挖掘", "DT_SHRINE_DEFENSE": "祈运坛防御",
    "DT_CAPTURE": "捕获", "DT_INTERCEPTION": "拦截", "DT_RACE": "竞速", "DT_COLLECTION": "收集",
    "DT_BREAK_TARGETS": "摧毁目标", "DT_LOOT": "搜集物资",
}
# Names verified against the supplied in-game reference. Unknown modifiers retain IDs.
DESCENT_DETAILS = {
    "HorseCombatOnly": "绝灵骥战斗", "VeryToxic": "毒蛭吸血卓越者军团",
    "BasicLootCreatures": "贪囤断肢劫掠", "FireAndIce": "冰火卓越者军团",
    "HardShell": "冰封卓越者军团", "ArchonBoreal": "执刑官诡文枭主",
    "Wisp": "玛丽的圣所", "GiantRealm": "巨人症", "Sentients": "Tau 的复仇",
    "HordeWeakpoints": "弱点敌群", "ShockingLeech": "电击吸血卓越者军团",
    "BasicMimics": "掠夺轮盘", "Harrow": "里昂的圣所", "HeadShotsOnly": "只有弱点才会受到伤害",
    "JadeGuardian": "翠玉卓越者军团", "UnseenFoes": "潜在威胁",
    "PowerHouse": "力量贪婪卓越者军团", "FieryTrail": "防火道", "SpicyKnife": "拆弹",
    "Devil": "罗瑟的遗忘",
}


async def fetch_descent(client, *, platform="pc", language="zh"):
    from .worldstate_client import _format_eta_from_dt, _parse_any_datetime
    ws = await client._get_worldstate(platform=platform, language=language)
    row = current_rotation(ws.get("Descents")) if isinstance(ws, dict) else None
    if not row:
        return None
    challenges = row.get("Challenges", [])
    entries = []
    valid = [x for x in challenges if isinstance(x, dict) and type(x.get("Index")) is int]
    for floor in sorted(valid, key=lambda x: x["Index"]):
        kind = str(floor.get("Type") or "未知任务")
        detail = str(floor.get("Challenge") or "详情未提供")
        entries.append((f"第 {floor['Index']:02d} 层 · {DESCENT_TYPES.get(kind, kind)}", DESCENT_DETAILS.get(detail, detail)))
    return ActivityReport("沉沦之地", _format_eta_from_dt(_parse_any_datetime(row.get("Expiry"))), tuple(entries))


async def fetch_calendar(client, *, platform="pc", language="zh"):
    from .worldstate_client import _format_eta_from_dt, _parse_any_datetime
    ws = await client._get_worldstate(platform=platform, language=language)
    row = current_rotation(ws.get("KnownCalendarSeasons")) if isinstance(ws, dict) else None
    if not row:
        return None
    localization = getattr(client, "_calendar_localization", None)
    if localization is None:
        base = "https://raw.githubusercontent.com/calamity-inc/warframe-public-export-plus/senpai/"
        dictionary, challenges, older = await asyncio.gather(*(
            client._fetch_json_resilient([url]) for url in (
                base + "dict.zh.json", base + "ExportChallenges.json",
                "https://raw.githubusercontent.com/WFCD/warframe-worldstate-data/master/data/zh/languages.json",
            )
        ))
        localization = tuple(x if isinstance(x, dict) else {} for x in (dictionary, challenges, older))
        if any(localization):
            client._calendar_localization = localization
    dictionary, challenges, older = localization

    known_rewards = {
        "OrokinReactorBlueprint": "奥罗金反应堆蓝图",
        "OrokinCatalystBlueprint": "奥罗金催化剂蓝图",
        "ArchonCrystalViolet": "紫晶执刑官源力石",
        "WeaponUtilityUnlockerBlueprint": "武器特殊功能槽连接器蓝图",
    }
    known_upgrades = {
        "PowerStrengthAndEfficiencyPerEnergySpent": "力量飙升",
        "EnergyRestoration": "特浓咖啡",
        "RadiationProcOnTakeDamage": "瓶装闪电",
        "HealingEffects": "应急特效药",
        "ElectricStatusDamageAndChance": "瓶装闪电",
    }

    def readable(text):
        text = re.sub(r"<[^>]+>", "", str(text or "")).strip()
        text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text.replace("_", " "))
        return text

    async def describe(path, kind):
        key = path.rsplit("/", 1)[-1]
        old = older.get(path, {})
        entry = challenges.get(path, {}) if kind == "CET_CHALLENGE" else {}
        if isinstance(entry, dict):
            name, desc = dictionary.get(entry.get("name")), dictionary.get(entry.get("description"))
            if isinstance(name, str) and name and isinstance(desc, str) and desc:
                desc = desc.splitlines()[-1].replace("|COUNT|", str(entry.get("requiredCount", "")))
                return f"{readable(name)}：{readable(desc)}"
        if kind == "CET_REWARD" and key in known_rewards:
            return known_rewards[key]
        if kind == "CET_UPGRADE" and key in known_upgrades:
            label = known_upgrades[key]
            if isinstance(old, dict) and old.get("desc"):
                return f"{label}：{readable(old['desc'])}"
            return label
        if isinstance(old, dict) and old.get("value"):
            return "：".join(readable(x) for x in (old.get("value"), old.get("desc")) if x)
        mapped = await client._public_export.translate_unique_name_loose(path, language=language)
        if isinstance(mapped, str) and mapped and mapped != path:
            return readable(mapped)
        return readable(key)

    entries = []
    days = row.get("Days", [])
    for day in sorted((d for d in days if isinstance(d, dict) and type(d.get("day")) is int), key=lambda d: d["day"]):
        if not 1 <= day["day"] <= 365:
            continue
        date = (datetime(1999, 1, 1) + timedelta(days=day["day"] - 1)).strftime("%Y-%m-%d")
        events = day.get("events", [])
        details = []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            field, label = {"CET_CHALLENGE": ("challenge", "待办事项"), "CET_REWARD": ("reward", "奖励选项"), "CET_UPGRADE": ("upgrade", "覆写选项"), "CET_PLOT": ("dialogueName", "剧情")}.get(kind, ("", str(kind or "事件")))
            path = event.get(field)
            if isinstance(path, str) and path:
                details.append(f"{label} · {await describe(path, kind)}")
        if details:
            entries.append((date, "\n".join(details)))
    season = {"CST_SPRING": "春季", "CST_SUMMER": "夏季", "CST_FALL": "秋季", "CST_WINTER": "冬季"}.get(row.get("Season"), "当前季节")
    return ActivityReport(f"1999 日历 · {season}", _format_eta_from_dt(_parse_any_datetime(row.get("Expiry"))), tuple(entries))
