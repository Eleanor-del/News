# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · SQLite 归档存储

承担四件事：
1) 秒开缓存 —— 上次刷新的完整快照落库，启动时直接读库渲染，不再空白等待
2) 历史归档 —— 所有见过的条目按 uid 留存，可回溯任意一天
3) 全文检索 —— FTS5（trigram 分词，适配中文子串查询），不可用时退化为 LIKE
4) 热度/名次历史 —— 每次刷新记录 (uid, ts, heat, rank)，用于计算趋势
"""

import os
import sqlite3
import threading
import time

from .config import HISTORY_DAYS, db_path, log

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    uid        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    url        TEXT,
    source     TEXT,
    category   TEXT,
    heat       REAL DEFAULT 0,
    first_seen REAL,
    last_seen  REAL,
    seen_count INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_items_last  ON items(last_seen);
CREATE INDEX IF NOT EXISTS idx_items_title ON items(title);

CREATE TABLE IF NOT EXISTS heat_log (
    uid  TEXT NOT NULL,
    ts   REAL NOT NULL,
    heat REAL DEFAULT 0,
    rank INTEGER DEFAULT 0,
    PRIMARY KEY (uid, ts)
);
CREATE INDEX IF NOT EXISTS idx_heat_ts ON heat_log(ts);

CREATE TABLE IF NOT EXISTS favorites (
    uid     TEXT PRIMARY KEY,
    title   TEXT,
    url     TEXT,
    source  TEXT,
    added   REAL
);

CREATE TABLE IF NOT EXISTS read_state (
    uid TEXT PRIMARY KEY,
    at  REAL
);

CREATE TABLE IF NOT EXISTS subs (
    kw    TEXT PRIMARY KEY,
    added REAL
);

CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""


class Store:
    def __init__(self, path=None):
        self.path = path or db_path()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=15)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        except Exception:                                   # noqa: BLE001
            pass
        self._fts_ok = False
        self._fts_mode = "none"
        self._init_schema()
        self._init_fts()

    # ------------------------------------------------------------ 初始化
    def _init_schema(self):
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def _init_fts(self):
        """优先 trigram（中文友好），退化 unicode61，再退化 LIKE"""
        for tok in ("trigram", "unicode61"):
            try:
                self._conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5("
                    "title, source, tokenize='%s')" % tok)
                self._conn.commit()
                self._fts_ok = True
                self._fts_mode = tok
                return
            except Exception:                               # noqa: BLE001
                try:
                    self._conn.execute("DROP TABLE IF EXISTS fts")
                except Exception:                           # noqa: BLE001
                    pass
        self._fts_ok = False
        self._fts_mode = "none"
        log("FTS5 不可用，全文检索退化为 LIKE 扫描")

    def rebuild_fts(self, days=30):
        """
        重建全文索引。FTS5 对带条件的 DELETE 支持很差，
        因此不做增量维护，而是整表重建（数千行耗时不到 1 秒，后台执行即可）。
        """
        if not self._fts_ok:
            return False
        cutoff = time.time() - days * 86400
        with self._lock:
            try:
                c = self._conn
                c.execute("DELETE FROM fts")        # 普通表语义，清空内容
                c.execute(
                    "INSERT INTO fts (title, source) "
                    "SELECT title, source FROM items WHERE last_seen>=?", (cutoff,))
                c.commit()
                self._fts_dirty = False
                return True
            except Exception as e:                          # noqa: BLE001
                log("重建全文索引失败: %s" % e)
                self._fts_ok = False
                return False

    @property
    def fts_ready(self):
        return self._fts_ok and not self._fts_dirty

    # ------------------------------------------------------------ 写入
    def save_snapshot(self, items, ts=None):
        """
        保存一次刷新结果：
        - upsert items
        - 记录 heat_log(uid, ts, heat, rank)，rank 为本次全局热度排名
        """
        ts = ts or time.time()
        ordered = sorted(items, key=lambda x: -x.heat)
        rank_of = {}
        for i, it in enumerate(ordered):
            rank_of[it.uid] = i + 1

        item_rows = []
        heat_rows = []
        for it in items:
            r = rank_of.get(it.uid, 0)
            item_rows.append((it.uid, it.title, it.url, it.source, it.category,
                              it.heat, it.fetched_at, it.fetched_at))
            heat_rows.append((it.uid, ts, it.heat, r))

        with self._lock:
            c = self._conn
            c.executemany(
                "INSERT INTO items (uid,title,url,source,category,heat,first_seen,last_seen,seen_count)"
                " VALUES (?,?,?,?,?,?,?,?,1)"
                " ON CONFLICT(uid) DO UPDATE SET"
                " title=excluded.title, url=excluded.url, heat=excluded.heat,"
                " last_seen=excluded.last_seen, category=excluded.category,"
                " seen_count=items.seen_count+1",
                item_rows)
            c.executemany(
                "INSERT OR REPLACE INTO heat_log (uid,ts,heat,rank) VALUES (?,?,?,?)",
                heat_rows)
            c.execute("INSERT OR REPLACE INTO meta (k,v) VALUES ('last_refresh',?)", (str(ts),))
            c.commit()
        self._fts_dirty = True
        return ts

    # ------------------------------------------------------------ 读取
    def last_refresh(self):
        with self._lock:
            r = self._conn.execute("SELECT v FROM meta WHERE k='last_refresh'").fetchone()
        try:
            return float(r["v"]) if r else 0.0
        except (TypeError, ValueError):
            return 0.0

    def load_snapshot(self, limit=900):
        """取出最近一次刷新的条目（秒开用）"""
        ts = self.last_refresh()
        if not ts:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT i.*, h.rank FROM items i JOIN heat_log h ON h.uid=i.uid"
                " WHERE h.ts=? ORDER BY h.rank LIMIT ?", (ts, limit)).fetchall()
        return [self._row_to_item(r) for r in rows]

    def rank_map(self, ts=None):
        """某次快照的 uid -> rank"""
        ts = ts or self.last_refresh()
        if not ts:
            return {}
        with self._lock:
            rows = self._conn.execute(
                "SELECT uid, rank, heat FROM heat_log WHERE ts=?", (ts,)).fetchall()
        return {r["uid"]: (r["rank"], r["heat"] or 0.0) for r in rows}

    def previous_snapshot_ts(self, before=None):
        """早于 before 的最近一次快照时间"""
        before = before or self.last_refresh()
        with self._lock:
            r = self._conn.execute(
                "SELECT MAX(ts) AS ts FROM heat_log WHERE ts < ?", (before,)).fetchone()
        return r["ts"] if r and r["ts"] else None

    def history_of(self, uid, limit=40):
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, heat, rank FROM heat_log WHERE uid=? ORDER BY ts DESC LIMIT ?",
                (uid, limit)).fetchall()
        return [(r["ts"], r["heat"] or 0.0, r["rank"] or 0) for r in rows]

    # ------------------------------------------------------------ 检索
    def search(self, query, limit=300):
        q = (query or "").strip()
        if not q:
            return []
        # 1) FTS
        if self.fts_ready and len(q) >= 2:
            try:
                mq = '"%s"' % q.replace('"', '""')
                with self._lock:
                    rows = self._conn.execute(
                        "SELECT i.uid, i.title, i.url, i.source, i.category, i.heat, i.last_seen "
                        "FROM fts f JOIN items i ON i.title=f.title AND i.source=f.source "
                        "WHERE f MATCH ? ORDER BY bm25(f) LIMIT ?", (mq, limit)).fetchall()
                if rows:
                    return [self._row_to_item(dict(r)) for r in rows]
            except Exception:                               # noqa: BLE001
                pass
        # 2) LIKE 兜底
        like = "%" + q.replace("%", "") + "%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM items WHERE title LIKE ? OR source LIKE ?"
                " ORDER BY last_seen DESC LIMIT ?", (like, like, limit)).fetchall()
        return [self._row_to_item(r) for r in rows]

    def recent(self, days=7, limit=500):
        since = time.time() - days * 86400
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM items WHERE last_seen>=? ORDER BY last_seen DESC LIMIT ?",
                (since, limit)).fetchall()
        return [self._row_to_item(r) for r in rows]

    # ------------------------------------------------------------ 收藏 / 已读
    def favorites(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM favorites ORDER BY added DESC").fetchall()
        from .models import NewsItem
        out = []
        for r in rows:
            it = NewsItem(title=r["title"] or "", url=r["url"] or "",
                          source=r["source"] or "", category="收藏")
            it.fetched_at = r["added"] or time.time()
            out.append(it)
        return out

    def is_fav(self, uid):
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM favorites WHERE uid=?", (uid,)).fetchone() is not None

    def fav_add(self, item):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO favorites (uid,title,url,source,added) VALUES (?,?,?,?,?)",
                (item.uid, item.title, item.url, item.source, time.time()))
            self._conn.commit()

    def fav_remove(self, uid):
        with self._lock:
            self._conn.execute("DELETE FROM favorites WHERE uid=?", (uid,))
            self._conn.commit()

    def fav_toggle(self, item):
        if self.is_fav(item.uid):
            self.fav_remove(item.uid)
            return False
        self.fav_add(item)
        return True

    def mark_read(self, uid):
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO read_state (uid,at) VALUES (?,?)",
                               (uid, time.time()))
            self._conn.commit()

    def read_set(self):
        with self._lock:
            rows = self._conn.execute("SELECT uid FROM read_state").fetchall()
        return {r["uid"] for r in rows}

    # ------------------------------------------------------------ 订阅
    def subs(self):
        with self._lock:
            rows = self._conn.execute("SELECT kw FROM subs ORDER BY added").fetchall()
        return [r["kw"] for r in rows]

    def sub_add(self, kw):
        kw = (kw or "").strip()
        if not kw:
            return
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO subs (kw,added) VALUES (?,?)",
                               (kw, time.time()))
            self._conn.commit()

    def sub_remove(self, kw):
        with self._lock:
            self._conn.execute("DELETE FROM subs WHERE kw=?", (kw,))
            self._conn.commit()

    # ------------------------------------------------------------ 统计 / 维护
    def stats(self):
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) c FROM items").fetchone()["c"]
            fav = self._conn.execute("SELECT COUNT(*) c FROM favorites").fetchone()["c"]
            snaps = self._conn.execute("SELECT COUNT(DISTINCT ts) c FROM heat_log").fetchone()["c"]
        try:
            size = os.path.getsize(self.path) / 1048576.0
        except OSError:
            size = 0.0
        return dict(items=total, favorites=fav, snapshots=snaps, size_mb=size)

    def prune(self, days=HISTORY_DAYS):
        cutoff = time.time() - days * 86400
        with self._lock:
            self._conn.execute("DELETE FROM heat_log WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM items WHERE last_seen < ?", (cutoff,))
            self._conn.execute("DELETE FROM read_state WHERE at < ?", (cutoff,))
            self._conn.execute("VACUUM")
            self._conn.commit()

    def clear_all(self):
        with self._lock:
            for t in ("items", "heat_log", "favorites", "read_state"):
                self._conn.execute("DELETE FROM %s" % t)
            if self._fts_ok:
                try:
                    self._conn.execute("DELETE FROM fts")
                except Exception:                           # noqa: BLE001
                    pass
            self._conn.commit()

    # ------------------------------------------------------------ 工具
    @staticmethod
    def _row_to_item(r):
        from .models import NewsItem
        it = NewsItem(title=r["title"] or "", url=r["url"] or "",
                      source=r["source"] or "",
                      category=(r["category"] if "category" in r.keys() else "新闻") or "新闻",
                      heat=r["heat"] or 0)
        it.fetched_at = r["last_seen"] or (r["added"] if "added" in r.keys() else time.time()) or time.time()
        return it

    def close(self):
        try:
            self._conn.close()
        except Exception:                                   # noqa: BLE001
            pass
