"""Stable season IDs and concise display names."""

import copy

SEASON_NAMES = dict(
    enumerate(
        [
            "时空裂痕",
            "元素崛起",
            "银河战争",
            "命运之轮",
            "光明与黑暗",
            "双城之战",
            "巨龙之巢",
            "怪兽入侵",
            "符文大陆传奇",
            "强音争霸",
            "画之灵",
            "魔法乱斗",
            "双城传说II",
            "赛博之城",
            "天下无双格斗大会",
            "海克斯典籍",
            "星神",
            "自然之力",
        ],
        1,
    )
)


def canonical_season_id(season_id):
    return "s16" if season_id == "s16_5" else season_id


def season_label(season_id, fallback=None):
    sid = canonical_season_id(season_id)
    number = int(sid[1:]) if sid.startswith("s") and sid[1:].isdigit() else None
    return f"S{number}-{SEASON_NAMES[number]}" if number in SEASON_NAMES else (fallback or sid)


def normalize_catalog(data):
    """Merge legacy half-season data without discarding manual portraits."""
    seasons = data["seasons"]
    legacy = seasons.pop("s16_5", None)
    if legacy:
        base = seasons.setdefault("s16", dict(name="", champions=[]))
        for key, value in legacy.items():
            if key not in ("name", "champions"):
                base.setdefault(key, copy.deepcopy(value))
        for champion in legacy.get("champions", []):
            existing = next((c for c in base["champions"] if c["id"] == champion["id"]), None)
            if existing is None:
                existing = next(
                    (c for c in base["champions"] if c["name"] == champion["name"]), None
                )
            if existing is None:
                base["champions"].append(copy.deepcopy(champion))
            else:
                existing["portraits"] = list(
                    dict.fromkeys(existing.get("portraits", []) + champion.get("portraits", []))
                )
                for key, value in champion.items():
                    existing.setdefault(key, copy.deepcopy(value))
    for sid, season in seasons.items():
        season["name"] = season_label(sid, season.get("name"))
