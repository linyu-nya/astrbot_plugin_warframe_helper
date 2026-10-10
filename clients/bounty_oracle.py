"""Current non-landscape bounties from browse.wf's published rotation feed."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re


_BASE = "https://raw.githubusercontent.com/calamity-inc/warframe-public-export-plus/senpai/"
_LEVELS = {
    "ZarimanSyndicate": ((50, 55), (60, 65), (70, 75), (90, 95), (110, 115)),
    "EntratiLabSyndicate": ((55, 60), (65, 70), (75, 80), (95, 100), (115, 120)),
    "HexSyndicate": ((65, 70), (75, 80), (85, 90), (95, 100), (105, 110), (115, 120), (125, 130)),
}
_NAMES = {"ZarimanSyndicate": "扎里曼坚守者", "EntratiLabSyndicate": "科维兽", "HexSyndicate": "六人组"}
_HEX_ANTIVIRUS_NODES = {"SolNode850", "SolNode853", "SolNode854", "SolNode856"}


def _localized(dictionary, key):
    text = dictionary.get(key) if isinstance(dictionary, dict) else None
    if not isinstance(text, str) or not text.strip() or text.startswith("<"):
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


async def fetch_oracle_bounties(client, *, platform="pc", language="zh"):
    from .worldstate_client import SyndicateInfo, SyndicateJob, _format_eta_from_dt, _parse_any_datetime

    if platform != "pc":
        return []
    payload = client._cache_get("oracle:bounty-cycle")
    if payload is None:
        payload = await client._fetch_json_resilient(["https://oracle.browse.wf/bounty-cycle"])
        if not isinstance(payload, dict):
            payload = {"expiry": 0}
        client._cache_put("oracle:bounty-cycle", payload)
    if not isinstance(payload, dict):
        return []
    expiry = _parse_any_datetime(payload.get("expiry"))
    if expiry is None or expiry <= datetime.now(timezone.utc):
        return []
    bounty_map = payload.get("bounties")
    if not isinstance(bounty_map, dict):
        return []

    static = getattr(client, "_oracle_static", None)
    if static is None:
        regions, challenges, dictionary = await asyncio.gather(*(
            client._fetch_json_resilient([_BASE + filename])
            for filename in ("ExportRegions.json", "ExportChallenges.json", "dict.zh.json")
        ))
        if not all(isinstance(x, dict) for x in (regions, challenges, dictionary)):
            return []
        static = (regions, challenges, dictionary)
        client._oracle_static = static
    regions, challenges, dictionary = static
    eta = _format_eta_from_dt(expiry)
    faction = client._faction_name_cn(payload.get("zarimanFaction")) or ""
    boards = []
    for tag, levels in _LEVELS.items():
        raw_jobs = bounty_map.get(tag)
        if not isinstance(raw_jobs, list) or len(raw_jobs) != len(levels):
            continue
        jobs = []
        for index, (raw, (minimum, maximum)) in enumerate(zip(raw_jobs, levels, strict=True), 1):
            if not isinstance(raw, dict):
                continue
            node = raw.get("node")
            region = regions.get(node)
            if not isinstance(region, dict):
                continue
            task_code = region.get("missionType")
            if not isinstance(task_code, str) or not task_code:
                continue
            mission = _localized(dictionary, region.get("missionName")) or client._mission_type_cn(task_code)
            place = _localized(dictionary, region.get("name")) or str(node)
            challenge = challenges.get(raw.get("challenge"), {})
            detail = _localized(dictionary, challenge.get("description")) if isinstance(challenge, dict) else ""
            if detail:
                detail = detail.splitlines()[-1].replace("|COUNT|", str(challenge.get("requiredCount", "")))
            ally = raw.get("ally")
            ally_name = str(ally).rsplit("/", 1)[-1].removesuffix("AllyAgent") if ally else ""
            if ally_name:
                detail = f"{ally_name} · {detail}" if detail else ally_name
            jobs.append(SyndicateJob(
                node=f"{minimum}-{maximum}级", mission_type="赏金", eta=eta,
                title=f"{place} · {mission}" if node not in _HEX_ANTIVIRUS_NODES else place,
                faction=faction if tag == "ZarimanSyndicate" else "",
                min_level=minimum, max_level=maximum, tier=index,
                task_type=client._mission_type_cn(task_code),
                objective=detail, job_id=f"{node}:{raw.get('challenge', '')}",
                reward_table=f"browse.wf:tier:{index}",
            ))
        if len(jobs) == len(levels):
            boards.append(SyndicateInfo(name=_NAMES[tag], eta=eta, jobs=tuple(jobs), tag=tag, expiry_utc=expiry))
    return boards
