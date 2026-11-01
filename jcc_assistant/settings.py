"""Target name persistence. Versions 1/2 migrate without quantity limits."""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def validate_targets(targets):
    if not isinstance(targets, (list, tuple, dict)):
        raise ValueError("目标配置必须为名称列表")
    result = []
    for name in targets:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("目标卡名不能为空")
        name = name.strip()
        if name in result:
            raise ValueError("目标卡名不能重复")
        result.append(name)
    return result


def save_config(targets, path=CONFIG_PATH, stop_rules=None):
    names = validate_targets(targets)
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    data = dict(version=3, targets=names)
    if stop_rules is not None:
        data["stop_rules"] = validate_stop_rules(stop_rules, names)
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_config(path=CONFIG_PATH):
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version", 1)
    if version == 1:
        text = data["targets"]
        if not isinstance(text, str):
            raise ValueError("旧版配置格式错误")
        names = [
            part.replace("：", "=").replace(":", "=").split("=")[0].strip()
            for part in text.replace("，", ",").split(",")
            if part.strip()
        ]
    elif version == 2:
        names = [row["name"] for row in data["targets"]]
    elif version == 3:
        names = data["targets"]
        if not isinstance(names, list):
            raise ValueError("目标配置必须为名称列表")
    else:
        raise ValueError("不支持的配置版本")
    return validate_targets(names)


def validate_stop_rules(rules, names):
    if not isinstance(rules, dict) or any(
        type(rule) is not int or rule not in (0, 2, 3) for rule in rules.values()
    ):
        raise ValueError("停止条件格式错误")
    return {name: rules[name] for name in names if name in rules}


def load_stop_rules(names, path=CONFIG_PATH):
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return validate_stop_rules(data.get("stop_rules", {}), names)
