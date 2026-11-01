import tempfile
import unittest

from PIL import Image

from jcc_assistant.lineup.catalog import PortraitCatalog
from jcc_assistant.lineup.storage import make_profile, validate_profile, write_json


class SeasonMigrationTests(unittest.TestCase):
    def test_merge_keeps_manual_images_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = PortraitCatalog(directory)
            first = catalog.register("s16", "娑娜", Image.new("RGB", (8, 8), "blue"))
            legacy = dict(
                name="old",
                champions=[
                    dict(id="legacy_sona", name="娑娜", portraits=["manual.png"]),
                    dict(id="shaco", name="萨科", portraits=["shaco.png"]),
                ],
            )
            catalog.data["seasons"]["s16_5"] = legacy
            write_json(catalog.path, catalog.data)
            merged = PortraitCatalog(directory)
            self.assertNotIn("s16_5", merged.data["seasons"])
            self.assertEqual(merged.season("s16")["name"], "S16-海克斯典籍")
            self.assertEqual(
                merged.champions("s16")[0]["portraits"], first["portraits"] + ["manual.png"]
            )
            self.assertEqual(len(merged.champions("s16")), 2)
            self.assertIs(merged.champions("s16"), merged.champions("s16_5"))
            merged.save()
            reloaded = PortraitCatalog(directory)
            self.assertNotIn("s16_5", reloaded.data["seasons"])
            self.assertEqual(len(reloaded.champions("s16")), 2)

    def test_old_profile_loads_as_s16_and_new_profiles_use_s16(self):
        profile = make_profile("测试", "s16_5", ["娑娜"])
        self.assertEqual(profile["season_id"], "s16")
        profile["season_id"] = "s16_5"
        self.assertEqual(validate_profile(profile)["season_id"], "s16")
