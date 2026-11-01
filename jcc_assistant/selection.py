import time


def read_selection(device, recognizer, slot, requested_at, clock=time.perf_counter):
    """Read-only hotkey selection, never reuse a stale OCR result or send touch."""
    if slot not in range(1, 6):
        raise ValueError("商店栏位必须为 1～5")
    if clock() - requested_at > 0.7:
        raise ValueError("选牌请求已过期，请保持商店画面后重新按键")
    image, _ = device.capture_shop()
    card, _ = recognizer.recognize_slot(image, slot)
    if clock() - requested_at > 0.7:
        raise ValueError("选牌识别超时，请重新按键")
    if not card.name or card.confidence < 0.98:
        raise ValueError(f"第 {slot} 栏为空或识别不确定，未添加目标")
    return card.name
