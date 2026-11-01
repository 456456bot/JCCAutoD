import hashlib
import os
import re
from pathlib import Path

from .seasons import SEASON_NAMES, canonical_season_id, normalize_catalog, season_label
from .storage import DATA, read_json, write_json


class PortraitCatalog:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("JCC_PORTRAIT_DIR") or DATA)
        self.path = self.root / "catalog.json"
        self.data = (
            read_json(self.path)
            if self.path.exists()
            else dict(schema="jcc.portraits", version=1, seasons={})
        )
        if (
            self.data.get("schema") != "jcc.portraits"
            or self.data.get("version") != 1
            or not isinstance(self.data.get("seasons"), dict)
        ):
            raise ValueError("头像目录 JSON 格式错误")
        normalize_catalog(self.data)
        if not self.path.exists():
            for number in SEASON_NAMES:
                self.season(f"s{number}")

    def save(self):
        write_json(self.path, self.data)

    def season(self, season_id, label=None):
        season_id = canonical_season_id(season_id)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", season_id):
            raise ValueError("赛季 ID 只能使用字母、数字、下划线和短横线")
        return self.data["seasons"].setdefault(
            season_id, dict(name=season_label(season_id, label), champions=[])
        )

    def champions(self, season_id):
        return self.data["seasons"].get(canonical_season_id(season_id), {}).get("champions", [])

    def image_path(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("头像文件路径超出目录")
        return path

    def register(self, season_id, name, image, champion_id=None, source="manual", cost=None):
        name = name.strip()
        if not name:
            raise ValueError("棋子名称不能为空")
        season = self.season(season_id)
        cid = champion_id or "manual_" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
        champion = next(
            (
                c
                for c in season["champions"]
                if c["id"] == cid or (source == "manual" and c["name"] == name)
            ),
            None,
        )
        if champion is None:
            champion = dict(id=cid, name=name, portraits=[], source=source, cost=cost)
            season["champions"].append(champion)
        image = image.convert("RGB")
        digest = hashlib.sha256(image.tobytes()).hexdigest()[:24]
        relative = f"images/{digest}.png"
        path = self.image_path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            image.save(path)
        if relative not in champion["portraits"]:
            champion["portraits"].append(relative)
        return champion

    def coverage(self, season_id):
        champions = self.champions(season_id)
        ready = sum(
            any(self.image_path(p).exists() for p in c.get("portraits", [])) for c in champions
        )
        return dict(total=len(champions), ready=ready, missing=len(champions) - ready)
