# -*- coding: utf-8 -*-
"""
界面按钮全量点击测试

把主窗口里每一个自定义按钮真的点一遍，任何回调异常都会被记录。
（曾靠它发现 `_popup` 属性覆盖同名方法，导致「主题 / 导出」点了没反应）

    python tools/button_test.py
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk                                        # noqa: E402

# 屏蔽会阻塞的交互：保存对话框 / 打开浏览器 / 消息框
import tkinter.filedialog as _fd                            # noqa: E402
import tkinter.messagebox as _mb                            # noqa: E402
import webbrowser                                           # noqa: E402

_fd.asksaveasfilename = lambda *a, **k: ""
_fd.askopenfilename = lambda *a, **k: ""
webbrowser.open = lambda *a, **k: False
_mb.showinfo = lambda *a, **k: "ok"
_mb.showerror = lambda *a, **k: "ok"
_mb.askyesno = lambda *a, **k: True

ERRORS = []
RESULTS = []


def walk(widget, out):
    for c in widget.winfo_children():
        out.append(c)
        walk(c, out)


def find_buttons(root):
    from nhv4.ui.widgets import FlatButton
    out = []
    walk(root, [])
    allw = []
    walk(root, allw)
    for w in allw:
        if isinstance(w, FlatButton) and getattr(w, "command", None):
            out.append(w)
    return out


def toplevels(root):
    return [c for c in root.winfo_children() if isinstance(c, tk.Toplevel)]


def main():
    from nhv4.ui.app import HotspotsApp

    root = tk.Tk()
    root.withdraw()
    root.report_callback_exception = lambda *a: ERRORS.append(
        "".join(traceback.format_exception(*a)))
    app = HotspotsApp(root)

    state = {"waited": 0}

    def wait():
        state["waited"] += 300
        if app.core.refreshing and state["waited"] < 30000:
            root.after(300, wait)
            return
        run()
    root.after(400, wait)

    def run():
        try:
            btns = find_buttons(root)
            print("主窗口共发现 %d 个按钮" % len(btns))
            for b in btns:
                label = ""
                try:
                    label = b.cget("text")
                except Exception:                           # noqa: BLE001
                    pass
                before = len(toplevels(root))
                try:
                    b.command()
                    root.update_idletasks()
                    opened = len(toplevels(root)) - before
                    RESULTS.append((label, "OK", opened))
                    print("  [OK] %-10s %s" % (label, "（打开了对话框）" if opened else ""))
                except Exception:                           # noqa: BLE001
                    ERRORS.append(traceback.format_exc())
                    RESULTS.append((label, "FAIL", 0))
                    print("  [!!] %-10s 回调抛异常" % label)
                # 关掉所有被打开的窗口，避免堆积
                for t in toplevels(root):
                    try:
                        t.destroy()
                    except Exception:                       # noqa: BLE001
                        pass

            # 专项：主题 / 导出 浮层必须真的弹出来
            for name, fn in (("主题", app.popup_themes), ("导出", app.popup_export)):
                try:
                    fn()
                    root.update_idletasks()
                    ok = app._popup is not None
                    print("  [%s] %s浮层弹出" % ("OK" if ok else "!!", name))
                    if not ok:
                        ERRORS.append("%s 浮层未弹出（app._popup 为空）" % name)
                except Exception:                           # noqa: BLE001
                    ERRORS.append(traceback.format_exc())
                    print("  [!!] %s浮层抛异常" % name)
                finally:
                    app._close_popup()
        finally:
            try:
                app.on_close()
            except Exception:                               # noqa: BLE001
                pass
            try:
                root.destroy()
            except Exception:                               # noqa: BLE001
                pass

    root.mainloop()

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print("\n" + "=" * 60)
    print("按钮：%d 个，成功 %d，失败 %d" % (len(RESULTS), len(RESULTS) - len(fails), len(fails)))
    if ERRORS:
        print("\n捕获到 %d 个异常：" % len(ERRORS))
        for e in ERRORS[:8]:
            print("-" * 56)
            print(e[:900])
    else:
        print("未捕获到任何异常 ✓")
    print("=" * 60)
    return 1 if ERRORS or fails else 0


if __name__ == "__main__":
    sys.exit(main())
