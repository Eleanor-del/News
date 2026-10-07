# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 对话框：数据源管理 / 添加数据源 / 设置 / 关于
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from ..config import (APP_NAME, VERSION, data_dir, export_dir)
from ..sources import match_templates, probe_source
from .widgets import Chip, FlatButton, ScrollableFrame

try:
    from urllib.parse import urlparse
except ImportError:                                         # noqa: BLE001
    from urlparse import urlparse                           # noqa: BLE001


class BaseDialog(tk.Toplevel):
    def __init__(self, master, app, title, w=760, h=620):
        tk.Toplevel.__init__(self, master)
        self.app = app
        self.T = app.theme
        self.F = app.fonts
        self.title(title)
        self.geometry("%dx%d" % (w, h))
        self.minsize(int(w * 0.85), int(h * 0.8))
        self.configure(bg=self.T.get("bg"))
        self.transient(master)
        try:
            self.grab_set()
        except Exception:                                   # noqa: BLE001
            pass
        self._center(master)

    def _center(self, master):
        self.update_idletasks()
        try:
            x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
            y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 2
            self.geometry("+%d+%d" % (max(x, 20), max(y, 20)))
        except Exception:                                   # noqa: BLE001
            pass

    # ---------------------------------------------------------- 小工具
    def _section(self, parent, text):
        f = tk.Frame(parent, bg=self.T.get("bg"))
        f.pack(fill="x", padx=22, pady=(16, 6))
        tk.Label(f, text=text, font=self.F["h3"], bg=self.T.get("bg"),
                 fg=self.T.get("accent")).pack(anchor="w")
        return f

    def _row(self, parent, label, widget_side="right"):
        f = tk.Frame(parent, bg=self.T.get("card"))
        f.pack(fill="x", padx=1, pady=1)
        tk.Label(f, text=label, font=self.F["meta"], bg=self.T.get("card"),
                 fg=self.T.get("fg"), width=12, anchor="w").pack(side="left", padx=(14, 8))
        return f


# ===========================================================================
# 数据源管理
# ===========================================================================

class SourceManagerDialog(BaseDialog):
    def __init__(self, master, app):
        BaseDialog.__init__(self, master, app, "数据源管理", 820, 640)
        self.vars = {}
        self._build()
        self.refresh()

    def _build(self):
        T, F = self.T, self.F
        top = tk.Frame(self, bg=T.get("card"))
        top.pack(fill="x")
        top.columnconfigure(0, weight=1)
        tk.Label(top, text="数据源", font=F["h2"], bg=T.get("card"),
                 fg=T.get("fg")).grid(row=0, column=0, sticky="w", padx=20, pady=(14, 2))
        self.tip = tk.Label(top, text="", font=F["meta"], bg=T.get("card"),
                            fg=T.get("sub"))
        self.tip.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))
        btns = tk.Frame(top, bg=T.get("card"))
        btns.grid(row=0, column=1, rowspan=2, sticky="e", padx=20)
        FlatButton(btns, "+ 添加", command=self.add_source, theme=T,
                   style="primary", font=F["btn"], padx=12, pady=6).pack(side="left", padx=4)
        FlatButton(btns, "恢复内置", command=self.restore, theme=T,
                   style="accent-line", font=F["btn"], padx=12, pady=6).pack(side="left", padx=4)
        FlatButton(btns, "全选", command=lambda: self._all(True), theme=T,
                   style="accent-line", font=F["btn"], padx=12, pady=6).pack(side="left", padx=4)
        FlatButton(btns, "全不选", command=lambda: self._all(False), theme=T,
                   style="accent-line", font=F["btn"], padx=12, pady=6).pack(side="left", padx=4)
        FlatButton(btns, "刷新", command=self.refresh, theme=T,
                   style="accent-line", font=F["btn"], padx=12, pady=6).pack(side="left", padx=4)

        self.list = ScrollableFrame(self, bg=T.get("bg"))
        self.list.pack(fill="both", expand=True, padx=16, pady=(6, 10))

        foot = tk.Frame(self, bg=T.get("bg"))
        foot.pack(fill="x", padx=20, pady=(0, 14))
        FlatButton(foot, "关闭", command=self.destroy, theme=T,
                   style="primary", font=F["btn"], padx=18, pady=7).pack(side="right")

    def _all(self, on):
        for sid, v in self.vars.items():
            v.set(on)
            self.app.core.set_source_on(sid, on)
        self.refresh()

    def restore(self):
        self.app.core.restore_builtin()
        self.refresh()
        self.app.toast("已恢复全部内置数据源", "ok")

    def add_source(self):
        AddSourceDialog(self, self.app, on_done=self.refresh)

    def refresh(self):
        for w in self.list.inner.winfo_children():
            w.destroy()
        self.vars = {}
        T, F = self.T, self.F
        core = self.app.core

        for s in core.sources:
            row = tk.Frame(self.list.inner, bg=T.get("card"),
                           highlightthickness=1, highlightbackground=T.get("border"))
            row.pack(fill="x", pady=3, padx=2)

            v = tk.BooleanVar(master=self, value=s.on)
            self.vars[s.id] = v
            cb = tk.Checkbutton(row, variable=v, bg=T.get("card"),
                                activebackground=T.get("card"),
                                selectcolor=T.get("card"),
                                fg=T.get("fg"), highlightthickness=0, bd=0,
                                command=lambda sid=s.id, vv=v: self._toggle(sid, vv))
            cb.pack(side="left", padx=(12, 8))

            info = tk.Frame(row, bg=T.get("card"))
            info.pack(side="left", fill="both", expand=True, pady=8)
            tk.Label(info, text=s.name, font=F["strong"], bg=T.get("card"),
                     fg=T.get("fg"), anchor="w").pack(anchor="w")
            tk.Label(info, text=s.desc or (s.custom.get("url") if s.custom else ""),
                     font=F["mini"], bg=T.get("card"), fg=T.get("sub"),
                     anchor="w").pack(anchor="w", pady=(1, 0))

            # 健康度
            hp = tk.Frame(row, bg=T.get("card"))
            hp.pack(side="left", padx=10)
            color = (T.get("ok") if s.state == "ok" else
                     T.get("danger") if s.state in ("fail", "cooled") else
                     T.get("warn"))
            tk.Label(hp, text="●", bg=T.get("card"), fg=color,
                     font=F["meta"]).pack(side="left")
            st = {"ok": "正常", "fail": "失败", "cooled": "熔断", "testing": "测试中",
                  "idle": "未测"}.get(s.state, s.state)
            detail = "%s · %d条" % (st, s.item_count) if s.state == "ok" else st
            tk.Label(hp, text=detail, font=F["mini"], bg=T.get("card"),
                     fg=T.get("sub")).pack(side="left", padx=(4, 0))

            Chip(hp, s.category, T, kind="cat", font=F["mini"]).pack(side="left", padx=(10, 0))
            if not s.builtin:
                Chip(hp, "自定义", T, kind="source", font=F["mini"]).pack(side="left", padx=(6, 0))

            acts = tk.Frame(row, bg=T.get("card"))
            acts.pack(side="right", padx=12)
            FlatButton(acts, "删除", command=lambda sid=s.id: self._remove(sid),
                       theme=T, style="danger", font=F["mini"], padx=9, pady=3
                       ).pack(side="left", padx=(6, 0))

        self.list.refresh_wheel()
        self.tip.configure(
            text="共 %d 个源，启用 %d 个。取消勾选即停用；连续失败的源会自动熔断冷却。"
                 % (len(core.sources), len(core.enabled_sources())))

    def _toggle(self, sid, v):
        self.app.core.set_source_on(sid, v.get())

    def _remove(self, sid):
        s = self.app.core.find_source(sid)
        if not s:
            return
        if not messagebox.askyesno("删除数据源",
                                   "确定删除「%s」？\n内置源可在「恢复内置」中找回。" % s.name,
                                   parent=self):
            return
        self.app.core.remove_source(sid)
        self.refresh()
        self.app.toast("已删除 %s" % s.name, "ok")


# ===========================================================================
# 添加数据源
# ===========================================================================

class AddSourceDialog(BaseDialog):
    def __init__(self, master, app, on_done=None):
        self.on_done = on_done
        BaseDialog.__init__(self, master, app, "添加数据源", 720, 620)
        self.selected = {}
        self._build()

    def _build(self):
        T, F = self.T, self.F
        head = tk.Frame(self, bg=T.get("card"))
        head.pack(fill="x", padx=16, pady=16)
        tk.Label(head, text="关键词或网址", font=F["h3"], bg=T.get("card"),
                 fg=T.get("accent")).pack(anchor="w", padx=16, pady=(14, 6))

        line = tk.Frame(head, bg=T.get("card"))
        line.pack(fill="x", padx=16, pady=(0, 8))
        self.q = tk.StringVar(master=self)
        ent = tk.Entry(line, textvariable=self.q, font=F["body"],
                       bg=T.get("input"), fg=T.get("fg"), relief="flat",
                       insertbackground=T.get("accent"))
        ent.pack(side="left", fill="x", expand=True, ipady=7)
        ent.bind("<Return>", lambda e: self.search())
        FlatButton(line, "匹配", command=self.search, theme=T, style="primary",
                   font=F["btn"], padx=16, pady=6).pack(side="left", padx=(8, 0))

        self.hint = tk.Label(head, text="输入「科技」「财经」「虎扑」等关键词，或直接粘贴 RSS / JSON 地址",
                             font=F["mini"], bg=T.get("card"), fg=T.get("sub"))
        self.hint.pack(anchor="w", padx=16, pady=(0, 14))

        self.list = ScrollableFrame(self, bg=T.get("bg"))
        self.list.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        foot = tk.Frame(self, bg=T.get("bg"))
        foot.pack(fill="x", padx=20, pady=(0, 14))
        FlatButton(foot, "取消", command=self.destroy, theme=T,
                   style="accent-line", font=F["btn"], padx=16, pady=7).pack(side="right")
        FlatButton(foot, "添加选中", command=self.commit, theme=T,
                   style="primary", font=F["btn"], padx=16, pady=7).pack(side="right", padx=8)

        self.q.set("")
        self.search()

    def search(self):
        for w in self.list.inner.winfo_children():
            w.destroy()
        T, F = self.T, self.F
        q = self.q.get().strip()
        tmpl, is_rec = match_templates(q, self.app.core.sources)

        if not q:
            tmpl, is_rec = match_templates("推荐", self.app.core.sources)
            self.hint.configure(text="以下是根据你已启用板块推荐的常用数据源")
        else:
            self.hint.configure(text=("未找到完全匹配的源，以下是同类推荐" if is_rec
                                      else "为你匹配到 %d 个候选源" % len(tmpl)))

        self.selected = {}
        for t in tmpl:
            v = tk.BooleanVar(master=self, value=False)
            self.selected[t["name"]] = (v, t)
            row = tk.Frame(self.list.inner, bg=T.get("card"),
                           highlightthickness=1, highlightbackground=T.get("border"))
            row.pack(fill="x", pady=3, padx=2)
            tk.Checkbutton(row, variable=v, bg=T.get("card"), fg=T.get("fg"),
                           activebackground=T.get("card"), selectcolor=T.get("card"),
                           bd=0, highlightthickness=0).pack(side="left", padx=(12, 8))
            box = tk.Frame(row, bg=T.get("card"))
            box.pack(side="left", fill="both", expand=True, pady=8)
            tk.Label(box, text=t["name"], font=F["strong"], bg=T.get("card"),
                     fg=T.get("fg"), anchor="w").pack(anchor="w")
            tk.Label(box, text=t["url"], font=F["mini"], bg=T.get("card"),
                     fg=T.get("sub"), anchor="w").pack(anchor="w")
            Chip(box, t["category"], T, kind="cat", font=F["mini"]).pack(anchor="w", pady=(3, 0))

            FlatButton(row, "测试", command=lambda tt=t: self._probe(tt), theme=T,
                       style="accent-line", font=F["mini"], padx=10, pady=3
                       ).pack(side="right", padx=12)

        # 自定义 URL
        cust = tk.Frame(self.list.inner, bg=T.get("bg"))
        cust.pack(fill="x", pady=14)
        tk.Label(cust, text="自定义地址（自动探测类型）", font=F["h3"], bg=T.get("bg"),
                 fg=T.get("accent")).pack(anchor="w", pady=(0, 6))
        line = tk.Frame(cust, bg=T.get("card"))
        line.pack(fill="x")
        self.url = tk.StringVar(master=self)
        self.cname = tk.StringVar(master=self)
        tk.Entry(line, textvariable=self.url, font=F["body"], bg=T.get("input"),
                 fg=T.get("fg"), relief="flat",
                 insertbackground=T.get("accent")).pack(side="left", fill="x",
                                                        expand=True, ipady=6, padx=12, pady=10)
        tk.Entry(line, textvariable=self.cname, font=F["body"], bg=T.get("input"),
                 fg=T.get("fg"), relief="flat", width=12,
                 insertbackground=T.get("accent")).pack(side="left", ipady=6, padx=(0, 8))
        FlatButton(line, "探测并添加", command=self._probe_custom, theme=T,
                   style="primary", font=F["btn"], padx=14, pady=6).pack(side="left", padx=(0, 12))

        self.list.refresh_wheel()

    def _probe(self, t):
        self.app.toast("正在探测 %s …" % t["name"])
        def work():
            mode, n, desc = probe_source(t["url"], t["name"])
            self.after(0, lambda: messagebox.showinfo(
                "探测结果", "%s\n\n类型：%s\n%s" % (t["name"], mode, desc), parent=self))
        threading.Thread(target=work, daemon=True).start()

    def _probe_custom(self):
        url = self.url.get().strip()
        if not url:
            self.app.toast("请先填写地址", "warn")
            return
        if not url.startswith("http"):
            url = "https://" + url
        name = self.cname.get().strip() or self._guess_name(url)

        def work():
            mode, n, desc = probe_source(url, name)
            self.after(0, lambda: self._add_custom(url, name, mode, n, desc))
        self.app.toast("正在探测…")
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _guess_name(url):
        try:
            host = urlparse(url).netloc.lower()
        except Exception:                                   # noqa: BLE001
            return "自定义源"
        host = host.split(":")[0]
        for pre in ("www.", "news.", "finance.", "sports.", "mil.", "bbs.", "api."):
            if host.startswith(pre):
                host = host[len(pre):]
        return host.split(".")[0].upper() if host else "自定义源"

    def _add_custom(self, url, name, mode, n, desc):
        if n == 0 and "失败" in desc:
            messagebox.showwarning("探测结果", "无法解析该地址：\n%s" % desc, parent=self)
            return
        d = dict(id="custom_%d" % (abs(hash(url)) % 10 ** 8), name=name, url=url,
                 mode=mode, category="自定义")
        ok = self.app.core.add_custom_source(d)
        if ok:
            self.app.toast("已添加 %s（%s）" % (name, desc), "ok")
            if self.on_done:
                self.on_done()
            self.destroy()
        else:
            self.app.toast("该地址已存在", "warn")

    def commit(self):
        added = 0
        for name, (v, t) in self.selected.items():
            if not v.get():
                continue
            d = dict(id="custom_%s" % abs(hash(t["url"])) % 10 ** 8,
                     name=t["name"], url=t["url"], mode=t["mode"],
                     category=t["category"])
            if self.app.core.add_custom_source(d):
                added += 1
        self.app.toast("已添加 %d 个数据源" % added, "ok" if added else "warn")
        if added and self.on_done:
            self.on_done()
        self.destroy()


# ===========================================================================
# 设置
# ===========================================================================

class SettingsDialog(BaseDialog):
    def __init__(self, master, app):
        BaseDialog.__init__(self, master, app, "设置", 700, 660)
        self._build()

    def _build(self):
        T, F = self.T, self.F
        wrap = ScrollableFrame(self, bg=T.get("bg"))
        wrap.pack(fill="both", expand=True)
        inner = wrap.inner
        core = self.app.core

        # ---- 外观
        self._section(inner, "外观")
        card = tk.Frame(inner, bg=T.get("card"))
        card.pack(fill="x", padx=20)

        r = self._row(card, "主题")
        from ..theme import THEME_NAMES
        for nm in THEME_NAMES:
            FlatButton(r, nm, command=lambda n=nm: self._theme(n), theme=T,
                       style="subtle", font=F["mini"], padx=9, pady=5
                       ).pack(side="left", padx=3, pady=8)

        r = self._row(card, "列表布局")
        for nm, val in (("单列", "single"), ("双列", "double")):
            FlatButton(r, nm, command=lambda v=val: self._layout(v), theme=T,
                       style="subtle", font=F["mini"], padx=12, pady=5
                       ).pack(side="left", padx=3, pady=8)

        r = self._row(card, "显示密度")
        for nm, val in (("舒适", "comfortable"), ("紧凑", "compact")):
            FlatButton(r, nm, command=lambda v=val: self._density(v), theme=T,
                       style="subtle", font=F["mini"], padx=12, pady=5
                       ).pack(side="left", padx=3, pady=8)

        r = self._row(card, "自动刷新")
        from ..config import REFRESH_OPTIONS
        for nm, val in REFRESH_OPTIONS:
            FlatButton(r, nm, command=lambda v=val: self._refresh(v), theme=T,
                       style="subtle", font=F["mini"], padx=10, pady=5
                       ).pack(side="left", padx=3, pady=8)

        # ---- 订阅
        self._section(inner, "关键词订阅")
        card2 = tk.Frame(inner, bg=T.get("card"))
        card2.pack(fill="x", padx=20)
        line = tk.Frame(card2, bg=T.get("card"))
        line.pack(fill="x", padx=14, pady=12)
        self.kw = tk.StringVar(master=self)
        tk.Entry(line, textvariable=self.kw, font=F["body"], bg=T.get("input"),
                 fg=T.get("fg"), relief="flat",
                 insertbackground=T.get("accent")).pack(side="left", fill="x",
                                                        expand=True, ipady=6)
        FlatButton(line, "添加", command=self._add_sub, theme=T, style="primary",
                   font=F["btn"], padx=14, pady=6).pack(side="left", padx=(8, 0))

        self.sub_box = tk.Frame(card2, bg=T.get("card"))
        self.sub_box.pack(fill="x", padx=14, pady=(0, 12))
        self._render_subs()

        # ---- 数据
        self._section(inner, "数据与存储")
        card3 = tk.Frame(inner, bg=T.get("card"))
        card3.pack(fill="x", padx=20)
        st = core.stats
        r = self._row(card3, "归档统计")
        tk.Label(r, text="历史条目 %d · 收藏 %d · 快照 %d 次 · 数据库 %.1f MB" %
                 (st.get("items", 0), st.get("favorites", 0),
                  st.get("snapshots", 0), st.get("size_mb", 0)),
                 font=F["mini"], bg=T.get("card"), fg=T.get("sub")
                 ).pack(side="left", pady=10)

        r = self._row(card3, "数据位置")
        FlatButton(r, "打开目录", command=self._open_dir, theme=T,
                   style="accent-line", font=F["mini"], padx=12, pady=5
                   ).pack(side="left", pady=8)

        r = self._row(card3, "历史归档")
        FlatButton(r, "清理 30 天前", command=self._prune, theme=T,
                   style="accent-line", font=F["mini"], padx=12, pady=5
                   ).pack(side="left", pady=8)
        FlatButton(r, "清空全部", command=self._clear, theme=T,
                   style="danger", font=F["mini"], padx=12, pady=5
                   ).pack(side="left", padx=8, pady=8)

        tk.Label(inner, text="%s v%s　·　数据源 %d 个" % (APP_NAME, VERSION,
                                                        len(core.sources)),
                 font=F["mini"], bg=T.get("bg"), fg=T.get("weak")).pack(pady=18)

        wrap.refresh_wheel()

    def _render_subs(self):
        for w in self.sub_box.winfo_children():
            w.destroy()
        T, F = self.T, self.F
        subs = self.app.core.subs
        if not subs:
            tk.Label(self.sub_box, text="暂无订阅。添加后，命中的热点会打上「★ 关注」并自动置顶。",
                     font=F["mini"], bg=T.get("card"), fg=T.get("sub"),
                     anchor="w").pack(anchor="w", pady=4)
            return
        for kw in subs:
            chip = Chip(self.sub_box, "%s  ×" % kw, T, kind="source", font=F["mini"],
                        cursor="hand2")
            chip.pack(side="left", padx=(0, 6), pady=2)
            chip.bind("<Button-1>", lambda e, k=kw: self._del_sub(k))

    def _add_sub(self):
        kw = self.kw.get().strip()
        if not kw:
            return
        if self.app.core.add_sub(kw):
            self.kw.set("")
            self._render_subs()
            self.app.refresh_view()
            self.app.toast("已订阅「%s」" % kw, "ok")

    def _del_sub(self, kw):
        self.app.core.remove_sub(kw)
        self._render_subs()
        self.app.refresh_view()

    def _theme(self, name):
        self.app.apply_theme(name)
        self.destroy()

    def _layout(self, v):
        self.app.core.set("layout", v)
        self.app.render()

    def _density(self, v):
        self.app.core.set("density", v)
        self.app.render()

    def _refresh(self, v):
        self.app.set_auto_refresh(int(v))

    def _open_dir(self):
        d = data_dir()
        try:
            if os.name == "nt":
                os.startfile(d)                             # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:                              # noqa: BLE001
            messagebox.showerror("打开失败", "%s" % e, parent=self)

    def _prune(self):
        self.app.core.store.prune()
        self.app.toast("已清理 30 天前的历史", "ok")

    def _clear(self):
        if not messagebox.askyesno("清空数据",
                                   "将删除全部历史归档、收藏与热度记录，且不可恢复。\n确定继续？",
                                   parent=self):
            return
        self.app.core.store.clear_all()
        self.app.toast("已清空全部数据", "ok")


# ===========================================================================
# 关于
# ===========================================================================

class AboutDialog(BaseDialog):
    def __init__(self, master, app):
        BaseDialog.__init__(self, master, app, "关于", 560, 460)
        T, F = self.T, self.F
        card = tk.Frame(self, bg=T.get("card"))
        card.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(card, text=APP_NAME, font=F["h1"], bg=T.get("card"),
                 fg=T.get("accent")).pack(pady=(26, 2))
        tk.Label(card, text="v%s" % VERSION, font=F["meta"], bg=T.get("card"),
                 fg=T.get("sub")).pack()

        feats = [
            "秒开体验 —— 本地归档即时渲染，后台静默刷新",
            "跨源聚合 —— 同一事件多平台报道合并为一条",
            "全文检索 —— 历史热点可回溯、可搜索",
            "趋势监控 —— 新上榜 / 飙升 / 降温一目了然",
            "关键词订阅 —— 命中即高亮置顶",
            "明暗主题 —— 8 套配色随时切换",
        ]
        box = tk.Frame(card, bg=T.get("card"))
        box.pack(fill="both", expand=True, padx=30, pady=18)
        for f in feats:
            tk.Label(box, text="· " + f, font=F["meta"], bg=T.get("card"),
                     fg=T.get("fg"), anchor="w", justify="left").pack(fill="x", pady=3)

        tk.Label(card, text="导出目录：%s" % export_dir(), font=F["mini"],
                 bg=T.get("card"), fg=T.get("weak")).pack(pady=(0, 14))
        FlatButton(card, "关闭", command=self.destroy, theme=T, style="primary",
                   font=F["btn"], padx=20, pady=7).pack(pady=(0, 20))
