"""Import the official JCC Legend roster, including its S16.5 additions."""

import io
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

from .catalog import PortraitCatalog
from .storage import DATA, write_json
from .sync import get

INDEX_URL = "https://game.gtimg.cn/images/lol/act/jkzlk/js/config/versiondataconfig.js"
DATA_BASE = "https://game.gtimg.cn/images/lol/act/jkzlk/js"


def select_legend_config(index):
    candidates = [
        row
        for row in index
        if str(row.get("mode")) == "16"
        and row.get("is_newest_version") == 1
        and str(row.get("season", "")).startswith("S")
        and str(row["season"])[1:].isdigit()
        and int(str(row["season"])[1:]) < 100
    ]
    if not candidates:
        raise ValueError("官方索引中未找到英雄联盟传奇的标准模式最新版本")
    return max(candidates, key=lambda row: int(str(row["season"])[1:]))


def playable_units(data):
    units = {}
    rows = data.get("data", {})
    if not isinstance(rows, dict):
        raise ValueError("官方棋子数据格式变化")
    for row in rows.values():
        try:
            # The 1xxxx records are base-star playable units. Later ID ranges
            # include summons and the repeated two/three/four-star rows.
            valid = 1 <= float(row.get("price", "0")) <= 7 and 10000 <= int(row["id"]) < 18000
        except (ValueError, KeyError, TypeError):
            continue
        if valid and row.get("heroPaint") and row.get("picture") and row.get("name"):
            units.setdefault(row["heroPaint"].lower(), row)
    if not units:
        raise ValueError("官方棋子列表为空，未修改头像库")
    return list(units.values())


def sync_jcc_legend(root=DATA, notify=print):
    index = get(INDEX_URL).json()
    config = select_legend_config(index)
    url = DATA_BASE + config["herourl"]
    raw = get(url).json()
    units = playable_units(raw)
    catalog = PortraitCatalog(root)
    sources = catalog.root / "sources"
    write_json(sources / "jcc_legend_versions.json", index)
    write_json(sources / "jcc_legend_chess.json", raw)
    base = catalog.season("s16")
    existing_names = {c["name"] for c in base["champions"]}
    additions = sorted({row["name"] for row in units} - existing_names)
    failures = []
    jobs = {}
    for unit in units:
        jobs.setdefault(unit["picture"], []).append(unit)

    def download(picture):
        return Image.open(io.BytesIO(get(picture).content)).convert("RGB")

    with ThreadPoolExecutor(max_workers=8) as pool:
        pending = {pool.submit(download, picture): picture for picture in jobs}
        for i, future in enumerate(as_completed(pending), 1):
            picture = pending[future]
            try:
                image = future.result()
                for unit in jobs[picture]:
                    for sid in ("s16",):
                        old = next(
                            (c for c in catalog.champions(sid) if c["name"] == unit["name"]), None
                        )
                        cid = old["id"] if old else "jcc16_" + unit["heroPaint"].lower()
                        champion = catalog.register(
                            sid,
                            unit["name"],
                            image,
                            champion_id=cid,
                            source=f"TencentOfficial/{config['version']}",
                            cost=int(float(unit["price"])),
                        )
                        champion.update(
                            official_picture=picture,
                            official_id=unit["id"],
                            official_version=config["version"],
                        )
            except Exception as exc:
                failures.append(
                    dict(url=picture, names=[u["name"] for u in jobs[picture]], error=str(exc))
                )
            if i % 25 == 0 or i == len(pending):
                notify(f"金铲铲官方头像 {i}/{len(pending)}")
    for sid in ("s16",):
        catalog.data["seasons"][sid].update(
            official_source=url,
            official_version=config["version"],
            coverage_note="已补充金铲铲官方英雄联盟传奇最新标准模式数据；未验证所有限时模式",
        )
    catalog.save()
    report = dict(
        source_index=INDEX_URL,
        source=url,
        version=config["version"],
        internal_season=config["season"],
        new_names=additions,
        unit_forms=len(units),
        downloaded_images=len(jobs) - len(failures),
        seasons={"s16": catalog.coverage("s16")},
        failures=failures,
    )
    write_json(catalog.root / "jcc_s16_update_report.json", report)
    return report


if __name__ == "__main__":
    import json

    print(json.dumps(sync_jcc_legend(), ensure_ascii=False, indent=2))
