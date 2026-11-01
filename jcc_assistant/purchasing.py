"""Direct purchase dispatch: no recapture, confirmation or quantity limits."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from .settings import validate_targets

AUDIT_WRITER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="purchase-audit")


class Buyer:
    def __init__(
        self, recognizer, targets, cancelled, log_dir=Path("artifacts/purchases"), target_list=None
    ):
        self.targets = frozenset(validate_targets(targets))
        self.cancelled = cancelled
        self.count = 0
        self.counts = {name: 0 for name in self.targets}
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.pending_logs = []
        self.target_list = target_list
        self.last_clicks = []

    def progress(self):
        return dict(self.counts)

    def flush_logs(self):
        for future in self.pending_logs:
            future.result()

    def record_refresh(self, gold, cost, floor, coordinate, count):
        self._audit(
            dict(
                time=datetime.now().isoformat(),
                outcome="refresh_sent",
                gold=gold,
                refresh_cost=cost,
                gold_floor=floor,
                coordinate=coordinate,
                refresh_count=count,
            )
        )

    def _audit(self, row):
        def write():
            with (self.log_dir / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")

        self.pending_logs.append(AUDIT_WRITER.submit(write))

    def attempt(
        self,
        device,
        initial,
        cards,
        eligible_names=None,
        dispatch_guard=None,
        spend_budget=None,
        slot_prices=None,
    ):
        self.last_clicks = []
        for future in self.pending_logs:
            if future.done():
                future.result()
        self.pending_logs = [f for f in self.pending_logs if not f.done()]
        if self.cancelled.is_set():
            return None
        messages = []
        for card in sorted(cards, key=lambda c: c.slot):
            if self.cancelled.is_set():
                break
            current_targets = (
                self.target_list.snapshot()[1] if self.target_list is not None else self.targets
            )
            if card.name not in current_targets or card.confidence < 0.98:
                continue
            if eligible_names is not None and card.name not in eligible_names:
                continue
            if spend_budget is not None and (
                card.slot not in slot_prices or slot_prices[card.slot] > spend_budget
            ):
                continue
            now = time.perf_counter()
            row = dict(
                time=datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
                name=card.name,
                slot=card.slot,
                coordinate=card.center,
                mode="direct_click",
                shop_names=[c.name for c in sorted(cards, key=lambda c: c.slot)],
            )
            try:
                removed = False
                sent = False

                def send():
                    nonlocal sent, removed
                    if self.target_list is None:
                        device.tap(*card.center)
                        sent = True
                    else:
                        sent, removed = self.target_list.dispatch_purchase(
                            card.name, lambda: device.tap(*card.center), getattr(card, "upgrade", 0)
                        )

                if dispatch_guard is not None:
                    if not dispatch_guard(send):
                        continue
                else:
                    send()
                if not sent:
                    continue
            except Exception as exc:
                self.cancelled.set()
                self._audit(dict(row, outcome="touch_error", error=str(exc)))
                messages.append("触控异常，已停止；请检查游戏：" + str(exc))
                break
            self.count += 1
            self.last_clicks.append(card.slot)
            if spend_budget is not None:
                spend_budget -= slot_prices[card.slot]
            self.counts[card.name] = self.counts.get(card.name, 0) + 1
            elapsed = (time.perf_counter() - now) * 1000
            self._audit(
                dict(
                    row,
                    outcome="click_sent",
                    touch_call_ms=round(elapsed, 1),
                    click_count=self.count,
                    per_target_clicks=dict(self.counts),
                    upgrade_hint=getattr(card, "upgrade", 0),
                    target_removed=removed,
                )
            )
            messages.append(
                f"已发送购买点击：{card.name}（第 {card.slot} 栏），触控 {elapsed:.0f}ms；未确认购买结果"
            )
            if removed:
                messages.append(
                    f"{card.name}：识别到即将{card.upgrade}星提示，末次点击已发送，已从目标列表移除。"
                )
        return "\n".join(messages) if messages else None
