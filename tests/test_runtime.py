import tempfile
import unittest
from unittest.mock import patch

from jcc_assistant.lineup.catalog import PortraitCatalog
from jcc_assistant.mumu import MuMu


class RuntimeSetupTests(unittest.TestCase):
    def test_empty_library_has_seasons_for_first_time_resource_download(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"JCC_PORTRAIT_DIR": directory}):
                catalog = PortraitCatalog()
                self.assertEqual(catalog.root.as_posix(), directory.replace("\\", "/"))
                self.assertEqual(catalog.season("s16")["name"], "S16-海克斯典籍")
                self.assertEqual(catalog.coverage("s16"), dict(total=0, ready=0, missing=0))

    def test_mumu_path_override_reports_missing_sdk_without_loading_a_library(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"JCC_MUMU_PATH": directory, "JCC_MUMU_INSTANCE": "1"}):
                with self.assertRaisesRegex(RuntimeError, "JCC_MUMU_PATH"):
                    MuMu()
