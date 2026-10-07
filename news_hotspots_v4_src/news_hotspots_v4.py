# -*- coding: utf-8 -*-
"""
新闻热点速览 v4.0 —— 程序入口

图形界面（默认）：
    python news_hotspots_v4.py

命令行模式（无需界面，适合脚本 / 定时任务）：
    python news_hotspots_v4.py --cli
    python news_hotspots_v4.py --cli --board 科技 --top 15
    python news_hotspots_v4.py --export html --out 今日热点.html

打包（Windows）：
    pip install pyinstaller requests pillow
    python build.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_cli(args):
    """无界面模式：抓一次，打印到终端"""
    from nhv4.core import AppCore
    from nhv4.fetcher import fetch_blocking

    core = AppCore()
    print("正在抓取 %d 个数据源…" % len(core.enabled_sources()))
    items, results = fetch_blocking(core.sources)
    core.finish_refresh(items)

    bad = [r.source.name for r in results if r.error]
    print("完成：%d 个源成功%s\n" % (len(results) - len(bad),
                                    ("，失败：%s" % "、".join(bad)) if bad else ""))

    board = getattr(args, "board", None)
    entries = core.view(board=board) if board else core.entries
    top = getattr(args, "top", 20) or 20

    for e in entries[:top]:
        c = e.cluster
        tag = ("[%s] " % e.trend.label) if e.trend.label else ""
        src = ("%d源 " % c.source_count) if c.source_count > 1 else ""
        heat = ("  🔥%s" % c.heat_display) if c.heat_display else ""
        print("%3d. %s%s%s%s  (%s)" % (e.rank, tag, src, c.title, heat,
                                       "、".join(c.sources[:4])))
    print("\n共 %d 个事件（原始 %d 条，来自 %d 个源）"
          % (len(core.entries), len(items), len(core.enabled_sources())))

    if getattr(args, "out", None):
        from nhv4.export import export
        fmt = getattr(args, "export", "html") or "html"
        path = export(fmt, core.entries, args.out)
        print("已导出：%s" % path)
    return 0


def main():
    argv = sys.argv[1:]
    if "--cli" in argv:
        import argparse
        p = argparse.ArgumentParser(prog="新闻热点速览", description="命令行模式")
        p.add_argument("--cli", action="store_true")
        p.add_argument("--board", default=None, help="只看某个板块，如 科技 / 财经")
        p.add_argument("--top", type=int, default=20, help="打印前 N 条")
        p.add_argument("--export", default=None, help="导出格式 html/md/txt/csv/json")
        p.add_argument("--out", default=None, help="导出文件路径")
        return run_cli(p.parse_args(argv))

    from nhv4.ui.app import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
