import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from test_support import fixture_catalog

from jcc_assistant.lineup.catalog import PortraitCatalog
from jcc_assistant.lineup.storage import load_profile, make_profile, save_profile, validate_profile
from jcc_assistant.lineup.sync import sync_catalog
from jcc_assistant.lineup.vision import (
    PortraitMatcher,
    crop_planner,
    grid_from_cell,
    recognize_lineup,
)


class ProfileTests(unittest.TestCase):
    def test_roundtrip_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lineup.json"
            first = make_profile("阵容一", "s16", ["娑娜", "盖伦"])
            save_profile(path, first)
            self.assertEqual(load_profile(path)["targets"], ["娑娜", "盖伦"])
            second = make_profile("阵容二", "s16", ["慎"])
            save_profile(path, second)
            self.assertEqual(
                load_profile(path.with_suffix(".json.bak"))["targets"], first["targets"]
            )
            self.assertEqual(load_profile(path)["targets"], ["慎"])

    def test_reject_bad_schema_and_unknown_included_slot(self):
        with self.assertRaises(ValueError):
            validate_profile({"schema": "wrong"})
        profile = make_profile("测试", "s16", ["娑娜"], [dict(name="", included=True)])
        with self.assertRaises(ValueError):
            validate_profile(profile)
        profile["slots"][0]["included"] = False
        self.assertEqual(validate_profile(profile)["targets"], ["娑娜"])

    def test_reject_duplicate_targets(self):
        with self.assertRaises(ValueError):
            make_profile("测试", "s16", ["娑娜", "娑娜"])


class CatalogTests(unittest.TestCase):
    def test_public_import_normalizes_titles_downloads_once_and_reuses_cache(self):
        stream = io.BytesIO()
        Image.new("RGB", (128, 128), "red").save(stream, format="PNG")
        metadata = {
            "sets": {
                "2": {
                    "name": "Test",
                    "champions": [
                        dict(
                            apiName="TFT2_Ashe",
                            name="寒冰射手",
                            cost=2,
                            traits=["测试"],
                            tileIcon="assets/ashe.tex",
                        )
                    ],
                }
            }
        }

        def get(url):
            if "versions.json" in url:
                return SimpleNamespace(json=lambda: ["x"])
            if "champion.json" in url:
                return SimpleNamespace(
                    json=lambda: {"data": {"Ashe": {"name": "寒冰射手", "title": "艾希"}}}
                )
            if "zh_cn.json" in url:
                return SimpleNamespace(json=lambda: metadata)
            return SimpleNamespace(content=stream.getvalue())

        with tempfile.TemporaryDirectory() as directory:
            with patch("jcc_assistant.lineup.sync.get", side_effect=get):
                report = sync_catalog(root=directory, versions=["v1"], notify=lambda _: None)
            self.assertEqual(report["seasons"]["s2"]["ready"], 1)
            self.assertEqual(PortraitCatalog(directory).champions("s2")[0]["name"], "艾希")
            with patch(
                "jcc_assistant.lineup.sync.get",
                side_effect=AssertionError("Cache should avoid network"),
            ):
                report = sync_catalog(root=directory, versions=["v1"], notify=lambda _: None)
            self.assertEqual(report["failures"], [])

    def test_manual_registration_season_isolation_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = PortraitCatalog(directory)
            catalog.register("s1", "测试棋子", Image.new("RGB", (80, 80), "red"))
            catalog.register("s2", "测试棋子", Image.new("RGB", (80, 80), "blue"))
            catalog.save()
            loaded = PortraitCatalog(directory)
            self.assertEqual(loaded.coverage("s1")["ready"], 1)
            self.assertNotEqual(
                loaded.champions("s1")[0]["portraits"], loaded.champions("s2")[0]["portraits"]
            )
            self.assertEqual(loaded.champions("s3"), [])

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = PortraitCatalog(directory)
            with self.assertRaises(ValueError):
                catalog.image_path("../outside.png")
            with self.assertRaises(ValueError):
                catalog.season("../season")

    def test_match_requires_catalog_and_unknown_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = PortraitCatalog(directory)
            with self.assertRaises(ValueError):
                PortraitMatcher(catalog, "s16")
            image = Image.new("RGB", (128, 128), "black")
            catalog.register("s16", "测试棋子", image)
            matcher = PortraitMatcher(catalog, "s16")
            self.assertEqual(matcher.match(Image.new("RGB", (128, 128), "white"))["name"], "")


class ScreenshotLineupTests(unittest.TestCase):
    def test_reported_ten_unit_layout_never_uses_trait_strip(self):
        path = Path("tests/fixtures/lineup_sparse.png")
        catalog = fixture_catalog()
        if not path.exists() or not catalog.champions("s16"):
            self.skipTest("问题截图缺失")
        with Image.open(path) as image:
            grid, rows = recognize_lineup(image.convert("RGB"), catalog, "s16")
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row["box"][3] < 1000 for row in rows))
        self.assertEqual(sum(bool(row["name"]) for row in rows), 10)
        self.assertEqual(rows[-1]["name"], "萨科")
        self.assertGreater(grid["first_center"][1], 500)
        self.assertLess(grid["first_center"][1], 650)

    def test_crop_two_portraits_preserves_grid_without_three_anchors(self):
        path = Path("tests/fixtures/lineup_full.png")
        catalog = fixture_catalog()
        if not path.exists() or not catalog.champions("s16"):
            self.skipTest("问题截图缺失")
        with Image.open(path) as image:
            cropped = crop_planner(image.convert("RGB"), (230, 514, 478, 626))
        _, rows = recognize_lineup(cropped, catalog, "s16")
        self.assertEqual([row["name"] for row in rows], ["艾尼维亚", "泰达米尔"])

    def test_one_cell_manual_calibration(self):
        grid = grid_from_cell((232, 514, 336, 626))
        self.assertEqual(grid["first_center"], (284, 570))
        self.assertEqual(grid["step"], 140)
        with self.assertRaises(ValueError):
            grid_from_cell((0, 0, 5, 5))

    def test_user_reference_eight_champions_and_no_placeholders(self):
        path = Path("tests/fixtures/lineup.png")
        catalog = fixture_catalog()
        if not path.exists() or not catalog.champions("s16"):
            self.skipTest("真实截图与公开头像参考库未安装")
        expected = ["艾尼维亚", "泰达米尔", "艾希", "瑟庄妮", "丽桑卓", "布隆", "沃利贝尔", "奥恩"]
        with Image.open(path) as image:
            _, rows = recognize_lineup(image.convert("RGB"), catalog, "s16")
        self.assertEqual([row["name"] for row in rows], expected)

    def test_full_mumu_screenshot_same_targets(self):
        path = Path("tests/fixtures/lineup_full.png")
        catalog = fixture_catalog()
        if not path.exists() or not catalog.champions("s16"):
            self.skipTest("MuMu 样本与公开头像参考库未安装")
        with Image.open(path) as image:
            _, rows = recognize_lineup(image.convert("RGB"), catalog, "s16")
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[-1]["name"], "奥恩")
