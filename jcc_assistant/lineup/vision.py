from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass
class LineupSlot:
    index: int
    box: tuple
    name: str = ""
    score: float = 0.0
    margin: float = 0.0
    champion_id: str = ""
    included: bool = True


def _iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    return intersection / max(
        1, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    )


def calibrated_grid(image):
    """Known 4:3 MuMu planner layout, or an explicit crop-preserved calibration."""
    if image.info.get("lineup_grid"):
        return dict(image.info["lineup_grid"])
    if image.width >= 800 and abs(image.width / image.height - 4 / 3) < 0.015:
        sx, sy = image.width / 2048, image.height / 1536
        return dict(
            first_center=(284 * sx, 570 * sy),
            step=140 * sx,
            row_step=122 * sy,
            width=104 * sx,
            height=112 * sy,
            columns=7,
            rows=4,
        )
    return None


def crop_planner(image, box):
    cropped = image.crop(box)
    grid = calibrated_grid(image)
    if grid:
        grid["first_center"] = (grid["first_center"][0] - box[0], grid["first_center"][1] - box[1])
        cropped.info["lineup_grid"] = grid
    return cropped


def grid_from_cell(box):
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    if width < 20 or height < 20:
        raise ValueError("格子标定范围过小")
    return dict(
        first_center=((left + right) / 2, (top + bottom) / 2),
        step=width * 140 / 104,
        row_step=height * 122 / 112,
        width=width,
        height=height,
        columns=7,
        rows=4,
    )


def locate_grid(image):
    """Infer the seven-column planner grid from visible colored hexagons."""
    rgb = np.array(image.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    color = ((hsv[:, :, 1] > 65) & (hsv[:, :, 2] > 125)).astype("uint8") * 255
    color = cv2.morphologyEx(color, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    edges = cv2.Canny(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), 50, 130)
    candidates = []
    for mask in (color, edges):
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if not (
                35 <= w <= image.width * 0.95
                and 40 <= h <= image.height * 0.95
                and 0.7 < w / h < 1.05
                and area > w * h * 0.40
            ):
                continue
            if mask is edges:
                poly = cv2.approxPolyDP(contour, 0.035 * cv2.arcLength(contour, True), True)
                if not (5 <= len(poly) <= 8 and cv2.isContourConvex(poly)):
                    continue
            candidates.append((x, y, x + w, y + h))
    if not candidates:
        raise ValueError("未找到阵容网格，请使用“标定一个格子”框选第一行最左侧格子")
    # Prefer the largest repeated icon size, avoiding small trait icons.
    groups = {}
    for box in candidates:
        width = box[2] - box[0]
        groups.setdefault(round(width / 10), []).append(box)
    viable = [k for k, v in groups.items() if len(v) >= 3]
    if not viable:
        viable = list(groups)
    width_key = max(viable)
    group = [b for b in candidates if abs((b[2] - b[0]) - width_key * 10) <= 12]
    unique = []
    for box in sorted(group, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True):
        if not any(_iou(box, old) > 0.5 for old in unique):
            unique.append(box)
    width = float(np.median([b[2] - b[0] for b in unique]))
    height = float(np.median([b[3] - b[1] for b in unique]))
    bands = []
    for box in unique:
        cy = (box[1] + box[3]) / 2
        band = next(
            (v for v in bands if abs(np.mean([(b[1] + b[3]) / 2 for b in v]) - cy) < height * 0.35),
            None,
        )
        if band is None:
            bands.append([box])
        else:
            band.append(box)
    # Anchor to the top visible row, even when a lower row has more contours.
    row = min(bands, key=lambda band: np.mean([(b[1] + b[3]) / 2 for b in band]))
    cy = float(np.median([(b[1] + b[3]) / 2 for b in row]))
    centers = sorted((b[0] + b[2]) / 2 for b in row)
    differences = [
        b - a for a, b in zip(centers, centers[1:]) if width * 1.15 < b - a < width * 1.65
    ]
    step = float(np.median(differences)) if differences else width * 1.36
    first = centers[0]
    # Some light/locked borders fail contour extraction; recover occupied neighbors.
    for _ in range(6):
        previous = first - step
        box = tuple(
            round(v)
            for v in (previous - width / 2, cy - height / 2, previous + width / 2, cy + height / 2)
        )
        if box[0] < 0:
            break
        first = previous
    return dict(
        first_center=(first, cy),
        step=step,
        row_step=height * 1.065,
        width=width,
        height=height,
        columns=7,
        rows=4,
    )


def grid_boxes(grid):
    cx, cy = grid["first_center"]
    for row in range(grid.get("rows", 4)):
        for column in range(grid.get("columns", 7)):
            x = cx + (column + (row % 2) * 0.5) * grid["step"]
            y = cy + row * grid["row_step"]
            yield tuple(
                round(v)
                for v in (
                    x - grid["width"] / 2,
                    y - grid["height"] / 2,
                    x + grid["width"] / 2,
                    y + grid["height"] / 2,
                )
            )


def occupied(crop):
    rgb = np.array(crop.convert("RGB").resize((96, 112)))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    outer = np.zeros((112, 96), np.uint8)
    points = np.array([(48, 2), (93, 27), (93, 83), (48, 109), (2, 83), (2, 27)], np.int32)
    cv2.fillConvexPoly(outer, points, 1)
    inner = np.zeros_like(outer)
    cv2.fillConvexPoly(
        inner, np.array([(48, 8), (87, 30), (87, 80), (48, 103), (8, 80), (8, 30)], np.int32), 1
    )
    ring = (outer > 0) & (inner == 0)
    bright = float((hsv[:, :, 2][ring] > 110).mean())
    texture = float(rgb[20:92, 16:80].std(axis=(0, 1)).mean())
    return bright > 0.18 and texture > 18


def _feature(image, scale=1.0, offset_y=0.0):
    # Central circular mask removes borders, star badges and lock overlays.
    if scale != 1 or offset_y:
        w, h = image.size
        w2, h2 = w / scale, h / scale
        image = image.crop(
            ((w - w2) / 2, (h - h2) / 2 + offset_y * h, (w + w2) / 2, (h + h2) / 2 + offset_y * h)
        )
    rgb = np.array(image.convert("RGB").resize((48, 48)), dtype=np.float32)
    yy, xx = np.mgrid[:48, :48]
    mask = ((xx - 23.5) / 19) ** 2 + ((yy - 25) / 19) ** 2 < 1
    vector = rgb[mask].reshape(-1)
    vector -= vector.mean()
    norm = np.linalg.norm(vector)
    return vector / max(norm, 1e-6)


class PortraitMatcher:
    def __init__(self, catalog, season_id):
        self.entries = []
        for champion in catalog.champions(season_id):
            for relative in champion.get("portraits", []):
                path = catalog.image_path(relative)
                if not path.exists():
                    continue
                with Image.open(path) as im:
                    # Small scale variants account for planner crop vs square source.
                    for scale in (0.88, 1.0, 1.12):
                        for offset_y in (-0.045, 0, 0.045):
                            self.entries.append((champion, _feature(im, scale, offset_y)))
        if not self.entries:
            raise ValueError("该赛季还没有可用头像，请先批量导入或录入截图")
        self.matrix = np.stack([v for _, v in self.entries])

    def match(self, crop):
        scores = self.matrix @ _feature(crop)
        best_by_name = {}
        for (champion, _), score in zip(self.entries, scores):
            old = best_by_name.get(champion["name"])
            if old is None or score > old[0]:
                best_by_name[champion["name"]] = (float(score), champion)
        ranked = sorted(best_by_name.values(), key=lambda x: x[0], reverse=True)
        score, champion = ranked[0]
        margin = score - (ranked[1][0] if len(ranked) > 1 else -1)
        accepted = score > 0.60
        return dict(
            name=champion["name"] if accepted else "",
            suggested=champion["name"],
            score=round(score, 4),
            margin=round(margin, 4),
            champion_id=champion["id"] if accepted else "",
        )


def recognize_lineup(image, catalog, season_id, grid=None):
    from .stars import PlannerStarDetector

    grid = grid or calibrated_grid(image) or locate_grid(image)
    matcher = PortraitMatcher(catalog, season_id)
    results = []
    stars = PlannerStarDetector()
    for i, box in enumerate(grid_boxes(grid), 1):
        if box[0] < 0 or box[1] < 0 or box[2] > image.width or box[3] > image.height:
            continue
        crop = image.crop(box)
        if not occupied(crop):
            continue
        result = matcher.match(crop)
        level = stars.detect(image, box)
        results.append(
            dict(
                index=i,
                box=box,
                included=True,
                stars=level,
                stop_rule=level if level in (2, 3) else 0,
                **result,
            )
        )
    return grid, results
