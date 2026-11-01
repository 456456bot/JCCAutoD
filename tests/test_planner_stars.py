import unittest

from PIL import Image
from test_support import fixture_catalog

from jcc_assistant.lineup.stars import PlannerStarDetector, rules_from_slots
from jcc_assistant.lineup.storage import make_profile, validate_profile
from jcc_assistant.lineup.vision import recognize_lineup


class PlannerStarsTests(unittest.TestCase):
    def test_sparse_user_plan_six_units_and_star_goals(self):
        catalog = fixture_catalog()
        with Image.open("assets/lineup_stars/reference.png") as original:
            for factor in (1.0, 1.5):
                image = original.resize(
                    (round(original.width * factor), round(original.height * factor))
                )
                grid, rows = recognize_lineup(image, catalog, "s16")
                by_name = {row["name"]: row for row in rows}
                self.assertEqual(
                    set(by_name),
                    {"蕾欧娜", "塔里克", "黛安娜", "厄斐琉斯", "奥瑞利安·索尔", "佐伊"},
                )
                self.assertEqual(by_name["蕾欧娜"]["stars"], 3)
                self.assertEqual(by_name["塔里克"]["stars"], 2)
                self.assertTrue(
                    all(
                        row["stars"] == 1
                        for name, row in by_name.items()
                        if name not in ("蕾欧娜", "塔里克")
                    )
                )
                rules = rules_from_slots(rows)
                self.assertEqual(
                    rules,
                    dict(蕾欧娜=3, 塔里克=2, 黛安娜=0, 厄斐琉斯=0, 佐伊=0, **{"奥瑞利安·索尔": 0}),
                )
                profile = make_profile("星级测试", "s16", list(by_name), rows, stop_rules=rules)
                self.assertEqual(validate_profile(profile)["stop_rules"], rules)

    def test_missing_stars_default_continuous(self):
        detector = PlannerStarDetector()
        self.assertEqual(
            detector.detect(Image.new("RGB", (200, 200), "black"), (20, 0, 106, 95)), 0
        )
        self.assertEqual(
            detector.detect(Image.new("RGB", (200, 200), "black"), (20, 30, 106, 125)), 0
        )

    def test_duplicate_name_uses_highest_plan_goal(self):
        self.assertEqual(
            rules_from_slots(
                [
                    dict(name="蕾欧娜", stop_rule=0),
                    dict(name="蕾欧娜", stop_rule=3),
                    dict(name="", stop_rule=2),
                ]
            ),
            {"蕾欧娜": 3},
        )
