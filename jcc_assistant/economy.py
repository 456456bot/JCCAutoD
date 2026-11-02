"""Read small currency/price regions from the same Android shop frame."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


class EconomyReadError(ValueError):
    """A retryable numeric OCR failure, never permission to guess a cost."""


def refresh_digit_crops(region):
    """Isolate the one white digit, excluding button glow and coin fragments."""
    pixels = np.asarray(region.convert("RGB")).astype(float)
    variants = []
    for threshold in (160, 200):
        mask = np.uint8(
            (pixels.min(axis=2) > threshold) & (pixels.max(axis=2) - pixels.min(axis=2) < 70)
        )
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        if count < 2:
            continue
        index = 1 + stats[1:, cv2.CC_STAT_AREA].argmax()
        x, y, w, h, area = stats[index]
        if h < region.height * 0.25 or area < 8 or area > mask.size * 0.65:
            continue
        digit = Image.fromarray(np.uint8(labels[y : y + h, x : x + w] != index) * 255)
        variants.append(ImageOps.expand(digit, border=4, fill=255).convert("RGB"))
    return variants


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
            if key == "refresh":
                variants.extend(refresh_digit_crops(region))
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
