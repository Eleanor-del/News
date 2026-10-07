# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 跨源事件聚合

同一个热点事件往往被多个平台同时报道（头条/微博/百度/腾讯…），
v3 只做标题完全相同的去重，列表里仍会反复刷屏同一件事。
v4 用「中文二元切分 + Jaccard 相似度 + 子串奖励」把多源报道聚成一个
事件簇，并保留所有来源，界面上只显示一条 + 「N 源在报」。

性能：直接两两比较是 O(n²)，400 条即 8 万次相似度计算。
这里用 shingle 倒排索引做候选分块，只对至少共享一个二元组的新闻对
计算相似度，实际计算量下降一到两个数量级。
"""

from .config import CLUSTER_THRESHOLD, SHINGLE_N
from .models import norm_title


def shingles(title, n=SHINGLE_N):
    """中文二元切分集合"""
    s = norm_title(title)
    if not s:
        return set()
    if len(s) <= n:
        return {s}
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def similarity(a, b):
    """
    两条标题的相似度（0~1）

    纯 Jaccard 对中文短标题过于严苛：「秋分」与「今日秋分」只共享一个二元组，
    Jaccard 仅 0.33，会被判为两个事件。因此叠加重叠系数（inter / min），
    它对「短标题是长标题一部分」的情形更敏感，而这正是跨源改写的主要形态。
    """
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    sim = 0.0
    if union:
        sim = inter / float(union)
    if inter:
        # 重叠系数：短标题被长标题覆盖时接近 1
        sim = max(sim, 0.72 * (inter / float(min(len(sa), len(sb)))))
    # 子串奖励：一条标题完整包含在另一条里，几乎必然是同一事件
    na, nb = norm_title(a), norm_title(b)
    if na and nb:
        if na == nb:
            return 1.0
        if (na in nb or nb in na) and min(len(na), len(nb)) >= 5:
            sim = max(sim, 0.88)
    return sim


class EventCluster:
    """一个事件簇：同一事件的多源报道集合"""

    __slots__ = ("items", "uid", "_title", "_cat")

    def __init__(self, items):
        # 按热度降序、来源名升序，保证代表项稳定
        self.items = sorted(items, key=lambda x: (-x.heat, x.source))
        self.uid = self.items[0].uid
        self._title = None
        self._cat = None

    # ------------------------------------------------------------ 代表内容
    @property
    def title(self):
        """代表标题：取信息量最全的一条（最长且非纯符号）"""
        if self._title is None:
            cands = [it.title for it in self.items if len(it.title) >= 6]
            self._title = max(cands, key=len) if cands else (self.items[0].title or "")
        return self._title

    @property
    def head(self):
        """热度最高的一条，用于跳转链接"""
        return self.items[0]

    @property
    def url(self):
        for it in self.items:
            if it.url:
                return it.url
        return ""

    @property
    def sources(self):
        seen, out = set(), []
        for it in self.items:
            if it.source and it.source not in seen:
                seen.add(it.source)
                out.append(it.source)
        return out

    @property
    def source_count(self):
        return len(self.sources)

    @property
    def heat(self):
        return max((it.heat for it in self.items), default=0.0)

    @property
    def heat_display(self):
        return _fmt(self.heat) if self.heat > 0 else ""

    @property
    def category(self):
        if self._cat is None:
            tally = {}
            for it in self.items:
                tally[it.category] = tally.get(it.category, 0) + 1
            self._cat = max(tally.items(), key=lambda kv: kv[1])[0] if tally else "新闻"
        return self._cat

    @property
    def categories(self):
        seen = []
        for it in self.items:
            if it.category not in seen:
                seen.append(it.category)
        return seen

    @property
    def time(self):
        return max(it.fetched_at for it in self.items)

    @property
    def time_display(self):
        import datetime
        return datetime.datetime.fromtimestamp(self.time).strftime("%H:%M")

    @property
    def uids(self):
        return [it.uid for it in self.items]

    def summary_text(self):
        """簇内各来源标题，用于 tooltip / 导出"""
        return "\n".join("· [%s] %s" % (it.source, it.title) for it in self.items)

    def __len__(self):
        return len(self.items)

    def __repr__(self):
        return "<EventCluster %d源 %s>" % (self.source_count, self.title[:16])


def _fmt(n):
    if n >= 100000000:
        return "%.1f亿" % (n / 100000000)
    if n >= 10000:
        return "%.1f万" % (n / 10000)
    return "%.0f" % n


def _find(parent, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent, rank, a, b):
    ra, rb = _find(parent, a), _find(parent, b)
    if ra == rb:
        return
    if rank[ra] < rank[rb]:
        ra, rb = rb, ra
    parent[rb] = ra
    if rank[ra] == rank[rb]:
        rank[ra] += 1


def clusterize(items, threshold=CLUSTER_THRESHOLD):
    """把 NewsItem 列表聚合成 EventCluster 列表"""
    if not items:
        return []

    n = len(items)
    parent = list(range(n))
    rank = [0] * n

    # 1) 完全相同归一化标题的先按 uid 精确合并（最快路径）
    exact = {}
    for i, it in enumerate(items):
        k = it.key
        if k in exact:
            _union(parent, rank, exact[k], i)
        else:
            exact[k] = i

    # 2) shingle 倒排索引生成候选对
    index = {}
    for i, it in enumerate(items):
        for sh in shingles(it.title):
            index.setdefault(sh, []).append(i)

    MAX_POSTING = 80      # 超高频二元组（如"中国""一个"）不具区分度，跳过
    checked = set()
    for sh, postings in index.items():
        if len(postings) > MAX_POSTING or len(postings) < 2:
            continue
        for a in range(len(postings)):
            ia = postings[a]
            for b in range(a + 1, len(postings)):
                ib = postings[b]
                pair = (ia, ib) if ia < ib else (ib, ia)
                if pair in checked:
                    continue
                checked.add(pair)
                if similarity(items[ia].title, items[ib].title) >= threshold:
                    _union(parent, rank, ia, ib)

    # 3) 收集分组
    groups = {}
    for i in range(n):
        groups.setdefault(_find(parent, i), []).append(items[i])

    clusters = [EventCluster(g) for g in groups.values()]
    return clusters
