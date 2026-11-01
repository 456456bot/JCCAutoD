"""Small shop-star templates; these are hints, never proof of ownership."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "upgrade"
RULE_LABELS = {0: "持续购买", 2: "二星后移除", 3: "三星后移除"}


def hint_boxes(size):
    return [
        tuple(
            round(v * size[j % 2] / (2048, 1536)[j % 2])
            for j, v in enumerate((432 + i * 300, 1244, 550 + i * 300, 1344))
        )
        for i in range(5)
    ]


def color_mask(image, level):
    rgb = np.asarray(image.convert("RGB")).astype(np.float32)
    r, g, b = rgb.transpose(2, 0, 1)
    if level == 3:
        mask = (r > 165) & (g > 115) & (b < g * 0.9) & (r > b * 1.25)
    else:
        mask = (rgb.min(axis=2) > 160) & (rgb.max(axis=2) - rgb.min(axis=2) < 65)
    return mask.astype(np.float32)


class UpgradeDetector:
    def __init__(self):
        # Coordinates belong to user-provided source images, not game coordinates.
        specs = [
            ("video_source.png", 2, (364, 78, 396, 96), 176),
            ("video_source.png", 3, (738, 72, 774, 99), 176),
            ("two_source.png", 2, (11, 2, 44, 22), 176),
            ("three_source.png", 3, (27, 10, 58, 40), 176),
        ]
        self.templates = []
        for filename, level, box, card_width in specs:
            with Image.open(ASSETS / filename) as source:
                patch = source.crop(box)
            for scale in (0.8, 0.9, 1.0, 1.1, 1.2):
                factor = 288 / card_width * scale
                resized = patch.resize(
                    (round(patch.width * factor), round(patch.height * factor)),
                    Image.Resampling.BILINEAR,
                )
                mask = color_mask(resized, level)
                if mask.std() > 0.05:
                    self.templates.append((level, mask))

    def classify(self, region):
        # Keep the aspect ratio: expanding the capture must not squash stars.
        region = region.resize(
            (118, round(region.height * 118 / region.width)), Image.Resampling.BILINEAR
        )
        masks = {level: color_mask(region, level) for level in (2, 3)}
        best = {2: 0.0, 3: 0.0}
        for level, template in self.templates:
            if template.shape[0] > region.height or template.shape[1] > region.width:
                continue
            result = cv2.matchTemplate(masks[level], template, cv2.TM_CCOEFF_NORMED)
            _, score, _, (x, y) = cv2.minMaxLoc(result)
            patch = masks[level][y : y + template.shape[0], x : x + template.shape[1]]
            # A gold border/glow can correlate with a star's bright pixels.
            # Require matching foreground AND background, not just correlation.
            foreground = template > 0.5
            overlap = np.count_nonzero((patch > 0.5) & foreground)
            union = np.count_nonzero((patch > 0.5) | foreground)
            if union and overlap / union >= 0.48:
                best[level] = max(best[level], float(score))
        level = max(best, key=best.get)
        return level if best[level] >= 0.72 else 0

    def detect(self, image):
        regions = image.info.get("upgrade_regions")
        if regions is None:
            # Offline/full-screen diagnostics only. Name strips alone contain no stars.
            if image.info.get("origin"):
                return [0] * 5
            regions = [image.crop(box) for box in hint_boxes(image.size)]
        return [self.classify(region) for region in regions]
