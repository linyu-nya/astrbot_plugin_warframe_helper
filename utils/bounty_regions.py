"""Stable region aliases; unknown syndicate names remain queryable."""
REGIONS = (
    ("地球", ("地球", "夜灵平原", "希图斯", "奥斯顿", "earth", "cetus", "poe"),
     ("CetusSyndicate", "OstronsSyndicate", "Ostrons", "Ostron", "希图斯", "奥斯顿")),
    ("金星", ("金星", "金星平原", "奥布山谷", "福尔图娜", "索拉里斯", "venus", "vallis", "orb", "fortuna"),
     ("SolarisSyndicate", "Solaris United", "Solaris", "福尔图娜", "索拉里斯联合")),
    ("火卫二", ("火卫二", "魔胎之境", "魔胎", "英择谛", "deimos", "cambion", "entrati"),
     ("EntratiSyndicate", "Entrati", "英择谛")),
    ("扎里曼", ("扎里曼", "扎里曼号", "老家", "坚守者", "zariman", "holdfasts"),
     ("ZarimanSyndicate", "HoldfastSyndicate", "The Holdfasts", "Holdfasts", "坚守者", "扎里曼", "扎里曼坚守者")),
    ("圣所", ("圣所", "解剖圣所", "科维兽", "卡维亚", "cavia", "sanctum"),
     ("EntratiLabSyndicate", "CaviaSyndicate", "Cavia", "科维兽", "卡维亚")),
    ("1999", ("1999", "六人组", "霍尔瓦尼亚", "hex", "hollvania"),
     ("HexSyndicate", "The Hex", "Hex", "六人组")),
)


def key(value: str) -> str:
    return "".join(str(value or "").casefold().split())


def region_for(value: str):
    normalized = key(value)
    return next((region for region in REGIONS
                 if normalized in {key(x) for x in (region[0], *region[1], *region[2])}), None)
