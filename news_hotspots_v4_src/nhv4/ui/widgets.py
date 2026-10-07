# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 自定义控件

Tkinter 原生控件外观偏旧，这里实现一组可以完全按主题着色的轻量控件：
- ScrollableFrame：Canvas 滚动容器，支持平滑滚轮，子控件自动接管滚轮
- FlatButton  ：无边框扁平按钮（primary / ghost / subtle / danger）
- Chip        ：来源 / 分类小标签
- Toast       ：右下角轻提示
- Bar         ：细进度条
"""

import tkinter as tk


# ---------------------------------------------------------------------------
# 平滑滚动容器
# ---------------------------------------------------------------------------

class ScrollableFrame(tk.Frame):
    """带滚轮的滚动区域；子控件会自动继承滚轮事件"""

    def __init__(self, master, bg="#ffffff", **kw):
        tk.Frame.__init__(self, master, bg=bg, **kw)
        self.bg = bg

        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.vsb = tk.Frame(self, width=0, bg=bg)      # 用细条自绘滚动条更贴合主题
        self.vsb.pack(side="right", fill="y")
        self.vsb.pack_propagate(False)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self._bind_tree()

        self._target = 0.0
        self._animating = False

    # ---------------------------------------------------------- 布局同步
    def _on_inner(self, _e=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        # 内容区宽度跟随画布，避免横向溢出
        self.canvas.itemconfigure(self._win, width=self.canvas.winfo_width())

    def _on_canvas(self, e=None):
        self.canvas.itemconfigure(self._win, width=(e.width if e else self.canvas.winfo_width()))

    # ---------------------------------------------------------- 滚轮
    def _bind_tree(self, widget=None):
        """递归绑定滚轮：覆盖式绑定，重复调用不会累积"""
        w = widget or self.inner
        try:
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>", self._on_wheel)
            w.bind("<Button-5>", self._on_wheel)
        except Exception:                                   # noqa: BLE001
            pass
        for c in w.winfo_children():
            self._bind_tree(c)

    def refresh_wheel(self):
        """渲染完子控件后调用，让新控件也能响应滚轮"""
        self._bind_tree()

    def _on_wheel(self, event):
        num = getattr(event, "num", 0)
        if num == 4:
            delta = -3
        elif num == 5:
            delta = 3
        else:
            d = getattr(event, "delta", 0)
            if not d:
                return "break"
            delta = int(-d / 120.0) * 3
            if delta == 0:
                delta = -1 if d > 0 else 1
        self.canvas.yview_scroll(delta, "units")
        return "break"

    # ---------------------------------------------------------- 其他
    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()

    def scroll_top(self):
        self.canvas.yview_moveto(0.0)

    def set_bg(self, bg):
        self.bg = bg
        self.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.inner.configure(bg=bg)
        self.vsb.configure(bg=bg)


# ---------------------------------------------------------------------------
# 扁平按钮
# ---------------------------------------------------------------------------

class FlatButton(tk.Label):
    """
    用 Label 模拟的按钮：可完全控制前景/背景/圆角感，
    比 ttk.Button 更容易跟随主题换色。
    """

    STYLES = ("primary", "ghost", "subtle", "danger", "accent-line")

    def __init__(self, master, text="", command=None, theme=None, style="ghost",
                 font=None, padx=14, pady=7, width=None, anchor="center",
                 active=None, **kw):
        self.T = theme or {}
        self.style = style
        self.command = command
        self._enabled = True
        self.font = font
        self._padx, self._pady = padx, pady
        self._user_bg = active
        tk.Label.__init__(self, master, text=text, font=font, cursor="hand2",
                          padx=padx, pady=pady, width=width, anchor=anchor, **kw)
        self._paint(False)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self._paint(True))
        self.bind("<Leave>", lambda e: self._paint(False))
        self.bind("<ButtonRelease-1>", lambda e: self._paint(True))

    # ---------------------------------------------------------- 配色
    def _colors(self, hover):
        T = self.T
        if self.style == "primary":
            base = T.get("accent", "#3b82f6")
            fg = T.get("onaccent", "#fff")
            return (self._darken(base, 0.10) if hover else base), fg
        if self.style == "danger":
            base = T.get("danger", "#ef4444")
            return (self._darken(base, 0.10) if hover else base), "#ffffff"
        if self.style == "subtle":
            base = T.get("tag", "#eff6ff")
            fg = T.get("tagfg", "#2563eb")
            return (T.get("select", base) if hover else base), fg
        if self.style == "accent-line":
            base = T.get("panel", "#f8fafc")
            fg = T.get("accent", "#3b82f6")
            return (T.get("hover", base) if hover else base), fg
        # ghost
        base = self._user_bg or T.get("panel", "#f8fafc")
        fg = T.get("fg", "#1f2937")
        return (T.get("hover", "#f1f5f9") if hover else base), fg

    @staticmethod
    def _darken(hexcolor, amount=0.1):
        try:
            h = hexcolor.lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            f = 1 - amount
            return "#%02x%02x%02x" % (int(r * f), int(g * f), int(b * f))
        except Exception:                                   # noqa: BLE001
            return hexcolor

    def _paint(self, hover):
        if not self._enabled:
            self.configure(bg=self.T.get("panel", "#f8fafc"), fg=self.T.get("weak", "#94a3b8"))
            return
        bg, fg = self._colors(hover)
        self.configure(bg=bg, fg=fg)

    # ---------------------------------------------------------- 行为
    def _click(self, _e=None):
        if not self._enabled:
            return
        if self.command:
            self.command()

    def set_theme(self, T):
        self.T = T
        self._paint(False)

    def set_text(self, t):
        self.configure(text=t)

    def set_enabled(self, on):
        self._enabled = on
        self.configure(cursor="hand2" if on else "arrow")
        self._paint(False)


# ---------------------------------------------------------------------------
# 小标签
# ---------------------------------------------------------------------------

class Chip(tk.Label):
    def __init__(self, master, text="", theme=None, kind="tag", font=None, **kw):
        self.T = theme or {}
        self.kind = kind
        tk.Label.__init__(self, master, text=text, font=font, padx=7, pady=2, **kw)
        self.paint()

    def paint(self):
        T, k = self.T, self.kind
        if k == "source":
            bg, fg = T.get("tag", "#eff6ff"), T.get("tagfg", "#2563eb")
        elif k == "multi":
            bg, fg = T.get("accent", "#3b82f6"), T.get("onaccent", "#fff")
        elif k == "new":
            bg, fg = T.get("accent", "#3b82f6"), T.get("onaccent", "#fff")
        elif k == "surge":
            bg, fg = T.get("danger", "#ef4444"), "#fff"
        elif k == "up":
            bg, fg = T.get("warn", "#f59e0b"), "#fff"
        elif k == "down" or k == "drop":
            bg, fg = T.get("select", "#e2e8f0"), T.get("sub", "#64748b")
        elif k == "heat":
            bg, fg = T.get("card2", "#f7f9fc"), T.get("sub", "#64748b")
        elif k == "cat":
            bg, fg = T.get("select", "#e2e8f0"), T.get("sub", "#64748b")
        else:
            bg, fg = T.get("tag", "#eff6ff"), T.get("tagfg", "#2563eb")
        self.configure(bg=bg, fg=fg)

    def set_theme(self, T):
        self.T = T
        self.paint()


# ---------------------------------------------------------------------------
# 分隔线 / 细进度条
# ---------------------------------------------------------------------------

class Separator(tk.Frame):
    def __init__(self, master, color="#e2e8f0", height=1):
        tk.Frame.__init__(self, master, bg=color, height=height)
        self.configure(highlightthickness=0)


class Bar(tk.Frame):
    """细进度条，value 为 0~1；<0 表示不确定模式"""

    def __init__(self, master, theme=None, height=3):
        self.T = theme or {}
        tk.Frame.__init__(self, master, bg=self.T.get("border", "#e2e8f0"), height=height)
        self.pack_propagate(False)
        self.fill = tk.Frame(self, bg=self.T.get("accent", "#3b82f6"), width=0, height=height)
        self.fill.place(x=0, y=0, relheight=1.0, width=0)
        self.value = 0.0

    def set(self, v):
        w = self.winfo_width() or 1
        if v is None or v < 0:
            self.fill.configure(bg=self.T.get("accent2", "#22d3ee"))
            self.fill.place(width=int(w))
            return
        v = max(0.0, min(1.0, v))
        self.fill.configure(bg=self.T.get("accent", "#3b82f6"))
        self.fill.place(width=int(w * v))

    def set_theme(self, T):
        self.T = T
        self.configure(bg=T.get("border", "#e2e8f0"))
        self.fill.configure(bg=T.get("accent", "#3b82f6"))


# ---------------------------------------------------------------------------
# 轻提示
# ---------------------------------------------------------------------------

class Toast:
    """右下角浮出提示，2.4 秒后自动淡出"""

    def __init__(self, master, theme=None, font=None):
        self.master = master
        self.T = theme or {}
        self.font = font
        self._win = None
        self._job = None

    def __call__(self, msg, kind="info", ms=2400):
        """便捷写法：self.toast("提示", "ok") 等价于 self.toast.show(...)"""
        self.show(msg, kind, ms)

    def show(self, msg, kind="info", ms=2400):
        self.hide()
        T = self.T
        color = {"info": T.get("accent"), "ok": T.get("ok"),
                 "warn": T.get("warn"), "error": T.get("danger")}.get(kind, T.get("accent"))
        top = tk.Toplevel(self.master)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.0)
        except Exception:                                   # noqa: BLE001
            pass
        f = tk.Frame(top, bg=T.get("card"), highlightthickness=1,
                     highlightbackground=T.get("border"))
        f.pack(fill="both", expand=True)
        tk.Frame(f, bg=color, width=4).pack(side="left", fill="y")
        tk.Label(f, text=msg, font=self.font, bg=T.get("card"), fg=T.get("fg"),
                 padx=16, pady=11, justify="left").pack(side="left")
        top.update_idletasks()
        w, h = top.winfo_width(), top.winfo_height()
        x = self.master.winfo_rootx() + self.master.winfo_width() - w - 24
        y = self.master.winfo_rooty() + self.master.winfo_height() - h - 24
        top.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        self._win = top
        self._fade(0.0, 0.97)
        self._job = self.master.after(ms, lambda: self._fade(0.97, 0.0, destroy=True))

    def _fade(self, a, b, destroy=False, steps=8):
        if not self._win:
            return
        try:
            step = (b - a) / steps
            cur = a
            for _ in range(steps):
                cur += step
                self._win.attributes("-alpha", max(0.0, min(1.0, cur)))
                self._win.update_idletasks()
                self._win.after(14)
            if destroy:
                self.hide()
        except Exception:                                   # noqa: BLE001
            self.hide()

    def hide(self):
        if self._job:
            try:
                self.master.after_cancel(self._job)
            except Exception:                               # noqa: BLE001
                pass
            self._job = None
        if self._win:
            try:
                self._win.destroy()
            except Exception:                               # noqa: BLE001
                pass
            self._win = None
