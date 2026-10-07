# -*- coding: utf-8 -*-
"""
v4.0.1 问题体检

1) 阅读器：对每个源的真实 URL 跑 extract_article，统计成功率与失败原因
2) 板块：统计每个板块实际能拿到的事件数，找出空板块

    python tools/probe_v401.py
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import concurrent.futures as cf                            # noqa: E402

from nhv4.core import AppCore, available_boards            # noqa: E402
from nhv4.fetcher import fetch_blocking                    # noqa: E402
from nhv4.net import extract_article                       # noqa: E402


def main():
    core = AppCore()
    print("== 数据源 %d 个 ==" % len(core.enabled_sources()))
    items, results = fetch_blocking(core.sources)
    core.finish_refresh(items)

    print("\n=== [2] 板块统计 ===")
    boards = available_boards(core)
    print("板块列表: %s" % boards)
    for b in boards:
        if b in ("订阅", "收藏", "归档"):
            continue
        n = len(core.view(board=b))
        print("  %-4s 事件数=%-4d" % (b, n), ("  ← 空！" if n == 0 else ""))
    cats = defaultdict(int)
    for s in core.enabled_sources():
        cats[s.category] += 1
    print("  每个分类的源数量: %s" % dict(cats))

    print("\n=== [1] 阅读器正文提取实测 ===")
    # 每个源挑 3 条真实 URL
    by_src = defaultdict(list)
    for it in items:
        if len(by_src[it.source]) < 3 and it.url:
            by_src[it.source].append((it.title, it.url))

    jobs = []
    for src, lst in by_src.items():
        for title, url in lst:
            jobs.append((src, title, url))

    def run(job):
        src, title, url = job
        try:
            paras, imgs, vids, err, note = extract_article(url)
            info = (note or "") if paras else (err or "无段落")
            return src, title, url, (len(paras) if paras else 0), info
        except Exception as e:                             # noqa: BLE001
            return src, title, url, -1, "异常 %s: %s" % (type(e).__name__, e)

    stat = defaultdict(lambda: [0, 0])
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for src, title, url, n, err in ex.map(run, jobs):
            s = stat[src]
            if err or n <= 0:
                s[1] += 1
                print("  [失败] %-8s %-30s %s" % (src, title[:28], err or "无段落"))
                print("          %s" % url[:110])
            else:
                s[0] += 1

    print("\n  各源成功率：")
    for src in sorted(stat):
        ok, bad = stat[src]
        print("    %-10s 成功 %d / 失败 %d" % (src, ok, bad))
    tot_ok = sum(v[0] for v in stat.values())
    tot_bad = sum(v[1] for v in stat.values())
    print("  合计：成功 %d，失败 %d" % (tot_ok, tot_bad))


if __name__ == "__main__":
    main()
