"""Download publicly available TFT name/portrait data; never treat it as JCC-complete."""

import hashlib
import io
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image

from .catalog import PortraitCatalog
from .storage import DATA, read_json, write_json

SNAPSHOTS = ["pbe", "15.1", "13.24", "13.18", "13.1", "11.24", "10.25", "10.15", "10.1"]


def get(url):
    response = requests.get(
        url, headers={"User-Agent": "JCCAutoD/1.0 (local portrait catalog)"}, timeout=25
    )
    response.raise_for_status()
    return response


def sync_catalog(root=DATA, versions=SNAPSHOTS, seasons=None, notify=print):
    catalog = PortraitCatalog(root)
    raw_dir = catalog.root / "sources"
    raw_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    indexed = set()
    aliases = {}
    alias_path = raw_dir / "champion_aliases.json"
    try:
        if alias_path.exists():
            aliases = read_json(alias_path)
        else:
            version = get("https://ddragon.leagueoflegends.com/api/versions.json").json()[0]
            champions = get(
                f"https://ddragon.leagueoflegends.com/cdn/{version}/data/zh_CN/champion.json"
            ).json()["data"]
            # zh_CN Data Dragon uses name for the title and title for the personal name.
            aliases = {c["name"]: c["title"] for c in champions.values()}
            write_json(alias_path, aliases)
    except Exception as exc:
        notify(f"旧版称号名称归一化不可用：{exc}")
    for version in versions:
        metadata_path = raw_dir / f"{version}.json"
        try:
            if metadata_path.exists():
                data = read_json(metadata_path)
            else:
                data = get(
                    f"https://raw.communitydragon.org/{version}/cdragon/tft/zh_cn.json"
                ).json()
                write_json(metadata_path, data)
            for number, source_set in data.get("sets", {}).items():
                if "tutorial" in source_set.get("name", "").lower():
                    continue
                sid = "s" + number
                if seasons and sid not in seasons:
                    continue
                season = catalog.season(
                    sid, f"S{number} · {source_set.get('name', '')}（公共 TFT 参考）"
                )
                # Prefer the first (newest) dataset for an existing champion ID.
                known = {c["id"]: c for c in season["champions"]}
                for unit in source_set.get("champions", []):
                    if (
                        not unit.get("traits")
                        or not 1 <= unit.get("cost", 0) <= 7
                        or not unit.get("name")
                    ):
                        continue
                    cid = unit.get("apiName")
                    portrait = unit.get("tileIcon") or unit.get("squareIcon") or unit.get("icon")
                    existing = known.get(cid)
                    if not cid or not portrait:
                        continue
                    if existing and any(
                        catalog.image_path(p).exists() for p in existing["portraits"]
                    ):
                        continue
                    path = portrait.lower().rsplit(".", 1)[0] + ".png"
                    url = f"https://raw.communitydragon.org/{version}/game/{path}"
                    if (sid, cid) in indexed:
                        fallbacks = existing.setdefault("fallback_urls", [])
                        if url != existing["url"] and url not in fallbacks:
                            fallbacks.append(url)
                        continue
                    relative = "images/" + hashlib.sha256(url.encode()).hexdigest()[:24] + ".png"
                    entry = dict(
                        id=cid,
                        name=aliases.get(unit["name"], unit["name"]),
                        cost=unit["cost"],
                        portraits=[relative],
                        url=url,
                        source=f"CommunityDragon/{version}",
                    )
                    if existing:
                        existing.update(entry)
                    else:
                        season["champions"].append(entry)
                    known[cid] = entry
                    indexed.add((sid, cid))
                season["coverage_note"] = (
                    "公共数据参考；金铲铲专属赛季、模式及部分复刻需实机补录校验"
                )
            notify(f"已读取资源索引：{version}")
        except Exception as exc:
            failures.append(dict(source=version, error=str(exc)))
            notify(f"资源索引不可用：{version}：{exc}")
    for season in catalog.data["seasons"].values():
        for champion in season["champions"]:
            if champion.get("source") != "manual":
                champion["name"] = aliases.get(champion["name"], champion["name"])
    catalog.save()
    jobs = []
    for sid in catalog.data["seasons"]:
        if seasons and sid not in seasons:
            continue
        for champion in catalog.champions(sid):
            if champion.get("url"):
                path = catalog.image_path(champion["portraits"][0])
                if not path.exists():
                    jobs.append(
                        (
                            sid,
                            champion["id"],
                            champion["url"],
                            path,
                            champion.get("fallback_urls", []),
                        )
                    )

    def fetch(job):
        sid, cid, url, path, fallbacks = job
        error = None
        for address in [url, *fallbacks]:
            try:
                payload = get(address).content
                image = Image.open(io.BytesIO(payload)).convert("RGB")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_suffix(".tmp")
                image.save(temporary, format="PNG")
                temporary.replace(path)
                break
            except Exception as exc:
                error = exc
        else:
            raise error
        return sid, cid

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch, job): job for job in jobs}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
            except Exception as exc:
                job = futures[future]
                failures.append(dict(season=job[0], champion=job[1], error=str(exc)))
            if i % 50 == 0 or i == len(jobs):
                notify(f"头像下载 {i}/{len(jobs)}")
    report = dict(
        seasons={sid: catalog.coverage(sid) for sid in catalog.data["seasons"]}, failures=failures
    )
    write_json(catalog.root / "sync_report.json", report)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="批量下载分赛季中文棋子头像参考库")
    parser.add_argument("--season", action="append", help="如 s16；不指定则同步所有可用赛季")
    args = parser.parse_args()
    report = sync_catalog(seasons=args.season)
    print("完成：", report["seasons"], "失败项：", len(report["failures"]))
