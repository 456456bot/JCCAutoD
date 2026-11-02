"""Explicit auto-search sessions, serialized refreshes and image-based budgets."""

import threading
import time
from dataclasses import dataclass

from .economy import EconomyReadError, refresh_point

MANUAL = "手动刷新辅助"
AUTOMATIC = "自动搜牌"


@dataclass(frozen=True)
class SearchState:
    mode: str
    running: bool
    floor: int
    epoch: int


class SearchControl:
    def __init__(self):
        self._lock = threading.RLock()
        self._state = SearchState(MANUAL, False, 20, 0)

    def snapshot(self):
        with self._lock:
            return self._state

    def set_mode(self, mode):
        if mode not in (MANUAL, AUTOMATIC):
            raise ValueError("未知运行模式")
        with self._lock:
            self._state = SearchState(mode, False, self._state.floor, self._state.epoch + 1)

    def set_floor(self, floor):
        if type(floor) is not int or not 0 <= floor <= 9999:
            raise ValueError("金币下限须为 0～9999 的整数")
        with self._lock:
            s = self._state
            self._state = SearchState(s.mode, s.running, floor, s.epoch)

    def start(self):
        with self._lock:
            s = self._state
            if s.mode != AUTOMATIC:
                raise ValueError("请先切换到自动搜牌")
            self._state = SearchState(s.mode, True, s.floor, s.epoch + 1)

    def stop(self):
        with self._lock:
            s = self._state
            self._state = SearchState(s.mode, False, s.floor, s.epoch + 1)
            return self._state.epoch

    def current(self, epoch):
        with self._lock:
            s = self._state
            return s.epoch == epoch and (s.mode == MANUAL or s.running)

    def dispatch(self, epoch, action):
        with self._lock:
            if not self.current(epoch):
                return False
            action()
            return True

    def refresh(self, epoch, gold, cost, action):
        if type(gold) is not int or gold < 0 or type(cost) is not int or cost not in (0, 1, 2):
            raise ValueError("金币或刷新费用无效")
        with self._lock:
            if not self.current(epoch) or self._state.mode != AUTOMATIC:
                return "cancelled"
            if gold - cost < self._state.floor:
                self.stop()
                return "limit"
            action()
            return "refreshed"


@dataclass
class RefreshReceipt:
    names: tuple
    expected_gold: int
    cost: int
    sent_at: float
    same_count: int = 0

    def ready(self, cards, economy, now):
        if now - self.sent_at > 3.0:
            raise ValueError("刷新后未等到可确认的新商店画面，自动搜牌已停止")
        names = tuple(c.name for c in cards)
        usable = any(c.name and c.confidence >= 0.90 for c in cards)
        if not usable or economy.gold > self.expected_gold:
            self.same_count = 0
            return False
        if names != self.names:
            return True
        # Paid identical-name refreshes have an observable coin deduction. A free
        # identical shop has no receipt; stop on timeout rather than click blindly.
        self.same_count += 1
        return self.cost > 0 and self.same_count >= 2


@dataclass
class AutoStep:
    image: object
    cards: list
    capture_ms: float
    ocr_ms: float
    message: str = ""
    note: str = ""
    stopped_epoch: int | None = None


class AutoSearchSession:
    def __init__(self, epoch, clock=time.perf_counter):
        self.epoch = epoch
        self.clock = clock
        self.receipt = None
        self.refresh_count = 0
        self.uncertain_since = None
        self.uncertain_names = None
        self.numeric_since = None
        self.last_result = None

    def read_economy(self, device, recognizer, image, control, slots=()):
        # Retry in place: especially after purchases, restarting the whole step
        # could buy the same still-visible card again. No clicks occur here.
        deadline = time.perf_counter() + 2.0
        while True:
            if not control.current(self.epoch):
                raise RuntimeError("搜牌已取消")
            try:
                return recognizer.read_economy(image, slots)
            except EconomyReadError as exc:
                if time.perf_counter() >= deadline:
                    raise RuntimeError(f"数字连续 2 秒识别失败：{exc}") from exc
                image, _ = device.capture_shop()

    def step(self, device, recognizer, buyer, targets, control, detector):
        try:
            result = self._step(device, recognizer, buyer, targets, control, detector)
        except EconomyReadError as exc:
            now = self.clock()
            if self.numeric_since is None:
                self.numeric_since = now
            if now - self.numeric_since >= 2:
                raise ValueError(f"数字连续 2 秒识别失败：{exc}") from exc
            self.last_result.note = f"自动搜牌：等待数字清晰后重试；{exc}"
            return self.last_result
        self.numeric_since = None
        return result

    def _step(self, device, recognizer, buyer, targets, control, detector):
        image, capture_ms = device.capture_shop()
        cards, ocr_ms, _ = recognizer.recognize(image, targets.snapshot()[1])
        result = AutoStep(image, cards, capture_ms, ocr_ms)
        self.last_result = result
        if not control.current(self.epoch):
            return result
        if self.receipt:
            economy = recognizer.read_economy(image)
            if not self.receipt.ready(cards, economy, self.clock()):
                result.note = f"自动搜牌：等待第 {self.refresh_count} 次刷新画面；金币 {economy.gold}，显示费用 {economy.refresh_cost}。"
                return result
            self.receipt = None
        # Transitions and one difficult NON-target name must not abort a session.
        # Re-read an uncertain shop once; stable names can proceed, while Buyer
        # still only clicks names with confidence >= .90.
        uncertain = not any(c.name for c in cards) or any(
            c.name and c.confidence < 0.90 for c in cards
        )
        names_now = tuple(c.name for c in cards)
        if uncertain:
            now = self.clock()
            if self.uncertain_since is None:
                self.uncertain_since = now
            if not any(names_now):
                if now - self.uncertain_since > 3:
                    raise ValueError("连续 3 秒未识别到商店名称，请检查游戏商店是否可见")
                result.note = "自动搜牌：等待商店名称出现。"
                return result
            if names_now != self.uncertain_names and now - self.uncertain_since < 0.35:
                self.uncertain_names = names_now
                result.note = "自动搜牌：重读商店名称；低置信度卡牌不会购买。"
                return result
        self.uncertain_since = None
        self.uncertain_names = None
        if any(targets.rules().values()):
            levels = detector.detect(image)
            for card in cards:
                card.upgrade = levels[card.slot - 1]
        names = targets.snapshot()[1]
        slots = [c.slot for c in cards if c.name in names and c.confidence >= 0.90]
        economy = recognizer.read_economy(image, slots)
        # Only send affordable purchase attempts, reserving the observed card cost.
        result.message = (
            buyer.attempt(
                device,
                image,
                cards,
                spend_budget=economy.gold,
                slot_prices=economy.prices,
                dispatch_guard=lambda action: control.dispatch(self.epoch, action),
            )
            or ""
        )
        if buyer.cancelled.is_set():
            raise RuntimeError("买牌触控异常，自动搜牌已停止")
        if not targets.snapshot()[1]:
            if control.current(self.epoch):
                result.stopped_epoch = control.stop()
                result.note = "目标列表为空，自动搜牌已停止。"
            return result
        if not control.current(self.epoch):
            return result
        spent = sum(economy.prices[slot] for slot in buyer.last_clicks)
        # Do not wait for purchase confirmation. Reserve attempted spend locally,
        # and read current coins/cost once more if purchases may have changed them.
        if buyer.last_clicks:
            latest, _ = device.capture_shop()
            current = self.read_economy(device, recognizer, latest, control)
        else:
            current = economy
        effective_gold = min(current.gold, economy.gold - spent)
        state = control.snapshot()
        baseline = tuple("" if c.slot in buyer.last_clicks else c.name for c in cards)
        size = image.info.get("android_size", image.size)

        def refresh():
            # Hold the live target lock as well: deleting the final target before
            # dispatch must prevent another refresh.
            def send():
                device.tap(*refresh_point(size))
                self.receipt = RefreshReceipt(
                    baseline,
                    effective_gold - current.refresh_cost,
                    current.refresh_cost,
                    self.clock(),
                )
                self.refresh_count += 1
                buyer.record_refresh(
                    effective_gold,
                    current.refresh_cost,
                    control.snapshot().floor,
                    refresh_point(size),
                    self.refresh_count,
                )

            targets.dispatch_if_nonempty(send)

        decision = control.refresh(self.epoch, effective_gold, current.refresh_cost, refresh)
        if decision == "limit":
            result.stopped_epoch = control.snapshot().epoch
            result.note = (
                f"自动搜牌已停止：可用金币 {effective_gold}，刷新费用 {current.refresh_cost}，"
                f"下次刷新后 {effective_gold - current.refresh_cost} < 下限 {state.floor}。"
            )
        elif self.receipt:
            result.note = f"自动搜牌：已刷新 {self.refresh_count} 次；金币 {effective_gold}，本次费用 {current.refresh_cost}。"
        return result
