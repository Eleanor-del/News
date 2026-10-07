# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 业务核心

把「存储 / 抓取 / 聚合 / 趋势 / 订阅」串成一条完整链路，UI 只消费结果：

    启动  ──► store.load_snapshot()      秒开：直接渲染上次结果，无需等待网络
            ──► engine.refresh()         后台并发刷新
    刷新完成 ─► store.save_snapshot()    落库 + 记录名次/热度历史
            ──► clusterize()             跨源事件聚合
            ──► compute_trends()         与上一次快照比对得出趋势
"""

import time

from .cluster import EventCluster, clusterize
from .config import (HEAT_SURGE_RATIO, RANK_DROP, RANK_SURGE, log,
                     load_settings, save_settings)
from .fetcher import FetchEngine
from .models import Trend
from .sources import build_builtin_sources, clean_items, make_custom_source
from .store import Store


class Entry:
    """一个待渲染条目 = 事件簇 + 趋势 + 各种标记"""

    __slots__ = ("cluster", "trend", "rank", "subscribed", "read", "fav", "score")

    def __init__(self, cluster, trend=None, rank=0):
        self.cluster = cluster
        self.trend = trend or Trend()
        self.rank = rank
        self.subscribed = False
        self.read = False
        self.fav = False
        self.score = 0.0

    # 便捷代理
    @property
    def title(self):
        return self.cluster.title

    @property
    def uid(self):
        return self.cluster.uid

    @property
    def url(self):
        return self.cluster.url

    @property
    def sources(self):
        return self.cluster.sources

    @property
    def time_display(self):
        return self.cluster.time_display

    @property
    def heat_display(self):
        return self.cluster.heat_display

    def __repr__(self):
        return "<Entry #%d %s>" % (self.rank, self.title[:18])


def compute_trend(cluster, cur_map, prev_map):
    """比较本次与上次快照，得出该事件簇的趋势"""
    prev_ranks = []
    best = None
    for uid in cluster.uids:
        cur = cur_map.get(uid)
        if cur is None:
            continue
        prev = prev_map.get(uid)
        if prev is None:
            continue
        prev_ranks.append(prev[0])
        delta = prev[0] - cur[0]
        ratio = (cur[1] / prev[1]) if prev[1] > 0 and cur[1] > 0 else 1.0
        if best is None or delta > best[0]:
            best = (delta, ratio, prev[0])
    if not prev_ranks or best is None:
        return Trend("new")
    delta, ratio, prev_rank = best
    if delta >= RANK_SURGE or ratio >= HEAT_SURGE_RATIO:
        return Trend("surge", delta, ratio, prev_rank)
    if delta >= 1:
        return Trend("up", delta, ratio, prev_rank)
    if delta <= -RANK_DROP:
        return Trend("down", delta, ratio, prev_rank)
    if delta <= -1:
        return Trend("drop", delta, ratio, prev_rank)
    return Trend("flat", delta, ratio, prev_rank)


class AppCore:
    def __init__(self, store=None):
        self.settings = load_settings()
        self.store = store or Store()
        self.engine = FetchEngine()

        self.items = []            # 当前原始条目
        self.clusters = []         # 当前事件簇
        self.entries = []          # 当前渲染条目

        self._cur_map = {}
        self._prev_map = {}
        self._read = set()
        self._favs = set()
        self._subs = []

        self.last_refresh = 0.0
        self.refreshing = False
        self.last_error = ""

        self.sources = []
        self.rebuild_sources()
        self._load_marks()

    # ------------------------------------------------------------ 数据源
    def rebuild_sources(self):
        removed = set(self.settings.get("removed") or [])
        disabled = set(self.settings.get("disabled") or [])
        builtin = [s for s in build_builtin_sources() if s.id not in removed]
        custom = [make_custom_source(d) for d in (self.settings.get("custom") or [])]
        for s in builtin + custom:
            if s.id in disabled:
                s.on = False
        self.sources = builtin + custom

    def find_source(self, sid):
        return next((s for s in self.sources if s.id == sid), None)

    def enabled_sources(self):
        return [s for s in self.sources if s.on]

    def set_source_on(self, sid, on):
        s = self.find_source(sid)
        if not s:
            return
        s.on = on
        if on:
            s.reset_circuit()
        dis = set(self.settings.get("disabled") or [])
        dis.discard(sid) if on else dis.add(sid)
        self.settings["disabled"] = sorted(dis)
        save_settings(self.settings)

    def remove_source(self, sid):
        s = self.find_source(sid)
        if not s:
            return
        if s.builtin:
            rm = set(self.settings.get("removed") or [])
            rm.add(sid)
            self.settings["removed"] = sorted(rm)
        else:
            self.settings["custom"] = [
                d for d in (self.settings.get("custom") or []) if d.get("id") != sid]
        save_settings(self.settings)
        self.rebuild_sources()

    def restore_builtin(self):
        self.settings["removed"] = []
        save_settings(self.settings)
        self.rebuild_sources()

    def add_custom_source(self, defn):
        customs = list(self.settings.get("custom") or [])
        if any(d.get("url") == defn.get("url") for d in customs):
            return False
        customs.append(defn)
        self.settings["custom"] = customs
        save_settings(self.settings)
        self.rebuild_sources()
        return True

    # ------------------------------------------------------------ 标记
    def _load_marks(self):
        try:
            self._read = self.store.read_set()
            self._favs = {f.uid for f in self.store.favorites()}
            self._subs = self.store.subs()
        except Exception as e:                              # noqa: BLE001
            log("读取标记失败: %s" % e)

    # ------------------------------------------------------------ 秒开
    def load_cached(self):
        """从数据库恢复上次结果，立即渲染"""
        try:
            items = self.store.load_snapshot()
        except Exception as e:                              # noqa: BLE001
            log("读取缓存失败: %s" % e)
            items = []
        self.last_refresh = self.store.last_refresh()
        self._adopt(items, persist=False)
        return self.entries

    # ------------------------------------------------------------ 刷新
    def start_refresh(self):
        if self.refreshing:
            return False
        self.refreshing = True
        self.engine.refresh(self.sources)
        return True

    def poll(self):
        """主线程调用：取回已完成的抓取结果"""
        results = self.engine.drain()
        return results

    def finish_refresh(self, new_items):
        """合并结果、落库、重算聚合与趋势"""
        ts = time.time()
        if new_items:
            try:
                self.store.save_snapshot(new_items, ts)
            except Exception as e:                          # noqa: BLE001
                log("写入快照失败: %s" % e)
        self.last_refresh = ts
        self.refreshing = False
        self._adopt(new_items or self.items, persist=False)
        return self.entries

    # ------------------------------------------------------------ 核心装配
    def _adopt(self, items, persist=False):
        # clean_items 会剔除榜单说明之类的非新闻噪声（如「每10分钟更新一次」）
        self.items = clean_items([i for i in (items or []) if i and i.title])
        self.clusters = clusterize(items)
        self._cur_map = self.store.rank_map()
        prev_ts = self.store.previous_snapshot_ts()
        self._prev_map = self.store.rank_map(prev_ts) if prev_ts else {}
        self._build_entries()
        return self.entries

    def _build_entries(self):
        sub_pats = [s for s in self._subs if s]
        # 首次运行没有任何历史快照，此时给所有条目打「新」没有意义，一律留空
        has_history = bool(self._prev_map)
        entries = []
        for c in self.clusters:
            e = Entry(c, compute_trend(c, self._cur_map, self._prev_map)
                      if has_history else Trend())
            blob = " ".join(it.title for it in c.items).lower()
            e.subscribed = any(s.lower() in blob for s in sub_pats) if sub_pats else False
            e.read = any(u in self._read for u in c.uids)
            e.fav = any(u in self._favs for u in c.uids)
            entries.append(e)
        self._sort(entries, self.settings.get("sort", "rank"))
        for i, e in enumerate(entries):
            e.rank = i + 1
        self.entries = entries

    # ------------------------------------------------------------ 排序 / 筛选
    def _sort(self, entries, mode):
        if mode == "heat":
            entries.sort(key=lambda e: -e.cluster.heat)
        elif mode == "time":
            entries.sort(key=lambda e: -e.cluster.time)
        elif mode == "sources":
            entries.sort(key=lambda e: (-e.cluster.source_count, -e.cluster.heat))
        else:  # rank —— 综合分：热度 + 多源加成
            def sc(e):
                c = e.cluster
                bonus = 1.0 + 0.18 * (c.source_count - 1)
                return -(c.heat * bonus + 60.0 * c.source_count)
            entries.sort(key=sc)

    def view(self, board="全部", query="", sort=None, favorites=False):
        """按板块 / 关键词过滤"""
        if sort and sort != self.settings.get("sort"):
            self.settings["sort"] = sort
            save_settings(self.settings)
            self._sort(self.entries, sort)
            for i, e in enumerate(self.entries):
                e.rank = i + 1

        if favorites:
            src = [Entry(EventCluster([f]), Trend()) for f in self.store.favorites()]
            for i, e in enumerate(src):
                e.rank = i + 1
                e.fav = True
            out = src
        else:
            out = list(self.entries)

        if board and board not in ("全部", "订阅"):
            out = [e for e in out if board in e.cluster.categories]

        if board == "订阅":
            out = [e for e in out if e.subscribed]

        q = (query or "").strip()
        if q:
            ql = q.lower()
            out = [e for e in out
                   if ql in e.title.lower()
                   or any(ql in it.title.lower() for it in e.cluster.items)
                   or any(ql in s.lower() for s in e.cluster.sources)]

        # 订阅命中置顶
        if self.settings.get("pin_subscription", True):
            out.sort(key=lambda e: 0 if e.subscribed else 1)
        return out

    def search_archive(self, query, limit=300):
        """全文检索历史归档"""
        items = self.store.search(query, limit)
        out = []
        for it in items:
            c = EventCluster([it])
            e = Entry(c, Trend("flat"))
            e.read = it.uid in self._read
            e.fav = it.uid in self._favs
            out.append(e)
        for i, e in enumerate(out):
            e.rank = i + 1
        return out

    def recent_archive(self, days=7, limit=300):
        items = self.store.recent(days, limit)
        groups = {}
        for it in items:
            groups.setdefault(it.source, []).append(it)
        out = []
        for src, lst in groups.items():
            for it in lst:
                e = Entry(EventCluster([it]), Trend("flat"))
                e.read = it.uid in self._read
                out.append(e)
        out.sort(key=lambda e: -e.cluster.time)
        for i, e in enumerate(out):
            e.rank = i + 1
        return out

    # ------------------------------------------------------------ 交互
    def toggle_fav(self, entry):
        item = entry.cluster.head
        on = self.store.fav_toggle(item)
        if on:
            self._favs.add(item.uid)
        else:
            self._favs.discard(item.uid)
        entry.fav = on
        return on

    def mark_read(self, entry):
        for u in entry.cluster.uids:
            self.store.mark_read(u)
            self._read.add(u)
        entry.read = True

    # ------------------------------------------------------------ 订阅
    @property
    def subs(self):
        return list(self._subs)

    def add_sub(self, kw):
        kw = (kw or "").strip()
        if not kw or kw in self._subs:
            return False
        self.store.sub_add(kw)
        self._subs.append(kw)
        self._build_entries()
        return True

    def remove_sub(self, kw):
        self.store.sub_remove(kw)
        self._subs = [s for s in self._subs if s != kw]
        self._build_entries()

    def sub_hits(self):
        return [e for e in self.entries if e.subscribed]

    # ------------------------------------------------------------ 设置
    def save(self):
        save_settings(self.settings)

    def set(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)

    @property
    def stats(self):
        st = self.store.stats()
        st.update(clusters=len(self.clusters), items=len(self.items),
                  sources=len(self.enabled_sources()))
        return st

    def prune_if_needed(self):
        """每天最多清理一次历史"""
        key = "_last_prune"
        last = self.settings.get(key, 0)
        if time.time() - float(last or 0) < 86400:
            return
        try:
            self.store.prune()
        except Exception as e:                              # noqa: BLE001
            log("清理历史失败: %s" % e)
        self.settings[key] = time.time()
        save_settings(self.settings)


# ---------------------------------------------------------------------------
# 板块定义
# ---------------------------------------------------------------------------

BASE_BOARDS = ["全部", "新闻", "财经", "科技", "体育", "军事", "视频", "游戏"]
EXTRA_BOARDS = ["订阅", "收藏", "归档"]


def available_boards(core):
    cats = set()
    for s in core.enabled_sources():
        cats.add(s.category)
    boards = ["全部"] + [b for b in BASE_BOARDS[1:] if b in cats]
    boards += [c for c in sorted(cats) if c not in boards]
    return boards + EXTRA_BOARDS
