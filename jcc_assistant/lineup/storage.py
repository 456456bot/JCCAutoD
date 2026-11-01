import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..settings import validate_stop_rules, validate_targets
from .seasons import canonical_season_id

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "portraits"
PROFILES = ROOT / "configurations"


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def make_profile(name, season_id, targets, slots=(), source="manual", stop_rules=None):
    if (
        not isinstance(name, str)
        or not name.strip()
        or not isinstance(season_id, str)
        or not season_id.strip()
    ):
        raise ValueError("阵容名称和赛季不能为空")
    names = validate_targets(targets)
    rules = validate_stop_rules(stop_rules if stop_rules is not None else {}, names)
    return dict(
        schema="jcc.lineup",
        version=1,
        id=uuid.uuid4().hex,
        name=name.strip(),
        season_id=canonical_season_id(season_id.strip()),
        targets=names,
        stop_rules={n: rules.get(n, 3) for n in names},
        slots=list(slots),
        source=source,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def validate_profile(data):
    if not isinstance(data, dict) or data.get("schema") != "jcc.lineup" or data.get("version") != 1:
        raise ValueError("不支持的阵容 JSON 格式或版本")
    if not all(
        isinstance(data.get(key), str) and data[key].strip() for key in ("name", "season_id", "id")
    ):
        raise ValueError("阵容 JSON 缺少名称、赛季或 ID")
    result = dict(data)
    result["season_id"] = canonical_season_id(data["season_id"].strip())
    if not isinstance(data.get("targets"), list):
        raise ValueError("阵容目标必须为名称列表")
    result["targets"] = validate_targets(data.get("targets"))
    if "stop_rules" in data:
        result["stop_rules"] = validate_stop_rules(data["stop_rules"], result["targets"])
    if not isinstance(data.get("slots", []), list):
        raise ValueError("阵容位置数据必须为列表")
    for row in data.get("slots", []):
        if not isinstance(row, dict) or not isinstance(row.get("name", ""), str):
            raise ValueError("阵容位置条目格式错误")
        if row.get("included", True) and not row.get("name", "").strip():
            raise ValueError("仍有包含的未知头像，无法保存阵容")
    return result


def save_profile(path, data):
    data = validate_profile(data)
    path = Path(path)
    if path.exists():
        # Keep the last valid version when overwriting an existing profile.
        try:
            old = validate_profile(read_json(path))
        except (ValueError, KeyError):
            old = None
        if old:
            write_json(path.with_suffix(".json.bak"), old)
    write_json(path, data)


def load_profile(path):
    return validate_profile(read_json(path))
