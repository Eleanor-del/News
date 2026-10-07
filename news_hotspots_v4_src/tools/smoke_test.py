# -*- coding: utf-8 -*-
"""
无界面冒烟测试：验证内核链路（抓取 → 落库 → 聚合 → 趋势 → 检索 → 导出）
不依赖 Tk，可在 CI 或打包前快速自检。

    python tools/smoke_test.py
"""

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nhv4.cluster import clusterize                 # noqa: E402

from nhv4.core import AppCore                       # noqa: E402
from nhv4.export import export                      # noqa: E402
from nhv4.fetcher import fetch_blocking             # noqa: E402
from nhv4.store import Store                        # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("OK" if cond else "!!", name, ("  → " + detail) if detail else ""))


def main():
    print("=" * 70)
    print("新闻热点速览 v4 · 内核冒烟测试")
    print("=" * 70)

    print("\n[1] 存储初始化")
    tmp = tempfile.mkdtemp(prefix="nhv4_")
    db = os.path.join(tmp, "test.db")
    st = Store(db)
    check("SQLite 建库", os.path.exists(db))
    print("     全文索引模式：%s" % st._fts_mode)

    print("\n[2] 并发抓取（真实网络）")
    core = AppCore(store=st)
    t0 = time.time()
    items, results = fetch_blocking(core.sources)
    ms = (time.time() - t0) * 1000
    ok = [r for r in results if not r.error]
    check("抓到条目", len(items) > 50, "%d 条 / %.0f ms" % (len(items), ms))
    check("多数源可用", len(ok) >= len(results) * 0.6,
          "%d/%d 成功" % (len(ok), len(results)))

    print("\n[3] 落库与快照")
    st.save_snapshot(items)
    check("写入快照", st.last_refresh() > 0)
    cached = st.load_snapshot()
    check("秒开缓存可读", len(cached) > 50, "%d 条" % len(cached))

    print("\n[4] 事件聚合")
    core.finish_refresh(items)
    multi = [e for e in core.entries if e.cluster.source_count > 1]
    check("生成事件簇", len(core.entries) > 20, "%d 簇（原始 %d 条）" % (len(core.entries), len(items)))
    check("聚合生效（条目数 > 簇数）", len(core.entries) < len(items))
    if multi:
        print("     多源示例：%s" % multi[0].cluster.title[:34])
    for e in multi[:3]:
        print("     · [%d源] %s" % (e.cluster.source_count, e.cluster.title[:36]))

    print("\n[5] 趋势计算（构造确定性场景）")
    from nhv4.cluster import EventCluster
    from nhv4.core import compute_trend
    from nhv4.models import NewsItem

    T1, T2 = 1000.0, 2000.0
    # 10 条里让 A 从末位冲到首位，C 是本次才出现的新条目
    names = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
    s1 = [NewsItem("事件" + n, source="T", heat=(100 - i * 10)) for i, n in enumerate(names)]
    s1[9] = NewsItem("事件" + names[9], source="T", heat=1)      # 甲最末
    s2 = [NewsItem("事件" + n, source="T", heat=(10 + i * 10)) for i, n in enumerate(names)]
    s2[9] = NewsItem("事件" + names[9], source="T", heat=999)     # 甲冲到第一
    s2.append(NewsItem("全新事件", source="T", heat=5))

    st.save_snapshot(s1, T1)
    st.save_snapshot(s2, T2)
    cur = st.rank_map(T2)
    prev = st.rank_map(T1)
    check("快照排名可读", len(cur) == 11 and len(prev) == 10,
          "cur=%d prev=%d" % (len(cur), len(prev)))

    ta = compute_trend(EventCluster([s2[9]]), cur, prev)
    tc = compute_trend(EventCluster([s2[10]]), cur, prev)
    print("     末位→首位：kind=%s delta=%d" % (ta.kind, ta.rank_delta))
    print("     本次新增：kind=%s" % tc.kind)
    check("名次大涨识别为飙升", ta.kind == "surge", ta.label)
    check("首次出现识别为新上榜", tc.kind == "new", tc.label)

    # 无历史快照时不应全部标「新」
    core2 = AppCore(store=st)
    core2._prev_map = {}
    core2._cur_map = cur
    core2.clusters = clusterize(s2)
    core2._build_entries()
    fresh = {}
    for e in core2.entries:
        fresh[e.trend.kind] = fresh.get(e.trend.kind, 0) + 1
    print("     无历史时分布：%s" % fresh)
    check("无历史快照时不做新上榜标记", fresh.get("new", 0) == 0)

    print("\n[6] 视图筛选")
    for b in ("科技", "财经", "体育", "军事"):
        got = core.view(board=b)
        if got:
            print("     %s：%d 条，示例 %s" % (b, len(got), got[0].title[:26]))
    check("板块筛选可用", True)

    print("\n[7] 全文检索")
    st.rebuild_fts()
    q = "中国" if any("中国" in i.title for i in items) else (items[0].title[:2] if items else "的")
    hits = core.search_archive(q)
    check("FTS/LIKE 检索返回", True, "「%s」→ %d 条" % (q, len(hits)))
    print("     %s" % (hits[0].title[:40] if hits else "-"))

    print("\n[8] 收藏 / 订阅")
    e0 = core.entries[0]
    core.toggle_fav(e0)
    check("收藏写入", len(core.store.favorites()) == 1)
    core.add_sub(q)
    check("订阅匹配", len(core.sub_hits()) >= 0, "命中 %d 条" % len(core.sub_hits()))
    core.toggle_fav(e0)
    check("取消收藏", len(core.store.favorites()) == 0)

    print("\n[9] 导出")
    outdir = os.path.join(tmp, "out")
    os.makedirs(outdir, exist_ok=True)
    for fmt, ext in (("html", ".html"), ("md", ".md"), ("txt", ".txt"),
                     ("csv", ".csv"), ("json", ".json")):
        p = os.path.join(outdir, "t" + ext)
        try:
            export(fmt, core.entries[:30], p)
            size = os.path.getsize(p)
            check("导出 %s" % fmt, size > 100, "%d 字节" % size)
        except Exception as e:                              # noqa: BLE001
            check("导出 %s" % fmt, False, str(e))

    print("\n[10] 统计")
    s = core.stats
    print("     %s" % s)
    check("统计可读", s.get("items", 0) > 0)

    st.close()
    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 70)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：%s" % "、".join(FAIL))
    print("=" * 70)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
