"""Read hero names from the right-hand detail panel in Android coordinates."""

import time


def detail_name_box(size):
    # Calibrated from the user's 1705x1281 4:3 screenshot. Excludes portrait/cost.
    return tuple(
        round(value * size[index % 2] / (1705, 1281)[index % 2])
        for index, value in enumerate((1382, 135, 1585, 174))
    )


def detail_anchor_box(size):
    return tuple(
        round(value * size[index % 2] / (1705, 1281)[index % 2])
        for index, value in enumerate((1253, 111, 1264, 237))
    )


def panel_visible(image):
    import numpy as np

    pixels = np.asarray(image.convert("RGB")).astype(float)
    r, g, b = pixels.transpose(2, 0, 1)
    gold = (r > 95) & (g > 70) & (b < g * 0.85) & (r > b * 1.3)
    # A persistent vertical gold panel edge, not merely a few gold pixels.
    return bool((gold.mean(axis=0) > 0.65).any())


def read_detail_selection(device, recognizer, requested_at, clock=time.perf_counter):
    if clock() - requested_at > 1.5:
        raise ValueError("详情选牌请求已过期，请保持详情面板后重新按键")
    image, _ = device.capture_detail()
    if not image.info.get("detail_panel_visible", False):
        raise ValueError("未检测到右侧弈子详情面板，请先点选棋子")
    name, score = recognizer.recognize_detail_name(image)
    if clock() - requested_at > 1.5:
        raise ValueError("详情名称识别超时，请保持详情面板后重新按键")
    if not name or len(name) < 2 or score < 0.98:
        raise ValueError("详情英雄名为空或识别不确定，未修改目标列表")
    return name
