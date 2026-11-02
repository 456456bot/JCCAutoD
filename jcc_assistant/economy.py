"""Read small currency/price regions from the same Android shop frame."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import ImageOps


class EconomyReadError(ValueError):
    """A retryable numeric OCR failure, never permission to guess a cost."""


def numeric_value(text, score, key):
    text = text.strip()
    if not re.fullmatch(r"[0-9]{1,4}", text) or not np.isfinite(score) or score < 0.98:
        return None
    value = int(text)
    return value if key != "refresh" or value in (0, 1, 2) else None


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
    if (
        result.txts is None
        or result.scores is None
        or len(result.txts) != len(keys)
        or len(result.scores) != len(keys)
    ):
        raise EconomyReadError("金币或刷新费用未识别")
    values = {}
    for key, txt, score in zip(keys, result.txts, result.scores):
        value = numeric_value(txt, score, key)
        if value is None:
            region = regions[key].convert("RGB")
            # Native tiny crops often include borders and excessive vertical padding.
            w, h = region.size
            tight = region.crop((0, round(h * 0.12), w, round(h * 0.9)))
            variants = [
                tight.resize((w * 3, tight.height * 3)),
                ImageOps.autocontrast(tight.convert("L")).convert("RGB"),
            ]
            retry = engine.recognize_txt([np.asarray(p)[:, :, ::-1].copy() for p in variants])
            candidates = [
                numeric_value(t, s, key) for t, s in zip(retry.txts or (), retry.scores or ())
            ]
            valid = {v for v in candidates if v is not None}
            if len(valid) == 1:
                value = valid.pop()
            else:
                folder = Path("artifacts/diagnostics/economy")
                folder.mkdir(parents=True, exist_ok=True)
                region.save(folder / f"{key}.png")
                (folder / f"{key}.json").write_text(
                    json.dumps(
                        {
                            "time": datetime.now().isoformat(),
                            "key": key,
                            "text": str(txt),
                            "confidence": float(score),
                            "retry_texts": list(retry.txts or ()),
                            "retry_scores": [float(s) for s in (retry.scores or ())],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                raise EconomyReadError(f"{key} 数字识别不确定（读到 {txt!r}，置信度 {score:.1%}）")
        values[key] = value
    prices = {slot: values[f"price_{slot}"] for slot in set(price_slots)}
    return Economy(values["gold"], values["refresh"], prices)
