# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 内置阅读器

在软件内直接读正文，不必跳浏览器。正文在后台线程抓取，
抓到之前先显示标题与加载状态，界面不阻塞。
"""

import threading
import tkinter as tk
from tkinter import messagebox

from ..net import extract_article
from .widgets import FlatButton

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except Exception:                                           # noqa: BLE001
    _HAS_PIL = False


class ReaderWindow(tk.Toplevel):
    def __init__(self, master, title, url, source, theme, fonts, on_fav=None):
        tk.Toplevel.__init__(self, master)
        self.T = theme
        self.F = fonts
        self.url = url
        self.on_fav = on_fav
        self._imgs = []
        self._fsize = 12

        self.title("阅读 · 新闻热点速览")
        self.geometry("900x680")
        self.minsize(620, 460)
        self.configure(bg=theme.get("bg"))
        try:
            self.transient(master)
        except Exception:                                   # noqa: BLE001
            pass

        self._build(title, source)
        self._load()

    # ------------------------------------------------------------ 骨架
    def _build(self, title, source):
        T, F = self.T, self.F
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # 顶部
        head = tk.Frame(self, bg=T.get("card"))
        head.grid(row=0, column=0, sticky="ew")
        head.columnconfigure(0, weight=1)

        tk.Label(head, text=title, font=F["reader_title"], bg=T.get("card"),
                 fg=T.get("fg"), wraplength=800, justify="left",
                 anchor="w").grid(row=0, column=0, sticky="w", padx=20, pady=(16, 4))

        sub = tk.Frame(head, bg=T.get("card"))
        sub.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 12))
        tk.Label(sub, text=source, font=F["meta"], bg=T.get("tag"),
                 fg=T.get("tagfg"), padx=8, pady=2).pack(side="left")
        self.status = tk.Label(sub, text="正在加载正文…", font=F["meta"],
                               bg=T.get("card"), fg=T.get("sub"))
        self.status.pack(side="left", padx=10)

        # 工具条
        bar = tk.Frame(self, bg=T.get("panel"))
        bar.grid(row=1, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        left = tk.Frame(bar, bg=T.get("panel"))
        left.grid(row=0, column=0, sticky="w", padx=14, pady=8)
        FlatButton(left, "A−", command=lambda: self._font(-1), theme=T,
                   style="accent-line", font=F["btn"], padx=10, pady=3
                   ).pack(side="left", padx=(0, 6))
        FlatButton(left, "A+", command=lambda: self._font(1), theme=T,
                   style="accent-line", font=F["btn"], padx=10, pady=3
                   ).pack(side="left", padx=(0, 6))
        FlatButton(left, "复制正文", command=self._copy, theme=T,
                   style="accent-line", font=F["btn"], padx=10, pady=3
                   ).pack(side="left", padx=(0, 6))
        if self.on_fav:
            FlatButton(left, "收藏", command=self._fav, theme=T,
                       style="accent-line", font=F["btn"], padx=10, pady=3
                       ).pack(side="left", padx=(0, 6))
        right = tk.Frame(bar, bg=T.get("panel"))
        right.grid(row=0, column=1, sticky="e", padx=14, pady=8)
        FlatButton(right, "浏览器打开", command=self._browser, theme=T,
                   style="primary", font=F["btn"], padx=12, pady=3).pack(side="left")

        # 正文
        wrap = tk.Frame(self, bg=T.get("bg"))
        wrap.grid(row=2, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)

        self.text = tk.Text(wrap, wrap="word", bg=T.get("card"), fg=T.get("fg"),
                            insertontime=0, relief="flat", bd=0,
                            padx=28, pady=20, spacing1=6, spacing3=10,
                            font=(self.F["body_family"], self._fsize))
        self.text.configure(state="disabled")
        sb = tk.Scrollbar(wrap, command=self.text.yview, width=10)
        self.text.configure(yscrollcommand=sb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self.text.tag_configure("p", spacing1=8, spacing3=10,
                                lmargin1=6, lmargin2=6, rmargin=6)
        self.text.tag_configure("img", justify="center", spacing1=14, spacing3=14)

        self._write("正在加载正文…\n", clear=True)

    # ------------------------------------------------------------ 抓取
    def _load(self):
        def work():
            paras, imgs, vids, err, note = extract_article(self.url)
            self.after(0, lambda: self._render(paras, imgs, vids, err, note))
        if not self.url:
            self._render(None, [], [], "该条目无原文链接", "")
            return
        threading.Thread(target=work, daemon=True).start()

    def _render(self, paras, imgs, vids, err, note=""):
        if err:
            self.status.configure(text=err)
            self._write("\n" + err + "\n\n可点击右上角「浏览器打开」查看原文。", clear=True)
            return
        self._write("", clear=True)
        n = 0
        for p in paras:
            self._write(p + "\n\n", tag="p")
            n += len(p)
        self.status.configure(
            text=("正文约 %d 字 · %s" % (n, note)) if note else ("正文约 %d 字" % n))
        if note:
            self._write("\n（%s）\n" % note, tag="p")
        if imgs and _HAS_PIL:
            self._load_images(imgs)
        elif imgs:
            self._write("（原文含 %d 张图片，安装 Pillow 后可在此显示）\n" % len(imgs))

    def _load_images(self, imgs):
        def work():
            import requests
            from io import BytesIO
            from ..config import HEADERS
            for u in imgs[:3]:
                try:
                    r = requests.get(u, headers=HEADERS, timeout=8)
                    im = Image.open(BytesIO(r.content)).convert("RGB")
                    w, h = im.size
                    maxw = 760
                    if w > maxw:
                        im = im.resize((maxw, max(1, int(h * maxw / w))), Image.LANCZOS)
                    self.after(0, lambda im=im: self._insert_image(im))
                except Exception:                           # noqa: BLE001
                    continue
        threading.Thread(target=work, daemon=True).start()

    def _insert_image(self, im):
        try:
            photo = ImageTk.PhotoImage(im)
            self._imgs.append(photo)          # 持有引用，防止被 GC
            self.text.configure(state="normal")
            self.text.insert("end", "\n")
            self.text.image_create("end", image=photo)
            self.text.insert("end", "\n\n")
            self.text.configure(state="disabled")
        except Exception:                                   # noqa: BLE001
            pass

    # ------------------------------------------------------------ 工具
    def _write(self, s, clear=False, tag=None):
        self.text.configure(state="normal")
        if clear:
            self.text.delete("1.0", "end")
        if s:
            self.text.insert("end", s, (tag,) if tag else None)
        self.text.configure(state="disabled")
        self.text.see("1.0")

    def _font(self, d):
        self._fsize = max(9, min(24, self._fsize + d))
        self.text.configure(font=(self.F["body_family"], self._fsize))

    def _copy(self):
        body = self.text.get("1.0", "end").strip()
        if not body:
            return
        self.clipboard_clear()
        self.clipboard_append(body)
        try:
            messagebox.showinfo("已复制", "正文已复制到剪贴板", parent=self)
        except Exception:                                   # noqa: BLE001
            pass

    def _fav(self):
        if self.on_fav:
            self.on_fav()

    def _browser(self):
        import webbrowser
        if self.url:
            webbrowser.open(self.url)
