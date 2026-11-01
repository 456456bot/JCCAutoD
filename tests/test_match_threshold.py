import unittest
from unittest.mock import patch

import numpy as np

from jcc_assistant.lineup.vision import PortraitMatcher


class PortraitThresholdTests(unittest.TestCase):
    def match(self, score):
        matcher = PortraitMatcher.__new__(PortraitMatcher)
        matcher.entries = [
            ({"name": "蕾欧娜", "id": "leona"}, None),
            ({"name": "塔里克", "id": "taric"}, None),
        ]
        matcher.matrix = np.array([[score, 0], [score - 0.001, 0]])
        with patch("jcc_assistant.lineup.vision._feature", return_value=np.array([1.0, 0])):
            return matcher.match(None)

    def test_over_sixty_percent_is_accepted_without_margin_gate(self):
        self.assertEqual(self.match(0.61)["name"], "蕾欧娜")
        self.assertEqual(self.match(0.6001)["name"], "蕾欧娜")

    def test_exactly_sixty_and_below_are_unknown(self):
        self.assertEqual(self.match(0.60)["name"], "")
        self.assertEqual(self.match(0.59)["name"], "")
