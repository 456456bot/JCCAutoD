"""Season-organized profile storage and discovery for both applications."""

import re
from dataclasses import dataclass
from pathlib import Path

from .seasons import canonical_season_id
from .storage import PROFILES, load_profile, validate_profile


def season_title(season_id):
    sid = canonical_season_id(season_id)
    return sid.upper() if re.fullmatch(r"s\d+", sid) else sid


def profile_path(profile, root=None):
    profile = validate_profile(profile)
    sid = profile["season_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", sid):
        raise ValueError("赛季 ID 不能用于目录名称")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", profile["name"]).strip(" .")[:80].rstrip(" .")
    if not name:
        raise ValueError("阵容名称不能用作文件名")
    return Path(root or PROFILES) / season_title(sid) / f"{sid}_{name}.json"


@dataclass(frozen=True)
class ProfileEntry:
    season_id: str
    name: str
    path: Path


def scan_profiles(root=None):
    root = Path(root or PROFILES)
    entries = {}
    errors = []
    for path in sorted(root.glob("*.json")) + sorted(root.glob("*/*.json")):
        try:
            profile = load_profile(path)
            entry = ProfileEntry(profile["season_id"], profile["name"], path)
            entries[(entry.season_id, entry.name)] = entry
        except (ValueError, OSError, KeyError) as exc:
            errors.append((path, str(exc)))
    return sorted(entries.values(), key=lambda e: (e.season_id, e.name)), errors
