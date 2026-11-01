"""Read small currency/price regions from the same Android shop frame."""

import re
from dataclasses import dataclass, field

import numpy as np


def economy_boxes(size):
    boxes = {"gold": (1026, 1196, 1130, 1248), "refresh": (197, 1450, 242, 1503)}
    boxes.update({f"price_{i + 1}": (675 + i * 300, 1464, 718 + i * 300, 1508) for i in range(5)})
    return {
        name: tuple(round(v * size[j % 2] / (2048, 1536)[j % 2]) for j, v in enumerate(box))
        for name, box in boxes.items()
    }


def refresh_point(size):
    return round(280 * size[0] / 2048), round(1450 * size[1] / 1536)


@dataclass(frozen=True)
class Economy:
    gold: int
    refresh_cost: int
    prices: dict = field(default_factory=dict)


def read_economy(engine, image, price_slots=()):
    regions = image.info.get("economy_regions")
    if regions is None:
        if image.info.get("origin"):
            raise ValueError("截图缺少金币区域，自动搜牌已停止")
        regions = {name: image.crop(box) for name, box in economy_boxes(image.size).items()}
    keys = ["gold", "refresh"] + [f"price_{slot}" for slot in sorted(set(price_slots))]
    crops = [np.asarray(regions[key].convert("RGB"))[:, :, ::-1].copy() for key in keys]
    result = engine.recognize_txt(crops)
    if result.txts is None or result.scores is None or len(result.txts) != len(keys):
        raise ValueError("金币或刷新费用未识别，自动搜牌已停止")
    values = {}
    for key, txt, score in zip(keys, result.txts, result.scores):
        text = txt.strip()
        if not re.fullmatch(r"[0-9]{1,4}", text) or not np.isfinite(score) or score < 0.98:
            raise ValueError(f"{key} 数字识别不确定，自动搜牌已停止")
        values[key] = int(text)
    if values["refresh"] not in (0, 1, 2):
        raise ValueError("刷新费用不在 0／1／2 范围内，自动搜牌已停止")
    prices = {slot: values[f"price_{slot}"] for slot in set(price_slots)}
    return Economy(values["gold"], values["refresh"], prices)
