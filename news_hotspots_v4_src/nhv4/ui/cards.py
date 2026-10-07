# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 新闻卡片

一个卡片 = 一个「事件簇」：
  排名徽章 │ 标题 │ 趋势徽章 + 多源徽章 │ 来源 / 热度 / 时间 │ 操作按钮
点击「N源」徽章可就地展开该事件在各个平台的原标题，直观看到聚合结果。
"""

import tkinter as tk

from .widgets import Chip, FlatButton


class NewsCard(tk.Frame):
    def __init__(self, master, entry, app, theme, fonts, dense=False):
        self.T = theme
        self.entry = entry
        self.app = app
        self.fonts = fonts
        self.dense = dense
        self.expanded = False

        pad = 10 if dense else 14
        tk.Frame.__init__(self, master, bg=theme.get("card"),
                          highlightthickness=1,
                          highlightbackground=theme.get("border"))
        self.pad = pad
        self._build()
        self._bind_hover(self)

    # ------------------------------------------------------------ 构建
    def _build(self):
        T, F, e, c = self.T, self.fonts, self.entry, self.entry.cluster
        pad = self.pad

        body = tk.Frame(self, bg=T.get("card"))
        body.pack(fill="both", expand=True, padx=pad, pady=pad)

        # ---- 顶部行：排名 + 标题 + 徽章
        top = tk.Frame(body, bg=T.get("card"))
        top.pack(fill="x")

        self.rank_lbl = tk.Label(top, text=str(e.rank), font=F["rank"],
                                 bg=T.get("card2"), fg=T.get("sub"),
                                 width=3, pady=4)
        self.rank_lbl.pack(side="left", anchor="n", padx=(0, 10))

        right = tk.Frame(top, bg=T.get("card"))
        right.pack(side="left", fill="both", expand=True)

        self.title_lbl = tk.Label(right, text=c.title, font=F["title"],
                                  bg=T.get("card"), fg=T.get("fg"),
                                  justify="left", anchor="w", cursor="hand2",
                                  wraplength=520)
        self.title_lbl.pack(fill="x", anchor="w")
        self.title_lbl.bind("<Button-1>", lambda ev: self.app.open_entry(e))
        self.title_lbl.bind("<Enter>", lambda ev: self.title_lbl.configure(
            fg=T.get("accent")))
        self.title_lbl.bind("<Leave>", lambda ev: self._paint_title())

        # 徽章行（趋势 / 多源 / 订阅）
        badges = tk.Frame(right, bg=T.get("card"))
        badges.pack(fill="x", anchor="w", pady=(4, 0))

        if e.trend.kind != "flat" and e.trend.label:
            Chip(badges, e.trend.label, T, kind=e.trend.style,
                 font=F["chip"]).pack(side="left", padx=(0, 6))
        if c.source_count > 1:
            self.multi_btn = Chip(badges, "%d 源在报 ▾" % c.source_count, T,
                                  kind="multi", font=F["chip"], cursor="hand2")
            self.multi_btn.pack(side="left", padx=(0, 6))
            self.multi_btn.bind("<Button-1>", lambda ev: self.toggle_expand())
        if e.subscribed:
            Chip(badges, "★ 关注", T, kind="new", font=F["chip"]).pack(
                side="left", padx=(0, 6))
        if e.fav:
            Chip(badges, "已收藏", T, kind="up", font=F["chip"]).pack(
                side="left", padx=(0, 6))

        # ---- 元信息行
        meta = tk.Frame(body, bg=T.get("card"))
        meta.pack(fill="x", padx=(33, 0), pady=(8, 0))

        Chip(meta, c.category, T, kind="cat", font=F["chip"]).pack(
            side="left", padx=(0, 6))
        for s in c.sources[:5]:
            Chip(meta, s, T, kind="source", font=F["chip"]).pack(
                side="left", padx=(0, 5))
        if len(c.sources) > 5:
            tk.Label(meta, text="+%d" % (len(c.sources) - 5), font=F["chip"],
                     bg=T.get("card"), fg=T.get("weak")).pack(side="left", padx=(0, 6))
        if c.heat_display:
            Chip(meta, "🔥 %s" % c.heat_display, T, kind="heat",
                 font=F["chip"]).pack(side="left", padx=(0, 6))
        tk.Label(meta, text=c.time_display, font=F["chip"],
                 bg=T.get("card"), fg=T.get("weak")).pack(side="left")

        # 操作按钮（右侧）
        acts = tk.Frame(meta, bg=T.get("card"))
        acts.pack(side="right")
        FlatButton(acts, "阅读", command=lambda: self.app.open_entry(e),
                   theme=T, style="accent-line", font=F["btn"],
                   padx=10, pady=3).pack(side="left", padx=(4, 0))
        self.fav_btn = FlatButton(acts, "★" if e.fav else "☆",
                                  command=lambda: self.app.toggle_fav(e, self),
                                  theme=T, style="accent-line", font=F["btn"],
                                  padx=9, pady=3)
        self.fav_btn.pack(side="left", padx=(4, 0))
        FlatButton(acts, "↗", command=lambda: self.app.open_browser(e),
                   theme=T, style="accent-line", font=F["btn"],
                   padx=9, pady=3).pack(side="left", padx=(4, 0))

        # 展开区（多源明细）
        self.detail = tk.Frame(body, bg=T.get("card"))

        self._paint_title()

    # ------------------------------------------------------------ 展开多源
    def toggle_expand(self):
        self.expanded = not self.expanded
        for w in self.detail.winfo_children():
            w.destroy()
        if not self.expanded:
            self.detail.pack_forget()
            if hasattr(self, "multi_btn"):
                self.multi_btn.configure(text="%d 源在报 ▾" % self.entry.cluster.source_count)
            return
        if hasattr(self, "multi_btn"):
            self.multi_btn.configure(text="%d 源在报 ▴" % self.entry.cluster.source_count)
        T, F = self.T, self.fonts
        for it in self.entry.cluster.items:
            row = tk.Frame(self.detail, bg=T.get("card2"))
            row.pack(fill="x", pady=2)
            tk.Label(row, text=it.source, font=F["chip"], bg=T.get("card2"),
                     fg=T.get("tagfg"), width=10, anchor="w").pack(side="left", padx=(33, 6))
            tk.Label(row, text=it.title, font=F["meta"], bg=T.get("card2"),
                     fg=T.get("fg"), anchor="w", justify="left",
                     wraplength=460, cursor="hand2").pack(side="left", fill="x", expand=True)
            row.winfo_children()[-1].bind(
                "<Button-1>", lambda ev, u=it.url: self.app.open_url(u))
        self.detail.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------ 外观
    def _paint_title(self):
        T = self.T
        fg = T.get("sub") if self.entry.read else T.get("fg")
        try:
            self.title_lbl.configure(fg=fg)
        except Exception:                                   # noqa: BLE001
            pass

    def _bind_hover(self, w):
        # 用 add="+" 追加，避免覆盖子控件（按钮 / 标题）自身的悬停行为
        w.bind("<Enter>", lambda e: self._hover(True), add="+")
        w.bind("<Leave>", lambda e: self._hover(False), add="+")
        for c in w.winfo_children():
            self._bind_hover(c)

    def _hover(self, on):
        try:
            bg = self.T.get("hover") if on else self.T.get("card")
            self.configure(bg=bg, highlightbackground=self.T.get("accent") if on
                           else self.T.get("border"))
            self._recolor(self, bg)
            self.rank_lbl.configure(bg=self.T.get("select") if on else self.T.get("card2"))
        except Exception:                                   # noqa: BLE001
            pass

    def _recolor(self, w, bg):
        for c in w.winfo_children():
            try:
                if isinstance(c, tk.Frame):
                    cur = c.cget("bg")
                    if cur != self.T.get("card2"):
                        c.configure(bg=bg)
                elif isinstance(c, tk.Label):
                    cur = c.cget("bg")
                    if cur in (self.T.get("card"), self.T.get("hover")):
                        c.configure(bg=bg)
            except Exception:                               # noqa: BLE001
                pass
            if isinstance(c, tk.Frame):
                self._recolor(c, bg)

    def set_wrap(self, w):
        try:
            self.title_lbl.configure(wraplength=max(180, w))
        except Exception:                                   # noqa: BLE001
            pass

    def set_theme(self, T):
        self.T = T
        self.configure(bg=T.get("card"), highlightbackground=T.get("border"))

    def refresh_marks(self):
        self._paint_title()
        try:
            self.fav_btn.set_text("★" if self.entry.fav else "☆")
        except Exception:                                   # noqa: BLE001
            pass
