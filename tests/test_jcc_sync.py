import io
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from test_support import fixture_catalog

from jcc_assistant.lineup.catalog import PortraitCatalog
from jcc_assistant.lineup.jcc_sync import playable_units, select_legend_config, sync_jcc_legend


class OfficialLegendTests(unittest.TestCase):
    def test_downloaded_s165_library_contains_all_fourteen_additions(self):
        catalog = fixture_catalog()
        if not catalog.champions("s16_5"):
            self.skipTest("S16.5 资源库未下载")
        expected = {
            "伊莉丝",
            "凯隐",
            "墨菲特",
            "布兰德",
            "希维尔",
            "库奇",
            "彗",
            "杰斯",
            "维克托",
            "艾瑞莉娅",
            "莫德凯撒",
            "萨科",
            "远古巨龙",
            "阿利斯塔",
        }
        for sid in ("s16", "s16_5"):
            units = {c["name"]: c for c in catalog.champions(sid)}
            self.assertTrue(expected <= units.keys())
            for name in expected:
                self.assertTrue(
                    any(catalog.image_path(path).exists() for path in units[name]["portraits"])
                )

    def test_standard_mode_selected_not_fortune_event(self):
        index = [
            dict(mode="16", season="S19", is_newest_version=1, herourl="/normal"),
            dict(mode="16", season="S100024", is_newest_version=1, herourl="/fortune"),
        ]
        self.assertEqual(select_legend_config(index)["herourl"], "/normal")

    def test_star_records_and_summons_excluded_but_locked_champions_kept(self):
        def unit(identifier, name, paint, price="3"):
            return dict(
                id=str(identifier),
                name=name,
                heroPaint=paint,
                picture="https://example.com/a.png",
                price=price,
                showHeroTag="0",
            )

        raw = {
            "data": {
                "a": unit(13476, "萨科", "s16_shaco"),
                "b": unit(23476, "萨科", "s16_shaco"),
                "c": unit(18339, "卫兵", "s16_soldier", "1"),
                "d": unit(14365, "凯隐", "s16_kayn"),
            }
        }
        self.assertEqual([u["name"] for u in playable_units(raw)], ["萨科", "凯隐"])

    def test_official_images_added_to_unified_season_preserving_manual_template(self):
        buffer = io.BytesIO()
        Image.new("RGB", (128, 128), "red").save(buffer, format="PNG")
        config = dict(
            mode="16",
            season="S19",
            is_newest_version=1,
            version="test",
            herourl="/16/test/chess.js",
        )
        units = {
            "data": {
                "a": dict(
                    id="13476",
                    name="萨科",
                    heroPaint="s16_shaco",
                    picture="https://example.com/shaco.png",
                    price="3",
                )
            }
        }

        def get(url):
            if "versiondataconfig" in url:
                return SimpleNamespace(json=lambda: [config])
            if "chess.js" in url:
                return SimpleNamespace(json=lambda: units)
            return SimpleNamespace(content=buffer.getvalue())

        with tempfile.TemporaryDirectory() as directory:
            catalog = PortraitCatalog(directory)
            existing = catalog.register("s16", "娑娜", Image.new("RGB", (128, 128), "blue"))
            original = existing["portraits"][:]
            catalog.save()
            with patch("jcc_assistant.lineup.jcc_sync.get", side_effect=get):
                report = sync_jcc_legend(root=directory, notify=lambda _: None)
            self.assertEqual(report["new_names"], ["萨科"])
            self.assertEqual(report["failures"], [])
            loaded = PortraitCatalog(directory)
            self.assertNotIn("s16_5", loaded.data["seasons"])
            self.assertEqual(set(report["seasons"]), {"s16"})
            for sid in ["s16", "s16_5"]:
                self.assertIn("萨科", [c["name"] for c in loaded.champions(sid)])
                self.assertEqual(
                    next(c for c in loaded.champions(sid) if c["name"] == "娑娜")["portraits"],
                    original,
                )
