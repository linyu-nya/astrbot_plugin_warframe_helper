"""Conservative bounty selection: never infer a tier from list order."""
from datetime import datetime, timezone

from .bounty_regions import region_for


def eligible_bounties(boards):
    groups = {}
    for board in boards:
        region = region_for(board.tag) or region_for(board.name)
        if not region or region[0] not in {"扎里曼", "圣所", "1999"}:
            continue
        if not board.expiry_utc or board.expiry_utc <= datetime.now(timezone.utc):
            continue
        jobs = [j for j in board.jobs if j.mission_type == "赏金"]
        # Duplicated official/aggregate boards describe the same rotation.
        key = (region[0], board.expiry_utc)
        score = sum(bool(j.task_type) and j.max_level is not None for j in jobs)
        score += sum(bool(getattr(j, "objective", "")) for j in jobs)
        if key not in groups or score > groups[key][2]:
            groups[key] = (board, jobs, score)
    selected = []
    for (name, _), (board, jobs, _) in groups.items():
        levels = [(j.max_level, j.min_level) for j in jobs if type(j.max_level) is int and type(j.min_level) is int]
        highest = max(levels) if levels else None
        if name != "1999" and len(levels) != len(jobs):
            continue
        for job in jobs:
            if job.task_type.casefold().strip() not in {"歼灭", "exterminate", "extermination", "mt_exterminate", "mt_extermination"}:
                continue
            if name == "1999":
                reward_text = " ".join((job.reward_table, *job.reward_pool, job.title)).casefold()
                if job.tier != 6 or not (job.reward_table or job.reward_pool):
                    continue
                excluded = ("antivirus", "anti-virus", "杀毒", "防病毒", "字节卫士", "蠕虫驱逐", "木马追缉", "持续清理", "驱动除尘", "软件安全", "防毒先锋", "电脑巡警")
                if any(word in reward_text for word in excluded):
                    continue
            elif highest is None or (job.max_level, job.min_level) != highest:
                continue
            selected.append((name, board, job))
    return selected
