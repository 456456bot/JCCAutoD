"""Read stars in a static lineup plan, not on the live battlefield."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SOURCE = Path(__file__).resolve().parents[2] / "assets" / "lineup_stars" / "reference.png"


def rules_from_slots(rows):
    rules = {}
    for row in rows:
        if row.get("name"):
            rules[row["name"]] = max(rules.get(row["name"], 0), row.get("stop_rule", 0))
    return rules


def mask(image, gold=False):
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    r, g, b = rgb.transpose(2, 0, 1)
    if gold:
        return ((r > 170) & (g > 120) & (b < g * 0.8) & (r > b * 1.3)).astype(np.float32)
    return (
        (rgb.min(axis=2) > 105)
        & (b >= r * 0.95)
        & (g >= r * 0.95)
        & (rgb.max(axis=2) - rgb.min(axis=2) < 95)
    ).astype(np.float32)


class PlannerStarDetector:
    def __init__(self):
        self.templates = []
        with Image.open(SOURCE) as image:
            for level, box in [
                (3, (301, 61, 359, 86)),
                (2, (426, 61, 465, 86)),
                (1, (548, 61, 579, 86)),
                (1, (138, 366, 169, 395)),
                (1, (727, 367, 758, 396)),
                (1, (844, 367, 877, 396)),
            ]:
                patch = image.crop(box)
                for scale in (0.8, 0.9, 1.0, 1.1, 1.2):
                    sample = patch.resize(
                        (round(patch.width * scale), round(patch.height * scale)),
                        Image.Resampling.BILINEAR,
                    )
                    template = mask(sample, level == 3)
                    if template.std() > 0.05:
                        self.templates.append((level, template))

    def detect(self, image, box):
        left, top, right, bottom = box
        height = bottom - top
        if top < height * 0.15:
            return 0  # Stars cropped off: keep continuous instead of guessing.
        region = image.crop((left, round(top - height * 0.2), right, round(top + height * 0.28)))
        region = region.resize((86, 46), Image.Resampling.BILINEAR)
        masks = {True: mask(region, True), False: mask(region, False)}
        best = {1: 0.0, 2: 0.0, 3: 0.0}
        for level, template in self.templates:
            result = cv2.matchTemplate(masks[level == 3], template, cv2.TM_CCOEFF_NORMED)
            best[level] = max(best[level], float(result.max()))
        # Multi-star groups take precedence over matching one star inside a group.
        for level in (3, 2, 1):
            if best[level] >= 0.74:
                return level
        return 0
