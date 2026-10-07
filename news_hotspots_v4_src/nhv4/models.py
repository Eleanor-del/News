# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 数据模型
"""

import hashlib
import re
import time
from datetime import datetime

_PUNCT = re.compile(r"[\s,，。.!！?？:：;；'\"“”‘’、·\-—_/\\|#\[\]【】()（）<>《》]+")


def norm_title(t):
    """标题归一化：去标点与空白，用于去重与相似度比较"""
    return _PUNCT.sub("", (t or "")).lower()


def _fmt_heat(n):
    if n >= 100000000:
        return "%.1f亿" % (n / 100000000)
    if n >= 10000:
        return "%.1f万" % (n / 10000)
    return "%.0f" % n


class NewsItem:
    """单条新闻"""

    __slots__ = ("title", "url", "source", "category", "heat", "heat_raw",
                 "summary", "published", "fetched_at", "_uid", "_key")

    def __init__(self, title, url="", source="", category="新闻", heat="",
                 summary="", published=""):
        self.title = (title or "").strip()
        self.url = (url or "").strip()
        self.source = (source or "").strip()
        self.category = (category or "新闻").strip()
        self.heat = self._to_float(heat)
        self.heat_raw = str(heat or "").strip()
        self.summary = (summary or "").strip()
        self.published = (published or "").strip()
        self.fetched_at = time.time()
        self._uid = None
        self._key = None

    @staticmethod
    def _to_float(v):
        if v is None or v == "":
            return 0.0
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace(",", "")
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if not m:
            return 0.0
        try:
            return float(m.group(0))
        except ValueError:
            return 0.0

    # ------------------------------------------------------------ 标识
    @property
    def key(self):
        """归一化标题（跨源去重主键）"""
        if self._key is None:
            self._key = norm_title(self.title)
        return self._key

    @property
    def uid(self):
        """全局唯一 id = 源 + 归一化标题"""
        if self._uid is None:
            raw = "%s|%s" % (self.source, self.key)
            self._uid = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
        return self._uid

    # ------------------------------------------------------------ 展示
    @property
    def heat_display(self):
        if self.heat <= 0:
            return ""
        return _fmt_heat(self.heat)

    @property
    def time_display(self):
        return datetime.fromtimestamp(self.fetched_at).strftime("%H:%M")

    @property
    def host(self):
        m = re.match(r"https?://([^/]+)", self.url)
        return m.group(1) if m else ""

    def to_dict(self):
        return dict(title=self.title, url=self.url, source=self.source,
                    category=self.category, heat=self.heat, heat_raw=self.heat_raw,
                    summary=self.summary, published=self.published,
                    fetched_at=self.fetched_at, uid=self.uid)

    def __repr__(self):
        return "<NewsItem %s|%s>" % (self.source, self.title[:20])


# ---------------------------------------------------------------------------
# 趋势
# ---------------------------------------------------------------------------

TREND_STYLES = {
    "new":   ("新",   "new"),
    "surge": ("飙升", "surge"),
    "up":    ("升",   "up"),
    "down":  ("降温", "down"),
    "drop":  ("降",   "drop"),
    "flat":  ("",     "flat"),
}


class Trend:
    """热度/名次变化趋势"""

    __slots__ = ("kind", "rank_delta", "heat_ratio", "prev_rank")

    def __init__(self, kind="flat", rank_delta=0, heat_ratio=1.0, prev_rank=None):
        self.kind = kind
        self.rank_delta = rank_delta
        self.heat_ratio = heat_ratio
        self.prev_rank = prev_rank

    @property
    def label(self):
        base = TREND_STYLES.get(self.kind, ("", "flat"))[0]
        if self.kind in ("surge", "up") and self.rank_delta > 0:
            return "%s▲%d" % (base, self.rank_delta)
        if self.kind in ("drop", "down") and self.rank_delta < 0:
            return "%s▼%d" % (base, -self.rank_delta)
        return base

    @property
    def style(self):
        return TREND_STYLES.get(self.kind, ("", "flat"))[1]

    @property
    def arrow(self):
        return {"new": "●", "surge": "▲", "up": "▲", "down": "▼",
                "drop": "▼", "flat": "—"}.get(self.kind, "—")
