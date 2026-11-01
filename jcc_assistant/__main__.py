import argparse
import json
from dataclasses import asdict
from pathlib import Path

from PIL import Image

from .mumu import MuMu
from .recognition import Recognizer, annotate


def main():
    parser = argparse.ArgumentParser(description="金铲铲商店识别原型（只识别）")
    parser.add_argument("--image", type=Path, help="识别已有截图")
    parser.add_argument("--targets", default="", help="逗号分隔的目标卡名")
    parser.add_argument("--output", type=Path, default=Path("artifacts/recognition"))
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    if args.gui:
        from .ui import run

        run()
        return
    args.output.mkdir(parents=True, exist_ok=True)
    recognizer = Recognizer()
    if args.image:
        image = Image.open(args.image).convert("RGB")
        capture_ms = None
    else:
        with MuMu() as device:
            image, capture_ms = device.capture()
    cards, ocr_ms, sheet = recognizer.recognize(image, args.targets.split(","))
    report = dict(
        image_size=image.size,
        capture_ms=capture_ms,
        ocr_ms=round(ocr_ms, 2),
        cards=[asdict(c) for c in cards],
    )
    (args.output / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sheet.save(args.output / "name_crops.png")
    annotate(image, cards, recognizer).save(args.output / "annotated.png")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
