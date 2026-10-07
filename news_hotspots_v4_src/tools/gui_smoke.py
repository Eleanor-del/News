# -*- coding: utf-8 -*-
"""
界面冒烟测试：真实创建 Tk 窗口，跑一遍主要交互，捕获所有回调异常。

    python tools/gui_smoke.py
"""

import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ERRORS = []
STEPS = []


def ok(name, cond, detail=""):
    STEPS.append((name, cond, detail))
    print("  [%s] %s%s" % ("OK" if cond else "!!", name, ("  → " + detail) if detail else ""))


def main():
    import tkinter as tk
    from nhv4.ui.app import HotspotsApp
    from nhv4.ui.dialogs import AboutDialog, SettingsDialog, SourceManagerDialog

    root = tk.Tk()
    root.withdraw()          # 先隐藏，避免闪烁
    root.report_callback_exception = lambda *a: ERRORS.append("".join(traceback.format_exception(*a)))

    app = HotspotsApp(root)
    root.deiconify()
    root.geometry("1200x800+60+60")

    state = {"waited": 0}

    def wait_refresh():
        state["waited"] += 300
        if app.core.refreshing and state["waited"] < 30000:
            root.after(300, wait_refresh)
            return
        step_render()

    def step_render():
        n = len(app.cards)
        ok("首屏渲染出卡片", n > 10, "%d 张卡片" % n)
        ok("事件簇数量合理", len(app.core.entries) > 20, "%d 簇" % len(app.core.entries))
        ok("状态栏有内容", bool(app.status_var.get()), app.status_var.get()[:46])
        root.after(200, step_board)

    def step_board():
        try:
            target = next((b for b in app.boards if b not in ("全部", "归档", "收藏", "订阅")), "全部")
            app.set_board(target)
            ok("切换板块", True, "%s → %d 张卡片" % (target, len(app.cards)))
            app.set_board("收藏")
            ok("切换到收藏夹（空态）", True)
            app.set_board("归档")
            ok("切换到归档", True, "%d 张卡片" % len(app.cards))
            app.set_board("全部")
        except Exception:                                   # noqa: BLE001
            ERRORS.append(traceback.format_exc())
        root.after(150, step_search)

    def step_search():
        try:
            app.search_var.set("中国")
            app.refresh_view()
            ok("关键词过滤", True, "%d 张卡片" % len(app.cards))
            app.search_var.set("")
            app.refresh_view()
        except Exception:                                   # noqa: BLE001
            ERRORS.append(traceback.format_exc())
        root.after(150, step_layout)

    def step_layout():
        try:
            app.toggle_layout()
            ok("切换双列布局", len(app.cards) >= 0, "%d 张" % len(app.cards))
            app.toggle_layout()
            app.set_sort("heat")
            ok("切换排序", True)
            app.set_sort("rank")
        except Exception:                                   # noqa: BLE001
            ERRORS.append(traceback.format_exc())
        root.after(200, step_theme)

    def step_theme():
        try:
            app.apply_theme("午夜蓝")
            ok("应用深色主题", app.theme.get("dark") is True, app.theme_name)
            ok("换肤后仍有卡片", len(app.cards) > 5, "%d 张" % len(app.cards))
            app.apply_theme("清爽蓝")
            ok("切回浅色主题", app.theme.get("dark") is False)
        except Exception:                                   # noqa: BLE001
            ERRORS.append(traceback.format_exc())
        root.after(250, step_dialogs)

    def step_dialogs():
        for cls, name in ((SourceManagerDialog, "数据源管理"),
                          (SettingsDialog, "设置"),
                          (AboutDialog, "关于")):
            try:
                d = cls(root, app)
                root.update_idletasks()
                d.destroy()
                ok("打开%s对话框" % name, True)
            except Exception:                               # noqa: BLE001
                ERRORS.append(traceback.format_exc())
                ok("打开%s对话框" % name, False)
        root.after(150, step_fav)

    def step_fav():
        try:
            if app.cards:
                c = app.cards[0]
                app.toggle_fav(c.entry, c)
                ok("收藏/取消收藏", True)
                app.toggle_fav(c.entry, c)
            app.core.add_sub("测试关键词")
            app.refresh_view()
            ok("添加订阅并刷新", True)
            app.core.remove_sub("测试关键词")
        except Exception:                                   # noqa: BLE001
            ERRORS.append(traceback.format_exc())
        root.after(150, step_export)

    def step_export():
        try:
            tmp = tempfile.mkdtemp(prefix="nhv4_gui_")
            p = os.path.join(tmp, "t.html")
            from nhv4.export import export
            export("html", app.view_entries()[:40], p)
            ok("导出 HTML", os.path.getsize(p) > 500, "%d 字节" % os.path.getsize(p))
        except Exception:                                   # noqa: BLE001
            ERRORS.append(traceback.format_exc())
            ok("导出 HTML", False)
        root.after(150, finish)

    def finish():
        try:
            app.on_close()
        except Exception:                                   # noqa: BLE001
            pass
        try:
            root.destroy()
        except Exception:                                   # noqa: BLE001
            pass

    root.after(400, wait_refresh)
    root.mainloop()

    print("\n" + "=" * 66)
    passed = sum(1 for _, c, _ in STEPS if c)
    print("界面步骤：%d/%d 通过" % (passed, len(STEPS)))
    if ERRORS:
        print("\n捕获到 %d 个异常：" % len(ERRORS))
        for e in ERRORS[:6]:
            print("-" * 60)
            print(e[:1400])
    else:
        print("未捕获到任何界面异常 ✓")
    print("=" * 66)
    return 1 if (ERRORS or passed != len(STEPS)) else 0


if __name__ == "__main__":
    sys.exit(main())
