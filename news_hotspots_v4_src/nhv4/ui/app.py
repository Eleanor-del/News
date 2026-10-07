# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 主窗口

布局：左侧板块导航 ── 右侧（顶部工具条 + 卡片流 + 状态栏）
后台线程只负责抓取，所有 UI 更新都在主线程通过 after() 完成。
"""

import os
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

from ..config import APP_NAME, VERSION, save_settings
from ..core import AppCore, available_boards
from ..export import EXPORTERS, export
from ..theme import THEME_NAMES, get, resolve_fonts
from .cards import NewsCard
from .dialogs import AboutDialog, SettingsDialog, SourceManagerDialog
from .reader import ReaderWindow
from .widgets import Bar, FlatButton, ScrollableFrame, Separator, Toast

PAGE = 120          # 每页渲染条数


class HotspotsApp:
    def __init__(self, root):
        self.root = root
        self.core = AppCore()
        self.theme_name = self.core.settings.get("theme", "清爽蓝")
        if self.theme_name not in THEME_NAMES:
            self.theme_name = "清爽蓝"
        self.theme = get(self.theme_name)

        self.board = self.core.settings.get("board", "全部")
        self.search_var = tk.StringVar(master=root)
        self.status_var = tk.StringVar(master=root, value="正在载入…")
        self.sort_mode = self.core.settings.get("sort", "rank")

        self.cards = []
        self._limit = PAGE
        self._new_items = []
        self._got = 0
        self._expected = 0
        self._started_at = 0.0
        self._poll_job = None
        self._popup = None
        self._search_job = None
        self._resize_job = None
        self._refresh_at = 0.0

        self._setup_window()
        self._build_fonts()
        self._build_ui()
        self.toast = Toast(root, self.theme, self.fonts["body"])

        # 秒开：先渲染本地归档，再后台刷新
        self.core.load_cached()
        self.render()
        self._set_status()
        root.after(200, self.start_refresh)
        self._schedule_auto_refresh()
        self._bind_keys()

    # =====================================================================
    # 窗口与字体
    # =====================================================================
    def _setup_window(self):
        r = self.root
        r.title("%s v%s" % (APP_NAME, VERSION))
        w = self.core.settings.get("window") or {}
        r.geometry("%dx%d" % (w.get("w", 1240), w.get("h", 820)))
        r.minsize(1020, 640)
        try:
            r.configure(bg=self.theme.get("bg"))
        except Exception:                                   # noqa: BLE001
            pass

    def _build_fonts(self):
        fam, fixed = resolve_fonts(self.root)
        self.family = fam
        self.fixed = fixed
        compact = self.core.settings.get("density") == "compact"
        tsize = 11 if compact else 12
        self.fonts = {
            "h1": (fam, 20, "bold"),
            "h2": (fam, 15, "bold"),
            "h3": (fam, 10, "bold"),
            "strong": (fam, 11, "bold"),
            "nav": (fam, 11),
            "nav_on": (fam, 11, "bold"),
            "body": (fam, 10),
            "mini": (fam, 8),
            "chip": (fam, 8),
            "meta": (fam, 9),
            "btn": (fam, 9),
            "rank": (fam, 10, "bold"),
            "title": (fam, tsize),
            "sub": (fam, 9),
            "body_family": fam,
            "reader_title": (fam, 14, "bold"),
        }

    # =====================================================================
    # UI 骨架
    # =====================================================================
    def _build_ui(self):
        T = self.theme
        self.root.configure(bg=T.get("bg"))
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self.root, bg=T.get("panel"), width=224)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        main = tk.Frame(self.root, bg=T.get("bg"))
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        self._build_sidebar()
        self._build_topbar(main)
        self._build_content(main)
        self._build_statusbar()

    # ------------------------------------------------------------ 侧栏
    def _build_sidebar(self):
        T, F = self.theme, self.fonts
        for w in self.sidebar.winfo_children():
            w.destroy()

        head = tk.Frame(self.sidebar, bg=T.get("panel"))
        head.pack(fill="x", padx=18, pady=(22, 10))
        tk.Label(head, text=APP_NAME, font=F["h2"], bg=T.get("panel"),
                 fg=T.get("accent")).pack(anchor="w")
        tk.Label(head, text="v%s · 聚合 %d 源" % (VERSION, len(self.core.enabled_sources())),
                 font=F["mini"], bg=T.get("panel"), fg=T.get("sub")).pack(anchor="w", pady=(2, 0))

        Separator(self.sidebar, T.get("border")).pack(fill="x", padx=14, pady=6)

        tk.Label(self.sidebar, text="板块", font=F["h3"], bg=T.get("panel"),
                 fg=T.get("sub")).pack(anchor="w", padx=20, pady=(8, 4))

        self.nav_btns = {}
        self.boards = available_boards(self.core)
        if self.board not in self.boards:
            self.board = "全部"
        for b in self.boards:
            on = (b == self.board)
            btn = FlatButton(
                self.sidebar, b, command=lambda x=b: self.set_board(x),
                theme=T, style="accent-line", font=F["nav_on"] if on else F["nav"],
                padx=16, pady=8, anchor="w",
                active=T.get("select") if on else None)
            btn.pack(fill="x", padx=12, pady=1)
            self.nav_btns[b] = btn

        # 订阅命中提示
        hits = self.core.sub_hits()
        if hits:
            Separator(self.sidebar, T.get("border")).pack(fill="x", padx=14, pady=10)
            tk.Label(self.sidebar, text="订阅命中", font=F["h3"], bg=T.get("panel"),
                     fg=T.get("accent")).pack(anchor="w", padx=20, pady=(0, 4))
            for e in hits[:6]:
                FlatButton(self.sidebar, "· " + e.title[:18],
                           command=lambda x=e: self.open_entry(x),
                           theme=T, style="subtle", font=F["mini"],
                           padx=12, pady=5, anchor="w").pack(fill="x", padx=14, pady=1)

        # 底部
        foot = tk.Frame(self.sidebar, bg=T.get("panel"))
        foot.pack(side="bottom", fill="x", padx=12, pady=14)
        Separator(foot, T.get("border")).pack(fill="x", pady=(0, 10))
        for txt, cmd in (("数据源管理", self.open_sources),
                         ("设置", self.open_settings),
                         ("关于", self.open_about)):
            FlatButton(foot, txt, command=cmd, theme=T, style="accent-line",
                       font=F["btn"], padx=14, pady=7, anchor="w"
                       ).pack(fill="x", pady=2)

    # ------------------------------------------------------------ 顶部工具条
    def _build_topbar(self, parent):
        T, F = self.theme, self.fonts
        bar = tk.Frame(parent, bg=T.get("card"), height=58)
        bar.grid(row=0, column=0, sticky="ew")
        bar.pack_propagate(False)
        bar.columnconfigure(1, weight=1)

        left = tk.Frame(bar, bg=T.get("card"))
        left.grid(row=0, column=0, sticky="w", padx=16, pady=10)
        self.refresh_btn = FlatButton(left, "刷新", command=self.start_refresh,
                                      theme=T, style="primary", font=F["btn"],
                                      padx=16, pady=7)
        self.refresh_btn.pack(side="left")

        # 搜索
        mid = tk.Frame(bar, bg=T.get("card"))
        mid.grid(row=0, column=1, sticky="ew", padx=8)
        mid.columnconfigure(0, weight=1)
        box = tk.Frame(mid, bg=T.get("input"), highlightthickness=1,
                       highlightbackground=T.get("border"))
        box.grid(row=0, column=0, sticky="ew")
        tk.Label(box, text="🔍", bg=T.get("input"), fg=T.get("sub"),
                 font=F["body"]).pack(side="left", padx=(10, 4))
        ent = tk.Entry(box, textvariable=self.search_var, font=F["body"],
                       bg=T.get("input"), fg=T.get("fg"), relief="flat", bd=0,
                       insertbackground=T.get("accent"))
        ent.pack(side="left", fill="x", expand=True, ipady=6, pady=4)
        ent.bind("<KeyRelease>", self._on_search)
        self.search_entry = ent
        FlatButton(box, "搜历史", command=self.search_archive_mode, theme=T,
                   style="accent-line", font=F["mini"], padx=10, pady=3
                   ).pack(side="right", padx=(6, 8))

        right = tk.Frame(bar, bg=T.get("card"))
        right.grid(row=0, column=2, sticky="e", padx=16)
        for nm, mode in (("综合", "rank"), ("热度", "heat"), ("时间", "time"), ("多源", "sources")):
            FlatButton(right, nm, command=lambda m=mode: self.set_sort(m),
                       theme=T, style="subtle", font=F["mini"], padx=9, pady=5
                       ).pack(side="left", padx=2)
        layout_txt = "▦" if self.core.settings.get("layout") == "double" else "▤"
        FlatButton(right, layout_txt, command=self.toggle_layout, theme=T,
                   style="accent-line", font=F["btn"], padx=10, pady=5
                   ).pack(side="left", padx=(10, 3))
        FlatButton(right, "主题", command=self.popup_themes, theme=T,
                   style="accent-line", font=F["mini"], padx=10, pady=5
                   ).pack(side="left", padx=3)
        FlatButton(right, "导出", command=self.popup_export, theme=T,
                   style="accent-line", font=F["mini"], padx=10, pady=5
                   ).pack(side="left", padx=3)

        self.bar = Bar(parent, T, height=3)
        self.bar.grid(row=0, column=0, sticky="sew")
        self.bar.set(0)

    # ------------------------------------------------------------ 内容区
    def _build_content(self, parent):
        T = self.theme
        self.content = ScrollableFrame(parent, bg=T.get("bg"))
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.canvas.bind("<Configure>", self._on_resize)

    def _build_statusbar(self):
        T, F = self.theme, self.fonts
        sb = tk.Frame(self.root, bg=T.get("panel"))
        sb.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status_lbl = tk.Label(sb, textvariable=self.status_var, font=F["mini"],
                                   bg=T.get("panel"), fg=T.get("sub"), anchor="w")
        self.status_lbl.pack(side="left", padx=16, pady=7)
        self.health_lbl = tk.Label(sb, text="", font=F["mini"], bg=T.get("panel"),
                                   fg=T.get("weak"), anchor="e")
        self.health_lbl.pack(side="right", padx=16, pady=7)

    # =====================================================================
    # 渲染
    # =====================================================================
    def view_entries(self):
        q = self.search_var.get().strip()
        if self.board == "归档":
            return (self.core.search_archive(q) if q
                    else self.core.recent_archive(7))
        if self.board == "收藏":
            return self.core.view(favorites=True)
        return self.core.view(board=self.board, query=q)

    def render(self):
        T, F = self.theme, self.fonts
        self.content.clear()
        self.cards = []

        entries = self.view_entries()
        dense = self.core.settings.get("density") == "compact"
        cols = 2 if self.core.settings.get("layout") == "double" else 1
        pad = 8 if cols == 2 else 12

        if not entries:
            empty = tk.Frame(self.content.inner, bg=T.get("bg"))
            empty.pack(fill="both", expand=True, pady=90)
            msg = ("没有匹配的内容" if self.search_var.get().strip()
                   else "正在抓取热点…" if (self.core.refreshing or not self.core.items)
                   else "该板块暂无内容")
            tk.Label(empty, text=msg, font=F["h2"], bg=T.get("bg"),
                     fg=T.get("sub")).pack()
            tk.Label(empty, text="换个板块试试，或点击「刷新」重新抓取",
                     font=F["meta"], bg=T.get("bg"), fg=T.get("weak")).pack(pady=6)
            self._set_status(len(entries))
            return

        for i, e in enumerate(entries[:self._limit]):
            c = NewsCard(self.content.inner, e, self, T, F, dense=dense)
            c.grid(row=i // cols, column=i % cols, sticky="nsew", padx=pad, pady=5)
            self.cards.append(c)
        # 必须先清空旧列权重：从双列切回单列时，残留的第 1 列仍会占掉一半宽度
        for i in range(4):
            self.content.inner.columnconfigure(i, weight=0, minsize=0)
        for i in range(cols):
            self.content.inner.columnconfigure(i, weight=1)

        if len(entries) > self._limit:
            more = FlatButton(self.content.inner,
                              "显示更多（还有 %d 条）" % (len(entries) - self._limit),
                              command=self.load_more, theme=T, style="primary",
                              font=F["btn"], padx=20, pady=9)
            more.grid(row=(self._limit // cols) + 1, column=0, columnspan=cols, pady=16)

        self.content.refresh_wheel()
        self.root.after(60, self._apply_wrap)
        self._set_status(len(entries))

    def _apply_wrap(self):
        try:
            w = self.content.canvas.winfo_width()
            cols = 2 if self.core.settings.get("layout") == "double" else 1
            per = int(w / cols) - (110 if cols == 2 else 90)
            for c in self.cards:
                c.set_wrap(max(200, per))
        except Exception:                                   # noqa: BLE001
            pass

    def _on_resize(self, _e=None):
        if self._resize_job:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:                               # noqa: BLE001
                pass
        self._resize_job = self.root.after(160, self._apply_wrap)

    def load_more(self):
        self._limit += PAGE
        self.render()

    def refresh_view(self):
        self._limit = PAGE
        self.render()
        self._update_nav()

    def _update_nav(self):
        for b, btn in self.nav_btns.items():
            on = (b == self.board)
            btn.configure(font=self.fonts["nav_on"] if on else self.fonts["nav"])
            btn._user_bg = self.theme.get("select") if on else None
            btn._paint(False)

    # =====================================================================
    # 交互
    # =====================================================================
    def set_board(self, b):
        self.board = b
        self.core.set("board", b)
        self._limit = PAGE
        self.render()
        self._update_nav()
        self.content.scroll_top()

    def set_sort(self, mode):
        self.sort_mode = mode
        self.core.settings["sort"] = mode
        save_settings(self.core.settings)
        self.refresh_view()

    def toggle_layout(self):
        cur = self.core.settings.get("layout", "single")
        self.core.set("layout", "double" if cur == "single" else "single")
        self.render()

    def _on_search(self, _e=None):
        if self._search_job:
            try:
                self.root.after_cancel(self._search_job)
            except Exception:                               # noqa: BLE001
                pass
        self._search_job = self.root.after(260, self.refresh_view)

    def search_archive_mode(self):
        self.board = "归档"
        self.core.set("board", "归档")
        self.refresh_view()
        self._update_nav()

    def _show_popup(self, build):
        """在「主题 / 导出」按钮下方弹出浮层；点别处或按 Esc 关闭

        注意：方法名不能与属性 self._popup 同名，否则实例属性会覆盖掉方法，
        导致「主题 / 导出」按钮点了没反应。
        """
        self._close_popup()
        T = self.theme
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.configure(bg=T.get("card"), highlightthickness=1,
                      highlightbackground=T.get("border"))
        build(top)
        top.update_idletasks()
        x = self.root.winfo_rootx() + self.root.winfo_width() - top.winfo_width() - 30
        y = self.root.winfo_rooty() + 96
        top.geometry("+%d+%d" % (max(x, 10), max(y, 10)))
        top.bind("<Escape>", lambda e: self._close_popup())
        self._popup = top
        # 点击主窗口任意位置即关闭（一次性绑定，避免与浮层内按钮冲突）
        self.root.bind("<Button-1>", self._on_root_click, add="+")
        return top

    def _on_root_click(self, _e=None):
        if self._popup:
            self.root.after(10, self._close_popup)

    def _close_popup(self):
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:                               # noqa: BLE001
                pass
            self._popup = None
        try:
            self.root.unbind("<Button-1>")
        except Exception:                                   # noqa: BLE001
            pass

    def popup_themes(self):
        T, F = self.theme, self.fonts

        def build(top):
            f = tk.Frame(top, bg=T.get("card"))
            f.pack(padx=10, pady=10)
            tk.Label(f, text="选择主题", font=F["h3"], bg=T.get("card"),
                     fg=T.get("sub")).pack(anchor="w", pady=(0, 8))
            for nm in THEME_NAMES:
                th = get(nm)
                row = tk.Frame(f, bg=T.get("card"))
                row.pack(fill="x", pady=2)
                sw = tk.Frame(row, bg=th.get("accent"), width=22, height=22)
                sw.pack(side="left", padx=(0, 8))
                sw.pack_propagate(False)
                FlatButton(row, nm,
                           command=lambda n=nm: (self._close_popup(), self.apply_theme(n)),
                           theme=T, style="accent-line", font=F["mini"], padx=12, pady=5,
                           anchor="w").pack(side="left", fill="x", expand=True)
        self._show_popup(build)

    def popup_export(self):
        T, F = self.theme, self.fonts

        def build(top):
            f = tk.Frame(top, bg=T.get("card"))
            f.pack(padx=10, pady=10)
            tk.Label(f, text="导出当前列表", font=F["h3"], bg=T.get("card"),
                     fg=T.get("sub")).pack(anchor="w", pady=(0, 8))
            for key, (_fn, label, ext, desc) in EXPORTERS.items():
                FlatButton(f, "%s（%s）" % (label, ext.lstrip(".")),
                           command=lambda k=key, x=ext, d=desc: self.do_export(k, x, d),
                           theme=T, style="accent-line", font=F["mini"], padx=12, pady=6,
                           anchor="w").pack(fill="x", pady=2)
        self._show_popup(build)

    def do_export(self, key, ext, desc):
        self._close_popup()
        entries = self.view_entries()
        if not entries:
            self.toast("当前列表为空", "warn")
            return
        path = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=ext, filetypes=[(desc, "*" + ext)],
            initialdir=os.path.dirname(os.path.abspath(__file__)),
            title="导出为 %s" % desc)
        if not path:
            return
        try:
            export(key, entries, path)
        except Exception as e:                              # noqa: BLE001
            messagebox.showerror("导出失败", str(e), parent=self.root)
            return
        self.toast("已导出：%s" % os.path.basename(path), "ok")
        try:
            webbrowser.open(path)
        except Exception:                                   # noqa: BLE001
            pass

    # ------------------------------------------------------------ 条目操作
    def open_entry(self, entry):
        self.core.mark_read(entry)
        entry.read = True
        for c in self.cards:
            if c.entry is entry:
                c.refresh_marks()
        if not entry.url:
            self.toast("该条目暂无原文链接", "warn")
            return
        ReaderWindow(self.root, entry.title, entry.url,
                     "、".join(entry.sources[:4]) or entry.cluster.category,
                     self.theme, self.fonts,
                     on_fav=lambda: (self.core.toggle_fav(entry), self.refresh_view()))

    def toggle_fav(self, entry, card=None):
        on = self.core.toggle_fav(entry)
        if card:
            card.refresh_marks()
        self.toast("已收藏" if on else "已取消收藏", "ok" if on else "info")
        self._set_status()

    def open_browser(self, entry):
        if entry.url:
            webbrowser.open(entry.url)
        else:
            self.toast("该条目暂无原文链接", "warn")

    def open_url(self, url):
        if url:
            webbrowser.open(url)

    # ------------------------------------------------------------ 对话框
    def open_sources(self):
        SourceManagerDialog(self.root, self)

    def open_settings(self):
        SettingsDialog(self.root, self)

    def open_about(self):
        AboutDialog(self.root, self)

    # =====================================================================
    # 主题
    # =====================================================================
    def apply_theme(self, name):
        self.theme_name = name
        self.theme = get(name)
        self.core.set("theme", name)
        for w in self.root.winfo_children():
            w.destroy()
        self._build_fonts()
        self._build_ui()
        self.toast = Toast(self.root, self.theme, self.fonts["body"])
        self._update_nav()
        self.render()

    # =====================================================================
    # 刷新
    # =====================================================================
    def start_refresh(self):
        if self.core.refreshing:
            return
        if not self.core.enabled_sources():
            self.toast("没有启用的数据源，请先到「数据源管理」启用", "warn")
            return
        self._new_items = []
        self._got = 0
        self._expected = len(self.core.enabled_sources())
        if not self.core.start_refresh():
            return
        try:
            self.refresh_btn.set_text("刷新中…")
            self.refresh_btn.set_enabled(False)
        except Exception:                                   # noqa: BLE001
            pass
        self.bar.set(-1)
        self.status_var.set("正在抓取 %d 个数据源…" % self._expected)
        self.root.after(150, self._poll)

    def _poll(self):
        results = self.core.poll()
        for r in results:
            self._got += 1
            if r.items:
                self._new_items.extend(r.items)
        self.bar.set(self._got / float(max(1, self._expected)))
        if self._got < self._expected:
            self.status_var.set("正在抓取… %d/%d" % (self._got, self._expected))
            self._poll_job = self.root.after(140, self._poll)
            return
        self._finish_refresh()

    def _finish_refresh(self):
        ok_src = sum(1 for s in self.core.sources
                     if s.on and s.state == "ok")
        self.core.finish_refresh(self._new_items)
        self.bar.set(0)
        try:
            self.refresh_btn.set_text("刷新")
            self.refresh_btn.set_enabled(True)
        except Exception:                                   # noqa: BLE001
            pass
        self._limit = PAGE
        self.render()
        self._update_nav()
        n = len(self.core.entries)
        multi = sum(1 for e in self.core.entries if e.cluster.source_count > 1)
        self.status_var.set(
            "刷新完成 · %d 个事件（其中 %d 个多源） · %d/%d 个源成功 · %s"
            % (n, multi, ok_src, self._expected,
               time.strftime("%H:%M:%S")))
        self._update_health()
        self.core.prune_if_needed()
        self._ensure_fts()
        if ok_src == 0:
            self.toast("所有数据源都失败了，请检查网络", "error")

    def _ensure_fts(self):
        """全文索引在后台重建，不阻塞界面"""
        if not self.core.store.fts_ready:
            threading.Thread(target=self.core.store.rebuild_fts, daemon=True).start()

    def _set_status(self, count=None):
        if count is None:
            count = len(self.view_entries())
        last = self.core.last_refresh
        ts = time.strftime("%H:%M:%S", time.localtime(last)) if last else "—"
        self.status_var.set("共 %d 个事件 · %d 个数据源 · 上次刷新 %s"
                            % (count, len(self.core.enabled_sources()), ts))
        self._update_health()

    def _update_health(self):
        bad = [s.name for s in self.core.sources if s.on and s.state in ("fail", "cooled")]
        if bad:
            self.health_lbl.configure(
                text="⚠ %d 个源异常：%s" % (len(bad), "、".join(bad[:3])))
        else:
            self.health_lbl.configure(text="全部数据源正常")

    def set_auto_refresh(self, seconds):
        self.core.set("auto_refresh", int(seconds))
        self._schedule_auto_refresh()
        self.toast("自动刷新：%s" % ("已关闭" if not seconds
                                    else "每 %d 秒" % seconds), "ok")

    def _schedule_auto_refresh(self):
        if self._refresh_at:
            try:
                self.root.after_cancel(int(self._refresh_at))
            except Exception:                               # noqa: BLE001
                pass
            self._refresh_at = 0
        sec = int(self.core.settings.get("auto_refresh") or 0)
        if sec <= 0:
            return
        self._refresh_at = self.root.after(sec * 1000, self._auto_tick)

    def _auto_tick(self):
        self._refresh_at = 0
        if not self.core.refreshing:
            self.start_refresh()
        self._schedule_auto_refresh()

    # =====================================================================
    # 键盘 & 关闭
    # =====================================================================
    def _bind_keys(self):
        self.root.bind("<F5>", lambda e: self.start_refresh())
        self.root.bind("<Control-f>", lambda e: (self.search_entry.focus_set(), "break"))
        self.root.bind("<Escape>", lambda e: (self.search_var.set(""),
                                              self.refresh_view()))

    def on_close(self):
        try:
            self.core.settings["window"] = dict(w=self.root.winfo_width(),
                                                h=self.root.winfo_height())
            save_settings(self.core.settings)
        except Exception:                                   # noqa: BLE001
            pass
        self.core.engine.shutdown(wait=False)
        try:
            self.core.store.close()
        except Exception:                                   # noqa: BLE001
            pass
        self.root.destroy()


def main():
    try:                                                    # Windows HiDPI
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:                                       # noqa: BLE001
        pass

    root = tk.Tk()
    app = HotspotsApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
