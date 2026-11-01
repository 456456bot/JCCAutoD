import argparse
from pathlib import Path

from PIL import Image

from .lineup.catalog import PortraitCatalog
from .lineup.storage import write_json
from .lineup.vision import recognize_lineup


def main():
    parser = argparse.ArgumentParser(description="阵容头像识别与 JSON 配置工具")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--season", default="s16")
    parser.add_argument("--output", type=Path, default=Path("artifacts/lineup/result.json"))
    args = parser.parse_args()
    if args.image is None:
        from .lineup.ui import run

        run()
        return
    with Image.open(args.image) as image:
        grid, rows = recognize_lineup(image.convert("RGB"), PortraitCatalog(), args.season)
    write_json(
        args.output,
        dict(
            season_id=args.season,
            grid=grid,
            slots=rows,
            targets=list(dict.fromkeys(row["name"] for row in rows if row["name"])),
            requires_review=any(not row["name"] for row in rows),
        ),
    )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
