import tempfile
import unittest
from pathlib import Path

from jcc_assistant.lineup.library import profile_path, scan_profiles
from jcc_assistant.lineup.storage import load_profile, make_profile, save_profile


class ProfileLibraryTests(unittest.TestCase):
    def test_automatic_season_path_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = make_profile("阵容x", "s16_5", ["蕾欧娜"], stop_rules={"蕾欧娜": 3})
            path = profile_path(profile, root)
            self.assertEqual(path, root / "S16" / "s16_阵容x.json")
            save_profile(path, profile)
            profile["stop_rules"]["蕾欧娜"] = 2
            save_profile(path, profile)
            self.assertEqual(load_profile(path)["stop_rules"], {"蕾欧娜": 2})
            self.assertEqual(
                load_profile(path.with_suffix(".json.bak"))["stop_rules"], {"蕾欧娜": 3}
            )

    def test_names_cannot_escape_the_library(self):
        root = Path("configurations").resolve()
        profile = make_profile("../阵容:测试", "s16", ["蕾欧娜"])
        self.assertTrue(profile_path(profile, root).resolve().is_relative_to(root / "S16"))
        profile["season_id"] = "../../private"
        with self.assertRaises(ValueError):
            profile_path(profile, root)

    def test_scan_displays_profile_titles_skips_bad_files_and_prefers_structured_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = make_profile("阵容x", "s16", ["蕾欧娜"])
            save_profile(root / "old.json", first)
            save_profile(profile_path(first, root), first)
            other = make_profile("其他阵容", "s15", ["塔里克"])
            save_profile(profile_path(other, root), other)
            (root / "broken.json").write_text("{", encoding="utf-8")
            entries, errors = scan_profiles(root)
            self.assertEqual(len(entries), 2)
            self.assertEqual(len(errors), 1)
            entry = next(e for e in entries if e.season_id == "s16")
            self.assertEqual(entry.name, "阵容x")
            self.assertEqual(entry.path, root / "S16" / "s16_阵容x.json")
