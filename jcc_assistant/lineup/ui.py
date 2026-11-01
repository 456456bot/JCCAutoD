import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageTk

from ..upgrade import RULE_LABELS
from ..windows import center_new_windows
from .catalog import PortraitCatalog
from .jcc_sync import sync_jcc_legend
from .library import profile_path
from .stars import rules_from_slots
from .storage import PROFILES, load_profile, make_profile, save_profile
from .sync import sync_catalog
from .vision import crop_planner, grid_from_cell, recognize_lineup


def run():
    root = tk.Tk()
    center_new_windows(root)
    root.title("金铲铲 · 阵容配置工具")
    root.geometry("1380x850")
    catalog = PortraitCatalog()
    state = dict(
        image=None,
        rows=[],
        rules={},
        grid=None,
        source="",
        photo=None,
        display_scale=1,
        drag=None,
        manual=False,
        busy=False,
        generation=0,
        after_id=None,
    )
    messages = queue.Queue()
    top = ttk.LabelFrame(root, text="赛季与头像库", padding=8)
    top.pack(fill="x", padx=10, pady=(10, 4))
    ttk.Label(top, text="赛季：").pack(side="left")
    season_box = ttk.Combobox(top, state="readonly", width=30)
    season_box.pack(side="left", padx=5)
    season_ids = []
    status = tk.StringVar(value="先选择赛季，再导入图片或获取 MuMu 截图。此工具只读游戏，不购买。")
    ttk.Label(root, textvariable=status, wraplength=1330).pack(anchor="w", padx=12, pady=4)
    toolbar = ttk.Frame(root)
    toolbar.pack(fill="x", padx=10, pady=4)
    toolbar.columnconfigure(0, weight=1)
    toolbar.columnconfigure(1, weight=1)
    actions = ttk.LabelFrame(toolbar, text="1. 截图与识别", padding=8)
    actions.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    main = ttk.Panedwindow(root, orient="horizontal")
    main.pack(fill="both", expand=True, padx=10)
    left = ttk.Frame(main)
    right = ttk.LabelFrame(main, text="2. 检查识别结果", padding=8)
    main.add(left, weight=3)
    main.add(right, weight=1)
    canvas = tk.Canvas(left, bg="#252532", width=940, height=600)
    canvas.pack(fill="both", expand=True)
    ttk.Label(
        right,
        text="按图中星级生成目标：一星持续关注，二／三星对应移除。\n可在下方修改。“未知”需修正名称；相似度不是正确概率。",
        wraplength=390,
    ).pack(anchor="w")
    tree = ttk.Treeview(
        right, columns=("name", "rule", "stars", "score", "state"), show="headings", height=17
    )
    for key, label, width in [
        ("name", "棋子名称", 110),
        ("rule", "追牌目标", 100),
        ("stars", "图中星级", 65),
        ("score", "相似度", 65),
        ("state", "导出状态", 65),
    ]:
        tree.heading(key, text=label)
        tree.column(key, width=width, anchor="center")
    tree.pack(fill="both", expand=True, pady=6)
    row_actions = ttk.Frame(right)
    row_actions.pack(fill="x")
    rule_area = ttk.LabelFrame(right, text="选中棋子的追牌目标（支持多选）", padding=6)
    rule_area.pack(fill="x", pady=6)
    rule_box = ttk.Combobox(
        rule_area, state="readonly", values=list(RULE_LABELS.values()), width=18
    )
    rule_box.set(RULE_LABELS[3])
    rule_box.pack(anchor="w")
    ttk.Label(
        right,
        text="头像来自所选赛季库；金铲铲专属内容需补录。\n未知项须填写名称或明确忽略后，才能导出。",
        wraplength=310,
    ).pack(anchor="w", pady=10)
    bottom = ttk.LabelFrame(toolbar, text="3. 阵容配置文件", padding=8)
    bottom.grid(row=0, column=1, sticky="nsew")
    ttk.Label(bottom, text="阵容名称：").pack(side="left")
    profile_name = ttk.Entry(bottom, width=22)
    profile_name.insert(0, "识别阵容")
    profile_name.pack(side="left", padx=6)
    zoom = ttk.Label(right)
    zoom.pack(pady=4)

    def season_id():
        index = season_box.current()
        if index < 0:
            raise ValueError("请先选择或新建赛季")
        return season_ids[index]

    def refresh_seasons(prefer=None):
        nonlocal catalog, season_ids
        catalog = PortraitCatalog(catalog.root)
        season_ids = sorted(
            catalog.data["seasons"],
            key=lambda s: (0, int(s[1:])) if s.startswith("s") and s[1:].isdigit() else (1, s),
        )
        season_box["values"] = [catalog.data["seasons"][sid]["name"] for sid in season_ids]
        if season_ids:
            selected = (
                prefer
                if prefer in season_ids
                else ("s16" if "s16" in season_ids else season_ids[0])
            )
            season_box.current(season_ids.index(selected))

    def clear_results():
        state["rows"] = []
        state["rules"] = {}
        state["grid"] = None
        refresh_rows()

    def draw():
        image = state["image"]
        if image is None:
            return
        overlay = image.copy()
        pen = ImageDraw.Draw(overlay)
        for row in state["rows"]:
            color = (
                "#50e89a"
                if row["name"] and row["included"]
                else ("#ffb548" if row["included"] else "#777777")
            )
            pen.rectangle(row["box"], outline=color, width=max(2, image.width // 700))
            pen.text(
                (row["box"][0], row["box"][1]),
                str(row["index"]),
                fill="white",
                stroke_width=1,
                stroke_fill="black",
            )
        root.update_idletasks()
        scale = min(
            max(canvas.winfo_width(), 100) / image.width,
            max(canvas.winfo_height(), 100) / image.height,
            1,
        )
        state["display_scale"] = scale
        preview = overlay.resize((round(image.width * scale), round(image.height * scale)))
        state["photo"] = ImageTk.PhotoImage(preview)
        canvas.delete("all")
        canvas.create_image(0, 0, image=state["photo"], anchor="nw")

    def refresh_rows():
        tree.delete(*tree.get_children())
        for i, row in enumerate(state["rows"]):
            if row["name"]:
                state["rules"].setdefault(row["name"], row.get("stop_rule", 0))
            rule = RULE_LABELS[state["rules"].get(row["name"], 3)] if row["name"] else "待确认"
            tree.insert(
                "",
                "end",
                iid=str(i),
                values=(
                    row["name"] or "未知（待确认）",
                    rule,
                    f"{row['stars']}星" if row.get("stars") else "未判定",
                    f"{row.get('score', 0):.1%}",
                    "包含" if row["included"] else "忽略",
                ),
            )
        draw()

    def select_rule(_=None):
        selection = tree.selection()
        if selection:
            name = state["rows"][int(selection[0])]["name"]
            rule_box.set(RULE_LABELS[state["rules"].get(name, 3)])

    def apply_rule(_=None):
        selection = tree.selection()
        if not selection:
            return
        rule = next(key for key, value in RULE_LABELS.items() if value == rule_box.get())
        for item in selection:
            name = state["rows"][int(item)]["name"]
            if name:
                state["rules"][name] = rule
        refresh_rows()
        tree.selection_set(selection)

    def set_image(image, source):
        state["generation"] += 1
        state.update(image=image.convert("RGB"), source=source, rows=[], rules={}, grid=None)
        refresh_rows()
        status.set(
            f"已加载 {image.width}×{image.height}，请选择赛季并点击“识别配置”。可拖框裁剪阵容区域。"
        )

    def open_image():
        if state["busy"]:
            return
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if path:
            try:
                with Image.open(path) as image:
                    set_image(image.copy(), str(Path(path).resolve()))
            except Exception as exc:
                messagebox.showerror("图片读取失败", str(exc))

    def background(action):
        if state["busy"]:
            return
        state["busy"] = True

        def worker():
            try:
                messages.put(("done", action()))
            except Exception as exc:
                messages.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def capture():
        def action():
            from ..mumu import MuMu

            with MuMu() as device:
                image, _ = device.capture()
            return ("image", image, "mumu:instance0")

        status.set("正在读取 MuMu 画面……")
        background(action)

    def recognize():
        if state["image"] is None:
            messagebox.showinfo("没有图片", "先导入图片或读取 MuMu 截图")
            return
        try:
            sid = season_id()
        except ValueError as exc:
            messagebox.showerror("赛季", str(exc))
            return
        image = state["image"].copy()
        generation = state["generation"]
        grid = state["grid"]
        status.set("正在定位阵容网格并匹配所选赛季头像……")

        def action():
            found_grid, rows = recognize_lineup(image, catalog, sid, grid=grid)
            return ("recognition", sid, generation, found_grid, rows)

        background(action)

    def selected():
        rows = tree.selection()
        if not rows:
            raise ValueError("请先选择一行结果")
        return state["rows"][int(rows[0])]

    def edit_name(register=False):
        if state["busy"]:
            return
        try:
            row = selected()
            sid = season_id()
        except ValueError as exc:
            messagebox.showinfo("选择结果", str(exc))
            return
        popup = tk.Toplevel(root)
        popup.title("录入头像" if register else "修正名称")
        popup.transient(root)
        if state["image"] is not None:
            crop = state["image"].crop(row["box"])
            crop.thumbnail((180, 180))
            photo = ImageTk.PhotoImage(crop)
            label = ttk.Label(popup, image=photo)
            label.image = photo
            label.pack(padx=15, pady=10)
        entry = ttk.Combobox(
            popup, values=sorted({c["name"] for c in catalog.champions(sid)}), width=30
        )
        entry.set(row["name"])
        entry.pack(padx=15, pady=8)
        ttk.Label(popup, text="选择已有名称或输入游戏中使用的名称。").pack(padx=15)
        save_template = tk.BooleanVar(value=register)
        template_box = ttk.Checkbutton(
            popup, text="同时保存头像，供下次识别使用", variable=save_template
        )
        template_box.pack(padx=15, pady=5)
        if state["image"] is None:
            template_box.state(["disabled"])
        if not row["name"] and row.get("suggested"):
            ttk.Label(
                popup,
                text=f"候选参考：{row['suggested']}，相似度 {row.get('score', 0):.1%}；未确认，不代表真实名称。",
                wraplength=360,
            ).pack(padx=15, pady=5)

        def commit():
            name = entry.get().strip()
            if not name:
                messagebox.showerror("名称", "名称不能为空", parent=popup)
                return
            try:
                if save_template.get():
                    if state["image"] is None:
                        raise ValueError("没有原图，无法录入头像")
                    champion = catalog.register(sid, name, state["image"].crop(row["box"]))
                    catalog.save()
                    row["champion_id"] = champion["id"]
                state["rules"].setdefault(
                    name, state["rules"].get(row["name"], row.get("stop_rule", 0))
                )
                row["name"] = name
                row["included"] = True
                row["reviewed"] = True
                refresh_rows()
                popup.destroy()
            except Exception as exc:
                messagebox.showerror("保存失败", str(exc), parent=popup)

        ttk.Button(popup, text="确定", command=commit).pack(pady=12)
        popup.grab_set()
        entry.focus_set()

    def ignore():
        try:
            row = selected()
            row["included"] = not row["included"]
            refresh_rows()
        except ValueError as exc:
            messagebox.showinfo("选择结果", str(exc))

    def export():
        try:
            sid = season_id()
            included = [row for row in state["rows"] if row["included"]]
            if not included:
                raise ValueError("没有可导出的棋子")
            if any(not row["name"] for row in included):
                raise ValueError("仍有未知头像，请修正名称或忽略该行")
            names = list(dict.fromkeys(row["name"] for row in included))
            profile = make_profile(
                profile_name.get(),
                sid,
                names,
                state["rows"],
                state["source"],
                stop_rules=state["rules"],
            )
            path = profile_path(profile, PROFILES)
            save_profile(path, profile)
            status.set(f"已保存：{path}；{len(names)} 个去重目标。未修改运行中的购买列表。")
        except Exception as exc:
            messagebox.showerror("无法导出", str(exc))

    def open_profile():
        if state["busy"]:
            return
        path = filedialog.askopenfilename(initialdir=PROFILES, filetypes=[("阵容 JSON", "*.json")])
        if not path:
            return
        try:
            profile = load_profile(path)
            if profile["season_id"] not in catalog.data["seasons"]:
                catalog.season(profile["season_id"])
                catalog.save()
            refresh_seasons(profile["season_id"])
            profile_name.delete(0, "end")
            profile_name.insert(0, profile["name"])
            state["image"] = None
            canvas.delete("all")
            state["rows"] = profile.get("slots") or [
                dict(index=i, box=(0, 0, 0, 0), name=name, included=True, score=0)
                for i, name in enumerate(profile["targets"], 1)
            ]
            state["rules"] = {
                name: profile.get("stop_rules", {}).get(name, 3) for name in profile["targets"]
            }
            state["source"] = profile.get("source", "")
            refresh_rows()
        except Exception as exc:
            messagebox.showerror("载入失败", str(exc))

    def synchronize():
        status.set("正在下载公开赛季索引和头像，已有文件会跳过；失败项会保留在报告中。")

        def action():
            report = sync_catalog(
                root=catalog.root, notify=lambda text: messages.put(("progress", text))
            )
            return ("sync", report)

        background(action)

    def new_season():
        if state["busy"]:
            return
        sid = simpledialog.askstring(
            "新增赛季", "赛季 ID（如 jcc_fuxing_2026，只用英文数字下划线）："
        )
        if not sid:
            return
        label = simpledialog.askstring("赛季显示名", "请输入赛季或模式名称：")
        if not label:
            return
        try:
            catalog.season(sid.strip(), label.strip())
            catalog.save()
            refresh_seasons(sid.strip())
            clear_results()
        except Exception as exc:
            messagebox.showerror("赛季", str(exc))

    def update_jcc():
        status.set("正在从金铲铲官方索引更新 S16-海克斯典籍头像（包含原 S16.5 新棋子）……")

        def action():
            report = sync_jcc_legend(
                root=catalog.root, notify=lambda text: messages.put(("progress", text))
            )
            return ("jcc_sync", report)

        background(action)

    def mouse_down(event):
        if state["image"] is not None and not state["busy"]:
            state["drag"] = (event.x, event.y)

    def mouse_move(event):
        if state["drag"]:
            canvas.delete("selection")
            canvas.create_rectangle(
                *state["drag"], event.x, event.y, outline="yellow", width=2, tags="selection"
            )

    def mouse_up(event):
        if not state["drag"]:
            return
        x, y = state["drag"]
        state["drag"] = None
        scale = state["display_scale"]
        image = state["image"]
        box = (
            max(0, round(min(x, event.x) / scale)),
            max(0, round(min(y, event.y) / scale)),
            min(image.width, round(max(x, event.x) / scale)),
            min(image.height, round(max(y, event.y) / scale)),
        )
        canvas.delete("selection")
        if box[2] - box[0] < 20 or box[3] - box[1] < 20:
            return
        if state["manual"] == "grid":
            state["manual"] = False
            state["grid"] = grid_from_cell(box)
            state["rows"] = []
            refresh_rows()
            status.set("网格已标定，点击“识别配置”。框选裁剪时会保留该坐标标定。")
        elif state["manual"]:
            state["rows"].append(
                dict(
                    index=len(state["rows"]) + 1,
                    box=box,
                    name="",
                    suggested="",
                    score=0,
                    included=True,
                )
            )
            state["manual"] = False
            refresh_rows()
            edit_name(True)
        else:
            image = image.copy()
            if state["grid"]:
                image.info["lineup_grid"] = state["grid"]
            set_image(crop_planner(image, box), state["source"] + f"#crop={box}")

    def manual():
        if state["busy"]:
            return
        state["manual"] = True
        status.set("请拖框包住一个完整头像，随后只需选择/填写一次名称。")

    def calibrate():
        if state["busy"]:
            return
        if state["image"] is None:
            messagebox.showinfo("没有图片", "请先导入截图")
            return
        state["manual"] = "grid"
        status.set(
            "请框选阵容第一行最左侧的一个完整六边形格子（不含顶部星星，可为空格）。不要求三个头像。"
        )

    def resources():
        popup = tk.Toplevel(root)
        popup.title("头像资源管理")
        popup.transient(root)
        popup.resizable(False, False)
        group = ttk.LabelFrame(popup, text="下载与更新", padding=12)
        group.pack(fill="x", padx=12, pady=8)

        def resource_action(action):
            popup.destroy()
            action()

        ttk.Button(
            group, text="更新 S16 官方头像", command=lambda: resource_action(update_jcc)
        ).pack(anchor="w")
        ttk.Label(group, text="补充海克斯典籍官方棋子，包含原 S16.5 更新。").pack(
            anchor="w", pady=(3, 10)
        )
        ttk.Button(
            group, text="补全全部赛季公开头像", command=lambda: resource_action(synchronize)
        ).pack(anchor="w")
        ttk.Label(group, text="初次建库或补全资源时使用；已有本地头像无需重复下载。").pack(
            anchor="w", pady=3
        )
        custom = ttk.LabelFrame(popup, text="手工维护", padding=12)
        custom.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(custom, text="新增赛季／模式", command=lambda: resource_action(new_season)).pack(
            anchor="w"
        )
        ttk.Button(custom, text="框选并补录一个头像", command=lambda: resource_action(manual)).pack(
            anchor="w", pady=8
        )
        sid = season_id()
        coverage = catalog.coverage(sid)
        ttk.Label(
            custom,
            text=f"当前头像库：{catalog.data['seasons'][sid]['name']}，可用 {coverage['ready']}/{coverage['total']} 条",
        ).pack(anchor="w")

    ttk.Button(top, text="资源管理…", command=resources).pack(side="left", padx=8)
    for text, command in [
        ("获取 MuMu 截图", capture),
        ("导入截图", open_image),
        ("识别配置", recognize),
    ]:
        ttk.Button(actions, text=text, command=command).pack(side="left", padx=4)
    helpers = ttk.Menubutton(actions, text="识别辅助 ▾")
    helpers.pack(side="left", padx=12)
    menu = tk.Menu(helpers, tearoff=False)
    helpers["menu"] = menu
    menu.add_command(label="标定一个格子（定位不准时使用）", command=calibrate)
    ttk.Label(actions, text="可直接拖框裁剪阵容区域").pack(side="left", padx=4)
    for text, command in [("修正名称／补录", edit_name), ("包含／忽略", ignore)]:
        ttk.Button(row_actions, text=text, command=command).pack(side="left", padx=2)
    ttk.Button(bottom, text="保存阵容 JSON", command=export).pack(side="left", padx=10)
    ttk.Button(bottom, text="打开阵容 JSON", command=open_profile).pack(side="left", padx=4)
    tree.bind("<Double-1>", lambda _: edit_name())
    tree.bind("<<TreeviewSelect>>", select_rule)
    rule_box.bind("<<ComboboxSelected>>", apply_rule)
    canvas.bind("<ButtonPress-1>", mouse_down)
    canvas.bind("<B1-Motion>", mouse_move)
    canvas.bind("<ButtonRelease-1>", mouse_up)
    season_box.bind("<<ComboboxSelected>>", lambda _: clear_results())

    def poll():
        try:
            for _ in range(20):
                kind, value = messages.get_nowait()
                if kind == "progress":
                    status.set(value)
                elif kind == "error":
                    state["busy"] = False
                    status.set(value)
                    messagebox.showerror("操作失败", value)
                else:
                    state["busy"] = False
                    mode = value[0]
                    if mode == "image":
                        set_image(value[1], value[2])
                    elif mode == "recognition":
                        sid, generation, grid, rows = value[1:]
                        if sid != season_id() or generation != state["generation"]:
                            status.set("赛季或原图已切换，旧识别结果已丢弃")
                            continue
                        # Fresh recognition derives defaults from plan stars; manual
                        # edits within this image remain authoritative on re-recognition.
                        for name, rule in rules_from_slots(rows).items():
                            state["rules"].setdefault(name, rule)
                        state.update(grid=grid, rows=rows)
                        refresh_rows()
                        status.set(
                            f"检测到 {len(rows)} 个头像；匹配 {sum(bool(row['name']) for row in rows)} 个，未知 {sum(not row['name'] for row in rows)} 个。请核对后保存 JSON。"
                        )
                    elif mode in ("sync", "jcc_sync"):
                        refresh_seasons()
                        report_file = (
                            "jcc_s16_update_report.json"
                            if mode == "jcc_sync"
                            else "sync_report.json"
                        )
                        label = "S16 官方头像更新完成" if mode == "jcc_sync" else "公开资源导入完成"
                        status.set(
                            f"{label}，失败项 {len(value[1]['failures'])}；详见 data/portraits/{report_file}。"
                        )
        except queue.Empty:
            pass
        state["after_id"] = root.after(100, poll)

    def close():
        if state["after_id"]:
            root.after_cancel(state["after_id"])
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    refresh_seasons()
    poll()
    root.mainloop()
