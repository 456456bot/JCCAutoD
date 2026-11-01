import unittest

from jcc_assistant.frame_cache import ShopNameCache


class NameCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = ShopNameCache()
        self.names = ["娑娜", "盖伦", "慎", "", "克格莫"]

    def test_same_names_repeated_never_trigger(self):
        self.assertTrue(self.cache.changed(self.names))
        for _ in range(100):
            self.assertFalse(self.cache.changed(list(self.names)))

    def test_a_b_a_is_processed(self):
        other = self.names.copy()
        other[1] = "凯特琳"
        self.assertEqual(
            [
                self.cache.changed(names)
                for names in [self.names, self.names, other, other, self.names]
            ],
            [True, False, True, False, True],
        )

    def test_slot_order_matters(self):
        self.cache.changed(self.names)
        swapped = self.names.copy()
        swapped[0], swapped[1] = swapped[1], swapped[0]
        self.assertTrue(self.cache.changed(swapped))

    def test_empty_slot_change_matters(self):
        self.cache.changed(self.names)
        cleared = self.names.copy()
        cleared[0] = ""
        self.assertTrue(self.cache.changed(cleared))

    def test_invalid_sequence_does_not_overwrite_cache(self):
        self.cache.changed(self.names)
        with self.assertRaises(ValueError):
            self.cache.changed(["娑娜"])
        self.assertFalse(self.cache.changed(self.names))

    def test_new_session_processes_current_names(self):
        self.cache.changed(self.names)
        self.assertTrue(ShopNameCache().changed(self.names))
