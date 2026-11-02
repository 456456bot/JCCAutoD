import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from jcc_assistant.economy import Economy, EconomyReadError, read_economy, refresh_point
from jcc_assistant.purchasing import Buyer
from jcc_assistant.recognition import Card, Recognizer
from jcc_assistant.search import AUTOMATIC, MANUAL, AutoSearchSession, RefreshReceipt, SearchControl
from jcc_assistant.targets import TargetList


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.control = SearchControl()
        self.control.set_mode(AUTOMATIC)
        self.control.start()
        self.targets = TargetList()
        self.targets.add("目标")
        self.buyer = Buyer(
            None, [], threading.Event(), Path(self.temp.name), target_list=self.targets
        )
        self.addCleanup(self.buyer.flush_logs)
        self.clock = 0.0
        self.session = AutoSearchSession(self.control.snapshot().epoch, clock=lambda: self.clock)
        self.frames = []
        self.clicks = []
        case = self

        class Device:
            def capture_shop(self):
                image = case.frames.pop(0)
                return image, 1

            def tap(self, *point):
                case.clicks.append(point)

        class OCR:
            def recognize(self, image, targets):
                return image.info["cards"], 1, None

            def read_economy(self, image, price_slots=()):
                e = image.info["economy"]
                return Economy(e.gold, e.refresh_cost, {s: e.prices[s] for s in price_slots})

        self.device = Device()
        self.ocr = OCR()
        self.detector = SimpleNamespace(detect=lambda image: [3, 0, 0, 0, 0])

    def frame(self, gold, cost, name="其他", price=1):
        image = Image.new("RGB", (100, 20))
        image.info.update(
            android_size=(2048, 1536),
            cards=[Card(i, name if i == 1 else "其他", 1, (i, 0)) for i in range(1, 6)],
            economy=Economy(gold, cost, {i: price for i in range(1, 6)}),
        )
        return image

    def step(self):
        return self.session.step(
            self.device, self.ocr, self.buyer, self.targets, self.control, self.detector
        )

    def test_zero_one_two_cost_and_exact_floor(self):
        for gold, cost, floor, allowed in [
            (20, 0, 20, True),
            (19, 0, 20, False),
            (21, 1, 20, True),
            (20, 1, 20, False),
            (22, 2, 20, True),
            (21, 2, 20, False),
        ]:
            with self.subTest(gold=gold, cost=cost):
                self.control.start()
                self.control.set_floor(floor)
                called = []
                result = self.control.refresh(
                    self.control.snapshot().epoch, gold, cost, lambda: called.append(True)
                )
                self.assertEqual(bool(called), allowed)
                self.assertEqual(result, "refreshed" if allowed else "limit")

    def test_uncertain_non_target_retries_once_then_refreshes(self):
        first = self.frame(22, 2)
        first.info["cards"][2].confidence = 0.85
        self.frames = [first, first.copy()]
        self.assertIn("重读", self.step().note)
        self.assertFalse(self.clicks)
        self.step()
        self.assertEqual(self.clicks, [refresh_point((2048, 1536))])

    def test_numeric_failure_retries_without_clicking_or_stopping(self):
        self.frames = [self.frame(22, 2), self.frame(22, 2)]
        original = self.ocr.read_economy
        failures = [True, False]

        def read(*args):
            if failures.pop(0):
                raise EconomyReadError("refresh 数字识别不确定")
            return original(*args)

        self.ocr.read_economy = read
        self.assertIn("重试", self.step().note)
        self.assertFalse(self.clicks)
        self.assertTrue(self.control.snapshot().running)
        self.step()
        self.assertEqual(len(self.clicks), 1)

    def test_numeric_retry_timeout_is_bounded(self):
        self.frames = [self.frame(22, 2), self.frame(22, 2)]

        def fail(*args):
            raise EconomyReadError("refresh 数字识别不确定")

        self.ocr.read_economy = fail
        self.step()
        self.clock = 2.1
        with self.assertRaisesRegex(ValueError, "连续 2 秒"):
            self.step()
        self.assertFalse(self.clicks)

    def test_post_purchase_numeric_retry_does_not_repeat_purchase(self):
        self.frames = [self.frame(30, 2, "目标"), self.frame(29, 2), self.frame(29, 2)]
        original = self.ocr.read_economy
        calls = []

        def read(*args):
            calls.append(True)
            if len(calls) == 2:
                raise EconomyReadError("refresh 数字识别不确定")
            return original(*args)

        self.ocr.read_economy = read
        self.step()
        self.assertEqual(self.clicks, [(1, 0), refresh_point((2048, 1536))])

    def test_blank_transition_waits_and_recovers_without_clicks(self):
        blank = self.frame(22, 2)
        for card in blank.info["cards"]:
            card.name = ""
        self.frames = [blank, self.frame(22, 2)]
        self.assertIn("等待", self.step().note)
        self.assertFalse(self.clicks)
        self.step()
        self.assertEqual(len(self.clicks), 1)

    def test_persistently_blank_shop_stops_after_bounded_wait(self):
        blank = self.frame(22, 2)
        for card in blank.info["cards"]:
            card.name = ""
        self.frames = [blank, blank.copy()]
        self.step()
        self.clock = 3.1
        with self.assertRaisesRegex(ValueError, "连续 3 秒"):
            self.step()
        self.assertFalse(self.clicks)

    def test_low_confidence_target_is_not_bought(self):
        frame = self.frame(22, 2, "目标")
        frame.info["cards"][0].confidence = 0.85
        self.frames = [frame, frame.copy()]
        self.step()
        self.step()
        self.assertEqual(self.clicks, [refresh_point((2048, 1536))])

    def test_ninety_percent_target_is_bought_but_below_threshold_is_not(self):
        frame = self.frame(22, 2, "目标")
        frame.info["cards"][0].confidence = 0.90
        frame.info["cards"][1].name = "目标"
        frame.info["cards"][1].confidence = 0.8999
        self.frames = [frame, frame.copy(), self.frame(21, 2)]
        self.step()
        self.step()
        self.assertEqual(self.clicks, [(1, 0)])

    def test_refresh_receipt_accepts_changed_shop_with_uncertain_non_target(self):
        before = self.frame(22, 2)
        after = self.frame(20, 2, "新牌")
        after.info["cards"][3].confidence = 0.8
        receipt = RefreshReceipt(tuple(c.name for c in before.info["cards"]), 20, 2, 0)
        self.assertTrue(receipt.ready(after.info["cards"], Economy(20, 2), 0.2))

    def test_start_stop_and_mode_change_invalidate_inflight_actions(self):
        epoch = self.control.snapshot().epoch
        self.control.stop()
        self.assertFalse(self.control.dispatch(epoch, lambda: self.fail("stopped action")))
        self.control.start()
        epoch = self.control.snapshot().epoch
        self.control.set_mode(MANUAL)
        self.assertFalse(self.control.dispatch(epoch, lambda: self.fail("old mode action")))
        self.assertFalse(self.control.snapshot().running)
        self.control.set_mode(AUTOMATIC)
        self.assertFalse(self.control.current(self.control.snapshot().epoch))

    def test_latest_floor_is_checked_at_dispatch(self):
        self.control.set_floor(21)
        self.assertEqual(
            self.control.refresh(
                self.control.snapshot().epoch, 22, 2, lambda: self.fail("floor changed")
            ),
            "limit",
        )

    def test_one_refresh_waits_for_new_shop_then_stops_at_floor(self):
        self.frames = [self.frame(22, 2), self.frame(22, 2), self.frame(20, 2, name="另一张")]
        self.step()
        self.assertEqual(self.clicks, [refresh_point((2048, 1536))])
        self.step()
        self.assertEqual(len(self.clicks), 1)
        result = self.step()
        self.assertEqual(len(self.clicks), 1)
        self.assertIn("下限 20", result.note)
        self.assertEqual(self.targets.snapshot()[1], ("目标",))
        self.assertFalse(self.control.snapshot().running)

    def test_free_refresh_reloads_new_cost_and_stops_on_one_gold_cost(self):
        self.frames = [self.frame(20, 0), self.frame(20, 0), self.frame(20, 1, name="新商店")]
        self.step()
        self.step()
        result = self.step()
        self.assertEqual(len(self.clicks), 1)
        self.assertIn("刷新费用 1", result.note)

    def test_paid_then_free_uses_observed_cost_instead_of_assuming_two(self):
        self.frames = [self.frame(22, 2), self.frame(20, 0, name="新商店")]
        self.step()
        self.step()
        self.assertEqual(len(self.clicks), 2)
        self.assertTrue(self.control.snapshot().running)

    def test_pending_purchase_spend_is_reserved_without_confirmation(self):
        self.control.set_floor(8)
        self.frames = [self.frame(10, 2, "目标", 3), self.frame(10, 2)]
        result = self.step()
        self.assertEqual(self.clicks, [(1, 0)])
        self.assertIn("可用金币 7", result.note)
        self.assertEqual(self.targets.snapshot()[1], ("目标",))

    def test_final_upgrade_removes_target_and_does_not_refresh(self):
        self.targets.set_rule("目标", 3)
        self.frames = [self.frame(30, 2, "目标", 3)]
        result = self.step()
        self.assertEqual(self.clicks, [(1, 0)])
        self.assertFalse(self.targets.snapshot()[1])
        self.assertFalse(self.control.snapshot().running)
        self.assertIn("目标列表为空", result.note)

    def test_hints_bind_by_slot_even_when_card_list_is_reordered(self):
        self.targets.set_rule("目标", 3)
        self.targets.add("保留")
        frame = self.frame(20, 2, "目标")
        cards = frame.info["cards"]
        cards[1].name = "保留"
        frame.info["cards"] = [cards[1], cards[0], *cards[2:]]
        self.frames = [frame, self.frame(19, 2)]
        self.step()
        self.assertEqual(self.targets.snapshot()[1], ("保留",))
        self.assertEqual(cards[0].upgrade, 3)
        self.assertEqual(cards[1].upgrade, 0)

    def test_stopped_during_ocr_cannot_buy_or_refresh(self):
        self.frames = [self.frame(30, 2, "目标", 3)]
        original = self.ocr.recognize

        def recognize(*args):
            self.control.stop()
            return original(*args)

        self.ocr.recognize = recognize
        self.step()
        self.assertFalse(self.clicks)

    def test_deleting_final_target_during_economy_read_prevents_refresh(self):
        self.frames = [self.frame(30, 2)]
        original = self.ocr.read_economy

        def read(*args):
            self.targets.clear()
            return original(*args)

        self.ocr.read_economy = read
        self.step()
        self.assertFalse(self.clicks)

    def test_removed_duplicate_does_not_consume_another_targets_purchase_budget(self):
        self.targets.set_rule("目标", 3)
        self.targets.add("另一个目标")
        first = self.frame(6, 2, "目标", 3)
        first.info["cards"][1].name = "目标"
        first.info["cards"][2].name = "另一个目标"
        self.control.set_floor(0)
        self.frames = [first, self.frame(6, 2)]
        self.step()
        self.assertEqual(self.clicks, [(1, 0), (3, 0)])
        self.assertEqual(self.targets.snapshot()[1], ("另一个目标",))

    def test_stalled_or_free_identical_shop_times_out_without_second_click(self):
        self.frames = [self.frame(20, 0), self.frame(20, 0)]
        self.step()
        self.clock = 8.1
        with self.assertRaisesRegex(ValueError, "新商店"):
            self.step()
        self.assertEqual(len(self.clicks), 1)

    def test_changed_shop_does_not_wait_for_reserved_purchase_gold(self):
        self.frames = [
            self.frame(40, 0, "目标", 3),
            self.frame(40, 0),
            self.frame(40, 0, "新的商店"),
        ]
        self.step()
        self.assertEqual(len(self.clicks), 2)
        self.step()
        self.assertEqual(len(self.clicks), 3)
        self.assertTrue(self.control.snapshot().running)

    def test_shop_change_after_income_or_slow_response_is_accepted(self):
        before = self.frame(22, 2)
        after = self.frame(30, 2, "新的商店")
        receipt = RefreshReceipt(tuple(c.name for c in before.info["cards"]), 20, 2, 0)
        self.assertTrue(receipt.ready(after.info["cards"], Economy(30, 2), 8.5))

    def test_purchase_disappearance_does_not_prove_refresh(self):
        before = self.frame(30, 0, "目标")
        after = self.frame(27, 0, "")
        receipt = RefreshReceipt(tuple(c.name for c in before.info["cards"]), 27, 0, 0)
        self.assertFalse(receipt.ready(after.info["cards"], Economy(27, 0), 0.3))

    def test_unreliable_changed_name_does_not_prove_refresh(self):
        before = self.frame(30, 0)
        after = self.frame(30, 0, "噪声")
        after.info["cards"][0].confidence = 0.5
        receipt = RefreshReceipt(tuple(c.name for c in before.info["cards"]), 30, 0, 0)
        self.assertFalse(receipt.ready(after.info["cards"], Economy(30, 0), 0.3))

    def test_paid_identical_names_need_coin_receipt_and_two_reads(self):
        cards = self.frame(20, 2).info["cards"]
        receipt = RefreshReceipt(tuple(c.name for c in cards), 18, 2, 0)
        self.assertFalse(receipt.ready(cards, Economy(20, 2), 0.1))
        self.assertFalse(receipt.ready(cards, Economy(18, 2), 0.2))
        self.assertTrue(receipt.ready(cards, Economy(18, 2), 0.3))


class EconomyTests(unittest.TestCase):
    def test_actual_free_refresh_glow_reads_zero_at_original_threshold(self):
        recognizer = Recognizer()
        with (
            Image.open("tests/fixtures/refresh_zero_glow.png") as cost,
            Image.open("assets/economy/gold_52.png") as gold,
        ):
            image = Image.new("RGB", (10, 10))
            image.info["economy_regions"] = {"gold": gold.copy(), "refresh": cost.copy()}
            self.assertEqual(recognizer.read_economy(image), Economy(52, 0))

    def test_uncertain_refresh_is_reprocessed_without_guessing_cost(self):
        outputs = iter(
            [
                SimpleNamespace(txts=("20", "2"), scores=(1, 0.8)),
                SimpleNamespace(txts=("2", "2"), scores=(0.995, 0.99)),
            ]
        )
        engine = SimpleNamespace(recognize_txt=lambda crops: next(outputs))
        image = Image.new("RGB", (2048, 1536))
        self.assertEqual(read_economy(engine, image), Economy(20, 2))

    def test_conflicting_refresh_variants_are_rejected(self):
        outputs = iter(
            [
                SimpleNamespace(txts=("20", "2"), scores=(1, 0.8)),
                SimpleNamespace(txts=("0", "2"), scores=(0.995, 0.99)),
            ]
        )
        engine = SimpleNamespace(recognize_txt=lambda crops: next(outputs))
        with self.assertRaises(EconomyReadError):
            read_economy(engine, Image.new("RGB", (2048, 1536)))

    def test_real_shop_and_user_currency_crops(self):
        recognizer = Recognizer()
        with Image.open("tests/fixtures/shop.png") as image:
            e = recognizer.read_economy(image, [1, 2, 3, 4, 5])
            self.assertEqual((e.gold, e.refresh_cost), (8, 2))
            self.assertEqual(e.prices, {i: 1 for i in range(1, 6)})
        image = Image.new("RGB", (10, 10))
        with (
            Image.open("assets/economy/gold_52.png") as gold,
            Image.open("assets/economy/refresh_2.png") as cost,
        ):
            image.info["economy_regions"] = {"gold": gold.copy(), "refresh": cost.copy()}
        self.assertEqual(recognizer.read_economy(image), Economy(52, 2))

    def test_numeric_ocr_accepts_zero_one_two_and_rejects_uncertain_or_invalid(self):
        image = Image.new("RGB", (100, 100))
        for text, score, ok in [
            ("0", 1, True),
            ("1", 1, True),
            ("2", 1, True),
            ("3", 1, False),
            ("", 1, False),
            ("2", 0.8, False),
            ("免费", 1, False),
        ]:
            engine = SimpleNamespace(
                recognize_txt=lambda crops: SimpleNamespace(txts=("20", text), scores=(1, score))
            )
            if ok:
                self.assertEqual(read_economy(engine, image).refresh_cost, int(text))
            else:
                with self.assertRaises(ValueError):
                    read_economy(engine, image)
