# -*- coding: utf-8 -*-
"""
数据源体检脚本：并发测试所有内置源，输出可用条数、耗时与样例标题。
用法：
    python tools/probe_sources.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nhv4.fetcher import fetch_blocking          # noqa: E402
from nhv4.sources import build_builtin_sources   # noqa: E402


def main():
    srcs = build_builtin_sources()
    t0 = time.time()
    items, results = fetch_blocking(srcs)
    total_ms = (time.time() - t0) * 1000

    print("=" * 92)
    print("%-14s %-10s %8s %8s  %s" % ("源ID", "分类", "条数", "耗时ms", "状态/样例"))
    print("=" * 92)
    ok = bad = 0
    for r in sorted(results, key=lambda x: x.source.id):
        src = r.source
        if r.error:
            bad += 1
            print("%-14s %-10s %8s %8.0f  FAIL %s" %
                  (src.id, src.category, "-", r.ms, r.error[:46]))
        else:
            ok += 1
            sample = (r.items[0].title[:24] if r.items else "(空)")
            print("%-14s %-10s %8d %8.0f  OK   %s" %
                  (src.id, src.category, len(r.items), r.ms, sample))
    print("=" * 92)
    print("可用源 %d / 失败 %d    总条目 %d    总耗时 %.0f ms" % (ok, bad, len(items), total_ms))

    # 聚合效果预览
    try:
        from nhv4.cluster import clusterize
        cl = clusterize(items)
        multi = [c for c in cl if c.source_count > 1]
        print("聚合后事件簇 %d 个（原始 %d 条），其中多源簇 %d 个"
              % (len(cl), len(items), len(multi)))
        for c in sorted(multi, key=lambda x: -x.source_count)[:5]:
            print("   [%d源] %s" % (c.source_count, c.title[:40]))
    except Exception as e:                                  # noqa: BLE001
        print("聚合预览失败:", e)


if __name__ == "__main__":
    main()
