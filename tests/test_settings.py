import json
import tempfile
import unittest
from pathlib import Path

from jcc_assistant.settings import load_config, save_config, validate_targets


class SettingsTests(unittest.TestCase):
    def test_names_validation(self):
        self.assertEqual(validate_targets([" 娑娜 ", "盖伦"]), ["娑娜", "盖伦"])
        for names in [[""], ["娑娜", " 娑娜 "], [1], None]:
            with self.subTest(names=names), self.assertRaises(ValueError):
                validate_targets(names)

    def test_names_only_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            self.assertEqual(load_config(p), [])
            save_config(["娑娜", "盖伦"], p)
            self.assertEqual(load_config(p), ["娑娜", "盖伦"])
            self.assertEqual(
                json.loads(p.read_text(encoding="utf-8")),
                {"version": 3, "targets": ["娑娜", "盖伦"]},
            )

    def test_legacy_migration_discards_all_quantities(self):
        cases = [
            {"version": 1, "targets": "娑娜=6,盖伦=6", "total_limit": 1},
            {
                "version": 2,
                "targets": [{"name": "娑娜", "quantity": 6}, {"name": "盖伦", "quantity": 1}],
            },
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            for case in cases:
                p.write_text(json.dumps(case), encoding="utf-8")
                self.assertEqual(load_config(p), ["娑娜", "盖伦"])

    def test_reject_bad_version_and_duplicate_names(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            for data in [
                {"version": 99, "targets": []},
                {"version": 3, "targets": ["娑娜", "娑娜"]},
            ]:
                p.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(p)
