import queue
import re
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .detail import read_detail_selection
from .frame_cache import ShopNameCache
from .hotkey import EmergencyHotkey
from .lineup.library import scan_profiles, season_title
from .lineup.storage import PROFILES, load_profile
from .mumu import MuMu
from .purchasing import Buyer
from .recognition import Recognizer
from .search import AUTOMATIC, MANUAL, AutoSearchSession, SearchControl
from .selection import read_selection
from .settings import validate_targets
from .targets import TargetList
from .ui_messages import UiMessages
from .upgrade import RULE_LABELS, UpgradeDetector
from .windows import center_new_windows


def run():
    root = tk.Tk()
    center_new_windows(root)
    root.title("金铲铲商店助手 · 双模式搜牌版")
    root.geometry("1000x840")
    search = SearchControl()
    ttk.Label(
        root, text="手动刷新辅助：列表非空自动买牌；自动搜牌：点击开始后自动买牌并刷新。"
    ).pack(anchor="w", padx=16, pady=(16, 4))
    ttk.Label(
        root,
        text="小键盘 +／−：读取右侧详情，新增／移除目标（新增默认持续关注）；1～5：添加商店牌；F8 清空。",
        wraplength=960,
    ).pack(anchor="w", padx=16)
    mode_bar = ttk.LabelFrame(root, text="运行模式", padding=8)
    mode_bar.pack(fill="x", padx=16, pady=(8, 0))
    mode_box = ttk.Combobox(mode_bar, state="readonly", values=[MANUAL, AUTOMATIC], width=18)
    mode_box.set(MANUAL)
    mode_box.pack(side="left", padx=(0, 16))
    ttk.Label(mode_bar, text="金币下限：").pack(side="left")
    floor_var = tk.StringVar(value="20")
    floor_box = ttk.Spinbox(mode_bar, from_=0, to=9999, textvariable=floor_var, width=6)
    floor_box.pack(side="left", padx=(4, 12))
    target_buttons = ttk.Frame(root)
    target_buttons.pack(anchor="w", padx=16, pady=10)
    status = tk.StringVar(value="目标列表为空，等待新增目标。")
    ttk.Label(root, textvariable=status, wraplength=960).pack(anchor="w", padx=16, pady=8)
    ttk.Label(root, text="动态目标列表（点击次数为本次启动累计，不代表实际购买数量）：").pack(
        anchor="w", padx=16
    )
    progress_tree = ttk.Treeview(
        root, columns=("name", "clicks", "rule", "state"), show="headings", height=5
    )
    for key, label in zip(
        ("name", "clicks", "rule", "state"), ("目标卡牌", "点击次数", "移除条件", "状态")
    ):
        progress_tree.heading(key, text=label)
        progress_tree.column(key, width=220, anchor="center")
    progress_tree.pack(fill="x", padx=16, pady=(4, 10))
    tree = ttk.Treeview(
        root, columns=("slot", "name", "score", "target", "upgrade"), show="headings", height=5
    )
    for key, label in zip(
        ("slot", "name", "score", "target", "upgrade"),
        ("栏位", "识别卡名", "置信度", "匹配目标", "升星提示"),
    ):
        tree.heading(key, text=label)
        tree.column(key, width=175, anchor="center")
    tree.pack(fill="x", padx=16)
    ttk.Label(
        root,
        text="命中升星条件：买下最后一张后直接移出列表，其他目标继续。星标独立检测，不受卡名去重限制。\n不复核购买结果、不统计持牌数量。F8 不能撤销已经发送的触控。",
        wraplength=960,
    ).pack(anchor="w", padx=16, pady=10)
    buttons = ttk.Frame(root)
    buttons.pack(anchor="w", padx=16)
    profile_bar = ttk.LabelFrame(root, text="导入配置", padding=8)
    profile_bar.pack(fill="x", padx=16, pady=(8, 0))
    ttk.Label(profile_bar, text="赛季：").pack(side="left")
    profile_season = ttk.Combobox(profile_bar, state="readonly", width=10)
    profile_season.pack(side="left", padx=(4, 12))
    ttk.Label(profile_bar, text="配置：").pack(side="left")
    profile_choice = ttk.Combobox(profile_bar, state="readonly", width=34)
    profile_choice.pack(side="left", padx=4)
    profile_entries = []
    ttk.Label(root, text="点击记录（日志：artifacts/purchases）：").pack(
        anchor="w", padx=16, pady=(12, 3)
    )
    history = tk.Text(root, height=6, state="disabled", wrap="word")
    history.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    closing = threading.Event()
    targets = TargetList()
    targets.default_rule = 3
    default_rule = tk.StringVar(value=RULE_LABELS[3])
    ttk.Label(target_buttons, text="手动／1～5 默认：").pack(side="left", padx=(0, 4))
    default_box = ttk.Combobox(
        target_buttons,
        state="readonly",
        textvariable=default_rule,
        values=list(RULE_LABELS.values()),
        width=13,
    )
    default_box.pack(side="left", padx=(0, 12))

    def default_changed(_=None):
        targets.default_rule = next(
            rule for rule, label in RULE_LABELS.items() if label == default_rule.get()
        )

    default_box.bind("<<ComboboxSelected>>", default_changed)
    messages = UiMessages()
    selection_requests = queue.Queue(maxsize=5)
    click_counts = {}
    poll_state = {"id": None}

    def log(text):
        history.configure(state="normal")
        history.insert("end", text + "\n")
        history.see("end")
        history.configure(state="disabled")

    def show_targets():
        rules = targets.rules()
        names = tuple(rules)
        progress_tree.delete(*progress_tree.get_children())
        for name in names:
            progress_tree.insert(
                "",
                "end",
                values=(
                    name,
                    click_counts.get(name, 0),
                    RULE_LABELS[rules[name]],
                    "待开始"
                    if search.snapshot().mode == AUTOMATIC and not search.snapshot().running
                    else "正在监测",
                ),
            )

    def update_list(names, rules=None):
        names = validate_targets(names)
        if names and not hotkey.ok:
            messagebox.showerror("无法启用购买", "F8 注册失败，请关闭旧版或释放 F8 后重启程序。")
            return False
        targets.replace(names, rules)
        show_targets()
        status.set(list_status())
        return True

    def emergency():
        search.stop()
        targets.clear()
        messages.put(("cleared", "F8：目标已清空，已禁止后续购买", None))

    def request_selection(slot):
        try:
            selection_requests.put_nowait((slot, time.perf_counter(), targets.selection_epoch()))
            targets.wake()
        except queue.Full:
            messages.put(("notice", "选牌请求过多，请稍后再按", None))

    hotkey = EmergencyHotkey(emergency, on_select=request_selection, on_detail=request_selection)
    if not hotkey.ok:
        status.set("F8 注册失败；请关闭旧版或释放 F8 后重启。当前列表保持为空。")
    failed = [str(slot) for slot, ok in hotkey.selection_ok.items() if not ok]
    if failed:
        messages.put(
            ("notice", "小键盘 " + "、".join(failed) + " 注册失败，可能被其他程序占用", None)
        )
    for action, key in [("add", "+"), ("remove", "−")]:
        if not hotkey.detail_ok.get(action):
            messages.put(("notice", f"小键盘 {key} 注册失败，可能被其他程序占用", None))

    def worker():
        recognizer, device, buyer, upgrade_detector = None, None, None, None
        name_cache = ShopNameCache()
        processed_activations = {}
        auto_session = None
        last_epoch = None
        try:
            while not closing.is_set():
                if search.snapshot().mode == MANUAL and closing.wait(0.01):
                    break
                try:
                    slot, requested_at, epoch = selection_requests.get_nowait()
                except queue.Empty:
                    pass
                else:
                    if epoch != targets.selection_epoch():
                        continue
                    try:
                        if recognizer is None:
                            recognizer = Recognizer()
                        if device is None:
                            device = MuMu()
                        if slot in ("add", "remove"):
                            name = read_detail_selection(device, recognizer, requested_at)
                            messages.put(("detail", (slot, name, epoch), None))
                        else:
                            name = read_selection(device, recognizer, slot, requested_at)
                            messages.put(("selection", (slot, name, epoch), None))
                    except Exception as exc:
                        messages.put(("notice", str(exc), None))
                    continue
                cycle = search.snapshot()
                if last_epoch != cycle.epoch:
                    name_cache = ShopNameCache()
                    processed_activations = {}
                    auto_session = None
                    last_epoch = cycle.epoch
                revision, names = targets.snapshot()
                if not names:
                    if cycle.mode == AUTOMATIC and cycle.running:
                        epoch = search.stop()
                        messages.put(
                            ("search", ("目标列表为空，自动搜牌已停止。", epoch, True), None)
                        )
                    # Reset dedup after idle so re-adding starts immediately.
                    name_cache = ShopNameCache()
                    processed_activations = {}
                    targets.wait()
                    continue
                if cycle.mode == AUTOMATIC and not cycle.running:
                    targets.wait()
                    continue
                try:
                    if recognizer is None:
                        recognizer = Recognizer()
                    if device is None:
                        device = MuMu()
                    if buyer is None:
                        buyer = Buyer(recognizer, [], threading.Event(), target_list=targets)
                    if cycle.mode == AUTOMATIC:
                        if auto_session is None:
                            auto_session = AutoSearchSession(cycle.epoch)
                        if upgrade_detector is None:
                            upgrade_detector = UpgradeDetector()
                        result = auto_session.step(
                            device, recognizer, buyer, targets, search, upgrade_detector
                        )
                        revision = targets.snapshot()[0]
                        messages.put(
                            (
                                "result",
                                (
                                    result.cards,
                                    result.image.info.get("android_size", result.image.size),
                                    result.capture_ms,
                                    result.ocr_ms,
                                    buyer.count,
                                ),
                                (revision, cycle.epoch),
                            )
                        )
                        if result.message:
                            messages.put(("purchase", (result.message, buyer.progress()), None))
                        if result.note:
                            epoch = (
                                result.stopped_epoch
                                if result.stopped_epoch is not None
                                else cycle.epoch
                            )
                            messages.put(
                                (
                                    "search",
                                    (result.note, epoch, result.stopped_epoch is not None),
                                    None,
                                )
                            )
                        continue
                    image, capture_ms = device.capture_shop()
                    cards, ocr_ms, _ = recognizer.recognize(image, names)
                    rules = targets.rules()
                    if any(rules.values()):
                        if upgrade_detector is None:
                            upgrade_detector = UpgradeDetector()
                        for card, level in zip(cards, upgrade_detector.detect(image)):
                            card.upgrade = level
                    # OCR may have overlapped list edits; use the latest snapshot.
                    revision, names, activations = targets.activation_snapshot()
                    if not names or closing.is_set():
                        continue
                    for card in cards:
                        card.target = card.name in names and bool(card.name)
                    messages.put(
                        (
                            "result",
                            (
                                cards,
                                image.info.get("android_size", image.size),
                                capture_ms,
                                ocr_ms,
                                buyer.count,
                            ),
                            (revision, cycle.epoch),
                        )
                    )
                    changed = name_cache.changed([card.name for card in cards])
                    added = {
                        name
                        for name in names
                        if activations[name] != processed_activations.get(name)
                    }
                    # Hints may appear while all five OCR names remain unchanged.
                    rules = targets.rules()
                    hinted = {
                        card.name
                        for card in cards
                        if rules.get(card.name, 0) and card.upgrade >= rules[card.name]
                    }
                    processed_activations = activations
                    if not changed and not added and not hinted:
                        continue
                    outcome = buyer.attempt(
                        device,
                        image,
                        cards,
                        eligible_names=None if changed else added | hinted,
                        dispatch_guard=lambda action: search.dispatch(cycle.epoch, action),
                    )
                    if outcome:
                        messages.put(("purchase", (outcome, buyer.progress()), None))
                    if buyer.cancelled.is_set():
                        targets.clear()
                        messages.put(("cleared", "触控异常，目标已清空并停止。", None))
                        buyer = None
                except Exception as exc:
                    if search.current(cycle.epoch):
                        if cycle.mode == AUTOMATIC:
                            epoch = search.stop()
                            messages.put(
                                (
                                    "search",
                                    (f"自动搜牌已停止：{exc}；目标列表保留。", epoch, True),
                                    None,
                                )
                            )
                        else:
                            targets.clear()
                            messages.put(("cleared", f"发生异常，目标已清空并停止：{exc}", None))
                    if device:
                        device.close()
                        device = None
                    buyer = None
        finally:
            if device:
                device.close()

    def clear_targets():
        search.stop()
        targets.clear()
        sync_mode_controls()
        show_targets()
        status.set("目标已清空，已停止。")

    def list_status():
        count = len(targets.snapshot()[1])
        state = search.snapshot()
        if not count:
            return "目标列表为空，已停止。"
        if state.mode == AUTOMATIC:
            return (
                f"自动搜牌运行中，{count} 个目标。"
                if state.running
                else f"{count} 个目标已就绪，请点击“开始搜牌”。"
            )
        return f"正在监测 {count} 个目标，列表修改立即生效。"

    def sync_mode_controls():
        state = search.snapshot()
        start_search_button.state(
            ["!disabled"] if state.mode == AUTOMATIC and not state.running else ["disabled"]
        )
        stop_search_button.state(
            ["!disabled"] if state.mode == AUTOMATIC and state.running else ["disabled"]
        )
        floor_box.state(["!disabled"] if state.mode == AUTOMATIC else ["disabled"])

    def mode_changed(_=None):
        search.set_mode(mode_box.get())
        targets.wake()
        sync_mode_controls()
        show_targets()
        status.set(list_status())

    def floor_changed(*_):
        try:
            search.set_floor(int(floor_var.get()))
        except (ValueError, tk.TclError):
            pass

    def start_search():
        if not hotkey.ok:
            messagebox.showerror("无法开始", "F8 注册失败，请先关闭旧版并重新启动。")
            return
        if not targets.snapshot()[1]:
            messagebox.showinfo("没有目标", "请先添加目标或导入配置。")
            return
        try:
            search.set_floor(int(floor_var.get()))
            search.start()
        except ValueError as exc:
            messagebox.showerror("无法开始", str(exc))
            return
        targets.wake()
        sync_mode_controls()
        show_targets()
        status.set(list_status())

    def stop_search():
        search.stop()
        targets.wake()
        sync_mode_controls()
        show_targets()
        status.set("自动搜牌已停止，目标列表保留。")

    start_search_button = ttk.Button(mode_bar, text="开始搜牌", command=start_search)
    start_search_button.pack(side="left", padx=4)
    stop_search_button = ttk.Button(mode_bar, text="停止搜牌", command=stop_search)
    stop_search_button.pack(side="left", padx=4)
    mode_box.bind("<<ComboboxSelected>>", mode_changed)
    floor_trace = floor_var.trace_add("write", floor_changed)
    sync_mode_controls()

    def refresh_profiles(_=None):
        nonlocal profile_entries
        old_name = profile_choice.get()
        entries, errors = scan_profiles(PROFILES)
        seasons = sorted(
            {season_title(e.season_id) for e in entries},
            key=lambda s: (0, int(s[1:])) if re.fullmatch(r"S\d+", s) else (1, s),
        )
        selected = profile_season.get()
        profile_season["values"] = seasons
        if selected not in seasons:
            selected = "S16" if "S16" in seasons else (seasons[0] if seasons else "")
        profile_season.set(selected)
        profile_entries = [e for e in entries if season_title(e.season_id) == selected]
        names = [e.name for e in profile_entries]
        profile_choice["values"] = names
        profile_choice.set(old_name if old_name in names else (names[0] if names else ""))
        if errors:
            status.set(f"已跳过 {len(errors)} 个无效配置文件；其他配置仍可导入。")

    def load_lineup():
        requested = (profile_season.get(), profile_choice.get())
        refresh_profiles()
        if requested[1] and requested != (profile_season.get(), profile_choice.get()):
            messagebox.showinfo("配置已变化", "原配置已移除或改名，请重新选择后导入。")
            return
        index = profile_choice.current()
        if index < 0:
            messagebox.showinfo("没有配置", "请先在配置工具中保存阵容，再选择赛季与配置。")
            return
        try:
            profile = load_profile(profile_entries[index].path)
            rules = profile.get("stop_rules", {})
            if update_list(
                profile["targets"],
                {name: rules.get(name, targets.default_rule) for name in profile["targets"]},
            ):
                log(f"已载入阵容：{profile['name']}（{profile['season_id']}）。" + list_status())
        except Exception as exc:
            messagebox.showerror("阵容载入失败", str(exc))

    def edit_target(edit=False):
        old_name = None
        if edit:
            selected = progress_tree.selection()
            if not selected:
                messagebox.showinfo("修改目标", "请先选中一项目标。")
                return
            old_name = str(progress_tree.item(selected[0], "values")[0])
        dialog = tk.Toplevel(root)
        dialog.title("修改目标" if edit else "新增目标")
        dialog.resizable(False, False)
        dialog.transient(root)
        form = ttk.Frame(dialog, padding=18)
        form.pack()
        ttk.Label(form, text="卡牌名称：").grid(row=0, column=0, sticky="w", pady=6)
        name_entry = ttk.Entry(form, width=24)
        name_entry.grid(row=0, column=1, pady=6)
        if old_name:
            name_entry.insert(0, old_name)
        ttk.Label(form, text="移除条件：").grid(row=1, column=0, sticky="w", pady=6)
        rule_box = ttk.Combobox(form, state="readonly", values=list(RULE_LABELS.values()), width=22)
        rule_box.set(RULE_LABELS[targets.rules().get(old_name, targets.default_rule)])
        rule_box.grid(row=1, column=1, pady=6)

        def commit():
            try:
                name = validate_targets([name_entry.get()])[0]
                if not hotkey.ok:
                    raise ValueError("F8 注册失败，请关闭旧版或释放 F8 后重启程序。")
                rule = next(rule for rule, label in RULE_LABELS.items() if label == rule_box.get())
                targets.edit(old_name, name, rule)
                show_targets()
                status.set("目标列表已更新，立即生效。")
                dialog.destroy()
            except ValueError as exc:
                messagebox.showerror("输入错误", str(exc), parent=dialog)

        actions = ttk.Frame(form)
        actions.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(actions, text="确定并生效", command=commit).pack(side="left", padx=6)
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="left", padx=6)
        dialog.bind("<Return>", lambda _: commit())
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        dialog.grab_set()
        name_entry.focus_set()

    def delete_target():
        selected = {
            str(progress_tree.item(item, "values")[0]) for item in progress_tree.selection()
        }
        targets.remove(selected)
        show_targets()
        status.set(
            f"正在监测 {len(targets.snapshot()[1])} 个目标。"
            if targets.snapshot()[1]
            else "目标列表为空，已停止。"
        )

    ttk.Button(target_buttons, text="新增目标", command=edit_target).pack(side="left")
    ttk.Button(target_buttons, text="修改目标", command=lambda: edit_target(True)).pack(
        side="left", padx=10
    )
    ttk.Button(target_buttons, text="删除目标", command=delete_target).pack(side="left")
    ttk.Button(buttons, text="清空目标并停止（F8）", command=clear_targets).pack(side="left")
    ttk.Button(profile_bar, text="导入配置", command=load_lineup).pack(side="left", padx=10)
    profile_season.bind("<<ComboboxSelected>>", refresh_profiles)
    profile_season.configure(postcommand=refresh_profiles)
    profile_choice.configure(postcommand=refresh_profiles)
    refresh_profiles()
    progress_tree.bind("<Double-1>", lambda _: edit_target(True))
    progress_tree.bind("<Delete>", lambda _: delete_target())

    def poll():
        for _ in range(30):
            try:
                kind, value, revision = messages.get_nowait()
            except queue.Empty:
                break
            if kind == "search":
                text, epoch, stopped = value
                if epoch != search.snapshot().epoch:
                    continue
                sync_mode_controls()
                show_targets()
                status.set(text)
                if stopped:
                    log(text)
            elif kind == "selection":
                slot, name, epoch = value
                if not hotkey.ok:
                    log("F8 不可用，未添加目标。")
                    continue
                added = targets.add_selection(name, epoch)
                if added is None:
                    continue
                show_targets()
                note = (
                    f"小键盘 {slot}：已添加 {name}。" + list_status()
                    if added
                    else f"小键盘 {slot}：{name} 已在目标列表中"
                )
                status.set(note)
                log(note)
            elif kind == "detail":
                action, name, epoch = value
                if action == "add" and not hotkey.ok:
                    log("F8 不可用，未添加目标。")
                    continue
                changed = targets.detail_selection(name, action, epoch)
                if changed is None:
                    continue
                show_targets()
                if action == "add":
                    note = (
                        f"详情 +：已添加 {name}，持续关注"
                        if changed
                        else f"详情 +：{name} 已在列表中，保留原条件"
                    )
                else:
                    note = f"详情 −：已移除 {name}" if changed else f"详情 −：{name} 不在目标列表中"
                status.set(note)
                log(note)
            elif kind == "purchase":
                text, counts = value
                click_counts.update(counts)
                show_targets()
                log(text)
                status.set(list_status())
            elif kind == "cleared":
                sync_mode_controls()
                show_targets()
                status.set(value)
                log(value)
            elif kind == "notice":
                status.set(value)
                log(value)
            elif kind == "result":
                current_revision, names = targets.snapshot()
                revision, epoch = revision
                if epoch != search.snapshot().epoch:
                    continue
                if revision != current_revision or not names:
                    continue
                cards, size, capture_ms, ocr_ms, count = value
                tree.delete(*tree.get_children())
                for card in cards:
                    tree.insert(
                        "",
                        "end",
                        values=(
                            card.slot,
                            card.name or "未识别",
                            f"{card.confidence:.1%}",
                            "是" if card.name in names else "",
                            f"即将{card.upgrade}星" if card.upgrade else "无",
                        ),
                    )
                status.set(
                    f"监测 {len(names)} 个目标 | 安卓 {size[0]}×{size[1]} | 截图 {capture_ms:.1f}ms | OCR {ocr_ms:.1f}ms | 已发送 {count} 次点击"
                )
        poll_state["id"] = root.after(50, poll)

    def close():
        search.stop()
        targets.clear()
        closing.set()
        targets.wake()
        hotkey.close()
        if poll_state["id"]:
            root.after_cancel(poll_state["id"])
        floor_var.trace_remove("write", floor_trace)
        worker_thread.join(timeout=3)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    worker_thread = threading.Thread(target=worker, daemon=False)
    worker_thread.start()
    poll()
    root.mainloop()
