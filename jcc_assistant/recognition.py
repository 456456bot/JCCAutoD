import re
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw
from rapidocr import RapidOCR


def clean_name(text):
    # UI particles are sometimes read as a trailing middle dot (e.g. 菲兹·).
    # Preserve genuine internal separators such as 德文·阿曼博.
    return re.sub(r"[^\u4e00-\u9fff·]", "", text).strip("·")


@dataclass
class Card:
    slot: int
    name: str
    confidence: float
    center: tuple
    target: bool = False
    upgrade: int = 0


class Recognizer:
    # Calibration for the user's 2048x1536 bottom-shop layout.
    BASE = (2048, 1536)

    def __init__(self):
        self.engine = RapidOCR(
            params={
                "Global.use_cls": False,
                "Global.use_det": False,
                "Global.log_level": "warning",
                "Det.limit_side_len": 320,
                "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            }
        )

    def regions(self, size):
        sx, sy = size[0] / 2048, size[1] / 1536
        return [
            tuple(
                round(v * (sx if j % 2 == 0 else sy))
                for j, v in enumerate((440 + i * 300, 1465, 638 + i * 300, 1506))
            )
            for i in range(5)
        ]

    def read_economy(self, image, price_slots=()):
        from .economy import read_economy

        return read_economy(self.engine, image, price_slots)

    def recognize_detail_name(self, image):
        crop = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
        output = self.engine.recognize_txt([crop])
        name = clean_name(output.txts[0]) if output.txts else ""
        score = float(output.scores[0]) if output.scores else 0.0
        return name, score

    def regions_for(self, image):
        size = image.info.get("android_size", image.size)
        origin = image.info.get("origin", (0, 0))
        return [tuple(v - origin[j % 2] for j, v in enumerate(box)) for box in self.regions(size)]

    def retry_target(self, crop, name, score, targets):
        if name not in targets or score >= 0.98:
            return name, score
        w, h = crop.size
        # Remove the card border/padding. Batch two resamplings only for a
        # low-confidence exact target, never fuzzy-map a different hero.
        tight = crop.crop((0, round(h * 0.1), w, round(h * 0.9)))
        variants = [
            tight,
            tight.resize((round(w * 0.75), tight.height)),
            crop.crop((round(w * 0.05), round(h * 0.1), w, round(h * 0.9))),
        ]
        output = self.engine.recognize_txt(
            [np.asarray(p.convert("RGB"))[:, :, ::-1].copy() for p in variants]
        )
        for text, confidence in zip(output.txts or (), output.scores or ()):
            if clean_name(text) == name and confidence > score:
                score = float(confidence)
        return name, score

    def recognize_slot(self, image, slot, targets=()):
        start = time.perf_counter()
        box = self.regions_for(image)[slot - 1]
        crop = np.asarray(image.crop(box))[:, :, ::-1].copy()
        output = self.engine.recognize_txt([crop])
        name = clean_name(output.txts[0]) if output.txts else ""
        score = float(output.scores[0]) if output.scores else 0.0
        name, score = self.retry_target(image.crop(box), name, score, targets)
        width, height = image.info.get("android_size", image.size)
        center = (round((575 + (slot - 1) * 300) * width / 2048), round(1370 * height / 1536))
        return Card(slot, name, round(score, 4), center, bool(name) and name in targets), (
            time.perf_counter() - start
        ) * 1000

    def recognize(self, image, targets=()):
        start = time.perf_counter()
        # Place each fixed name crop on its own row. This excludes price/traits.
        sheet = Image.new("RGB", (440, 5 * 100), "white")
        crops = []
        for i, box in enumerate(self.regions_for(image)):
            crop = image.crop(box)
            crops.append(np.asarray(crop)[:, :, ::-1].copy())
            sheet.paste(crop.resize((396, 82)), (12, i * 100 + 9))
        # Fixed line regions need neither detection nor orientation classification.
        output = self.engine.recognize_txt(crops)
        found = {}
        if output.txts is not None:
            for row, (txt, score) in enumerate(zip(output.txts, output.scores)):
                text = clean_name(txt)
                if 0 <= row < 5 and text and score > found.get(row, ("", 0))[1]:
                    found[row] = (text, float(score))
        cards = []
        for i in range(5):
            name, score = found.get(i, ("", 0.0))
            name, score = self.retry_target(
                image.crop(self.regions_for(image)[i]), name, score, targets
            )
            width, height = image.info.get("android_size", image.size)
            center = (round((575 + i * 300) * width / 2048), round(1370 * height / 1536))
            cards.append(Card(i + 1, name, round(score, 4), center, name in targets and bool(name)))
        # This is a recognition preview, not a purchase decision or shop detector.
        return cards, (time.perf_counter() - start) * 1000, sheet


def annotate(image, cards, recognizer):
    result = image.copy()
    draw = ImageDraw.Draw(result)
    for card, box in zip(cards, recognizer.regions_for(image)):
        draw.rectangle(box, outline="lime" if card.target else "orange", width=3)
    return result
