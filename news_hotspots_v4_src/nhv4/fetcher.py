# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 并发抓取引擎

- 线程池并发，每个源独立计时
- 连续失败达阈值即熔断（冷却期内跳过，不再拖慢整体刷新）
- 结果通过线程安全队列回传，主线程用 after() 轮询取回，后台线程绝不碰 Tk
"""

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import MAX_TOTAL, log


class FetchResult:
    __slots__ = ("source", "items", "error", "ms", "skipped")

    def __init__(self, source, items=None, error=None, ms=0.0, skipped=False):
        self.source = source
        self.items = items or []
        self.error = error
        self.ms = ms
        self.skipped = skipped

    @property
    def ok(self):
        return not self.error and not self.skipped and bool(self.items)


def stamp_category(items, src):
    """按「数据源声明的板块」统一校正条目分类

    通用解析器（parse_html_items / parse_rss_items）造出的条目 category 是
    NewsItem 的默认值「新闻」，与源自身声明的板块不一致——这会让财经、视频等
    板块被统计成 0 条（板块是按条目分类过滤的）。这里统一盖章。
    """
    cat = (getattr(src, "category", "") or "新闻").strip()
    for it in items:
        it.category = cat
    return items


class FetchEngine:
    def __init__(self, max_workers=14):
        self.max_workers = max_workers
        self.q = queue.Queue()
        self._executor = None
        self._lock = threading.Lock()
        self.running = False

    # ------------------------------------------------------------ 异步刷新
    def refresh(self, sources, on_complete=None):
        """启动一次后台刷新，结果进入 self.q"""
        if self.running:
            return False
        self.running = True
        targets = [s for s in sources if s.on]
        self._pending = len(targets)
        ex = ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(targets))))
        self._executor = ex

        def _worker(src):
            t0 = time.time()
            try:
                if src.is_cooled:
                    left = int(src.cooldown_until - time.time())
                    self.q.put(FetchResult(src, skipped=True,
                                           error="熔断冷却中（%ds）" % max(left, 0)))
                    return
                src.state = "testing"
                items = src.fetcher()
                items = [i for i in (items or []) if i.title][:MAX_TOTAL]
                stamp_category(items, src)
                ms = (time.time() - t0) * 1000
                src.record_ok(ms, len(items))
                self.q.put(FetchResult(src, items=items, ms=ms))
            except Exception as e:                          # noqa: BLE001
                ms = (time.time() - t0) * 1000
                src.record_fail(ms, e)
                log("源 %s 失败: %s" % (src.name, e))
                self.q.put(FetchResult(src, error=str(e)[:200], ms=ms))
            finally:
                self._pending -= 1
                if self._pending <= 0:
                    self.running = False
                    if on_complete:
                        try:
                            on_complete()
                        except Exception:                  # noqa: BLE001
                            pass

        for s in targets:
            ex.submit(_worker, s)
        if not targets:
            self.running = False
            if on_complete:
                on_complete()
        return True

    def drain(self):
        """取走当前队列里的全部结果"""
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out

    def shutdown(self, wait=False):
        if self._executor:
            try:
                self._executor.shutdown(wait=wait)
            except Exception:                               # noqa: BLE001
                pass
            self._executor = None
        self.running = False


def fetch_blocking(sources, max_workers=14):
    """同步抓取全部源，返回 (items, results) —— 供 CLI / 测试使用"""

    def _one(src):
        t0 = time.time()
        try:
            items = [i for i in (src.fetcher() or []) if i.title]
            stamp_category(items, src)
            ms = (time.time() - t0) * 1000
            src.record_ok(ms, len(items))
            return FetchResult(src, items=items, ms=ms)
        except Exception as e:                              # noqa: BLE001
            ms = (time.time() - t0) * 1000
            src.record_fail(ms, e)
            return FetchResult(src, error=str(e)[:200], ms=ms)

    targets = [s for s in sources if s.on]
    results = []
    if not targets:
        return [], results
    with ThreadPoolExecutor(max_workers=min(max_workers, len(targets))) as ex:
        results = list(ex.map(_one, targets))
    items = []
    for r in results:
        items.extend(r.items)
    return items, results
