# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 数据源层

- Source：统一描述一个数据源，带健康度（成功率 / 平均耗时 / 连续失败 / 熔断）
- 内置源：热榜 JSON 接口优先，RSS 次之，HTML 抓取兜底
- 自定义源：模板库关键词匹配 + URL 自动探测（json / rss / html）
"""

import re
import time
import xml.etree.ElementTree as ET

from . import net
from .config import CIRCUIT_COOLDOWN, CIRCUIT_FAILS, MAX_PER_SOURCE
from .models import NewsItem, norm_title

from urllib.parse import quote


# ===========================================================================
# 通用解析器
# ===========================================================================

def dedupe(items):
    seen, out = set(), []
    for it in items:
        if not it.title:
            continue
        k = norm_title(it.title)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _walk_dicts(obj):
    """递归找出 JSON 中所有含标题字段的 dict"""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list):
                for e in v:
                    if isinstance(e, dict):
                        found.append(e)
            elif isinstance(v, (dict, list)):
                found += _walk_dicts(v)
    elif isinstance(obj, list):
        for e in obj:
            if isinstance(e, dict):
                found += _walk_dicts(e)
    return found


_TITLE_KEYS = ("title", "Title", "name", "itemTitle", "word", "query", "showName",
               "hotword", "hotWord", "content", "desc", "text")
_URL_KEYS = ("url", "Url", "link", "url_m", "itemUrl", "shareUrl", "rawUrl", "href", "surl")
_HEAT_KEYS = ("hot", "hotScore", "heat", "num", "index", "hotValue", "HotValue",
              "hotIndex", "readCount", "viewCount", "score", "popularity")


def _first(d, keys):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    return ""


def extract_json_items(data, source_name, n=MAX_PER_SOURCE):
    """从任意嵌套 JSON 中尽力抽取新闻条目"""
    items = []
    for e in _walk_dicts(data):
        title = _first(e, _TITLE_KEYS)
        if not title or len(title) < 4:
            continue
        # 标题里出现明显非新闻键值的跳过
        if title.lower() in ("null", "undefined", "none"):
            continue
        url = _first(e, _URL_KEYS)
        heat = _first(e, _HEAT_KEYS)
        items.append(NewsItem(title=title, url=url, heat=heat, source=source_name))
    return dedupe(items)[:n]


def parse_json_items(url, source_name, n=MAX_PER_SOURCE):
    return extract_json_items(net.get_json(url), source_name, n)


def parse_json_post_items(url, source_name, n=MAX_PER_SOURCE, body=None, headers=None):
    return extract_json_items(net.post_json(url, body or {}, headers=headers),
                              source_name, n)


def parse_rss_items(url, source_name, n=MAX_PER_SOURCE):
    raw = net.get(url).content
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="ignore")
    text = text.lstrip("\ufeff \t\r\n")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        # 容忍 RSS 里常见的未转义 & 与控制字符
        cleaned = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", text)
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
        root = ET.fromstring(cleaned)
    items = []
    nodes = list(root.findall(".//item"))
    if not nodes:
        ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
        nodes = list(root.findall(".//%sentry" % ns))
    for item in nodes:
        t = (item.findtext("title") or "").strip()
        if not t:
            continue
        link = (item.findtext("link") or "").strip()
        if not link:
            for ch in item:
                if ch.tag.endswith("link") and ch.get("href"):
                    link = ch.get("href")
                    break
        desc = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()
        pub = (item.findtext("pubDate") or item.findtext("published") or "").strip()
        items.append(NewsItem(title=t, url=link, source=source_name,
                              summary=desc[:200], published=pub))
    return dedupe(items)[:n]


_NAV_WORDS = re.compile(
    r"(登录|注册|首页|导航|更多|下载|客户端|App|APP|English|版权|关于我们|联系我们|"
    r"招聘|隐私|帮助|意见反馈|网站地图|移动端|触屏版|电脑版|返回顶部|上一页|下一页|"
    r"Copyright|首页推荐|专题|排行榜|频道|社区|论坛|商城|会员|VIP|广告|免责)")


def parse_html_items(url, source_name, n=MAX_PER_SOURCE, must_have_date=False):
    """通用 HTML 链接抽取：同域优先，去导航噪声"""
    html = net.get_text(url)
    pairs = re.findall(r'<a[^>]*?href="([^"]+)"[^>]*?>([^<]{6,80})</a>', html)
    base_m = re.match(r"https?://[^/]+", url)
    base = base_m.group(0) if base_m else ""
    seen, items = set(), []
    for href, title in pairs:
        title = re.sub(r"\s+", " ", title).strip()
        if not title or "javascript" in href or href.startswith("#"):
            continue
        if _NAV_WORDS.search(title):
            continue
        if href.startswith("//"):
            link = "https:" + href
        elif href.startswith("/"):
            link = base + href
        elif href.startswith("http"):
            link = href
        else:
            continue
        if must_have_date and not re.search(r"/20\d{2}[-/]?\d{2}|\d{8}|/\d{6,}/", link):
            continue
        k = norm_title(title)
        if not k or k in seen:
            continue
        seen.add(k)
        items.append(NewsItem(title=title, url=link, source=source_name))
    # 同域链接优先
    items.sort(key=lambda it: 0 if (base and it.url.startswith(base)) else 1)
    return dedupe(items)[:n]


# ===========================================================================
# 专用抓取器
# ===========================================================================

def fetch_toutiao():
    d = net.get_json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    return [NewsItem(it.get("Title") or "", it.get("Url") or "", "头条", "新闻",
                     it.get("HotValue") or "")
            for it in (d.get("data") or [])[:MAX_PER_SOURCE]]


def fetch_weibo():
    d = net.get_json("https://weibo.com/ajax/side/hotSearch", referer="https://weibo.com/")
    rt = ((d.get("data") or {}).get("realtime") or [])
    out = []
    for it in rt[:MAX_PER_SOURCE]:
        w = it.get("word") or it.get("word_scheme") or ""
        if not w:
            continue
        out.append(NewsItem(w, "https://s.weibo.com/weibo?q=" + quote(w),
                            "微博", "新闻", it.get("num") or ""))
    return out


def fetch_baidu(tab="realtime", name="百度", category="新闻"):
    d = net.get_json("https://top.baidu.com/api/board?platform=wise&tab=%s" % tab,
                     referer="https://top.baidu.com/")
    out = []
    for card in (d.get("data") or {}).get("cards") or []:
        for block in card.get("content") or []:
            for it in block.get("content") or []:
                w = it.get("word") or it.get("query") or ""
                if not w:
                    continue
                out.append(NewsItem(w, it.get("url") or "", name, category,
                                    it.get("index") or it.get("hotScore") or ""))
    return out[:MAX_PER_SOURCE]


def fetch_tencent():
    d = net.get_json("https://r.inews.qq.com/gw/event/hot_ranking_list?page_size=50")
    out = []
    for lst in d.get("idlist") or []:
        for it in lst.get("newslist") or []:
            t = it.get("title") or it.get("longtitle") or ""
            if t:
                out.append(NewsItem(t, it.get("url") or "", "腾讯", "新闻",
                                    it.get("hotScore") or ""))
        break
    return out[:MAX_PER_SOURCE]


def fetch_zhihu():
    d = net.get_json("https://api.zhihu.com/topstory/hot-lists/total?limit=30",
                     referer="https://www.zhihu.com/")
    out = []
    for it in d.get("data") or []:
        tgt = it.get("target") or {}
        t = tgt.get("title") or tgt.get("titleArea") or {}
        if isinstance(t, dict):
            t = t.get("text") or ""
        t = (t or "").strip()
        if not t:
            continue
        nid = tgt.get("id") or ""
        out.append(NewsItem(t, "https://www.zhihu.com/question/%s" % nid if nid else "",
                            "知乎", "新闻", it.get("detail_text") or ""))
    if not out:
        raise RuntimeError("知乎接口无数据")
    return out[:MAX_PER_SOURCE]


def fetch_bilibili():
    """B站全站热门，主接口失败回退备用接口，再失败回退知乎热榜"""
    last = None
    for url in ("https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all",
                "https://api.bilibili.com/x/web-interface/popular?ps=30&pn=1"):
        try:
            d = net.get_json(url, referer="https://www.bilibili.com/")
            out = []
            for it in ((d.get("data") or {}).get("list") or []):
                link = it.get("short_link_v2") or \
                    ("https://www.bilibili.com/video/" + (it.get("bvid") or ""))
                out.append(NewsItem(it.get("title") or "", link, "B站", "视频",
                                    (it.get("stat") or {}).get("view") or ""))
            if out:
                return out[:MAX_PER_SOURCE]
        except Exception as e:                              # noqa: BLE001
            last = e
    # 注意：不要回退到知乎。回退条目自带 category=新闻，会让「视频」板块
    # 被算成 0 条（板块按条目自身分类过滤），等于视频源白装。宁可让源失败、
    # 在健康提示里暴露出来，也不要拿别的分类冒充。
    raise RuntimeError("B站接口均失败: %s" % last)


def fetch_36kr():
    d = net.post_json(
        "https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot",
        body={"partner_id": "wap", "param": {"siteId": 1, "platformId": 2}},
        referer="https://36kr.com/",
        headers={"Origin": "https://36kr.com", "Content-Type": "application/json"})
    out = []
    for it in ((d.get("data") or {}).get("hotRankList") or []):
        tm = it.get("templateMaterial") or {}
        t = (tm.get("widgetTitle") or "").strip()
        if not t:
            continue
        iid = tm.get("itemId") or it.get("itemId") or ""
        out.append(NewsItem(t, "https://36kr.com/p/%s" % iid if iid else "",
                            "36氪", "科技", tm.get("statRead") or ""))
    if not out:
        raise RuntimeError("36氪接口无数据")
    return out[:MAX_PER_SOURCE]


def fetch_cls_telegraph():
    """财联社电报"""
    d = net.get_json(
        "https://www.cls.cn/nodeapi/telegraphList?app=CailianpressWeb&os=web&sv=7.7.5"
        "&rn=30&sign=", referer="https://www.cls.cn/")
    out = []
    for it in (d.get("data") or {}).get("roll_data") or []:
        t = (it.get("title") or it.get("brief") or "").strip()
        if not t:
            t = (it.get("content") or "").strip()
        if not t:
            continue
        out.append(NewsItem(t[:60], "https://www.cls.cn/detail/%s" % (it.get("id") or ""),
                            "财联社", "财经", it.get("read_num") or ""))
    if not out:
        raise RuntimeError("财联社接口无数据")
    return out[:MAX_PER_SOURCE]


def _cctv_column(col_id, name, n=8):
    d = net.get_json(
        "http://api.cntv.cn/NewVideo/getVideoListByColumn?id=%s&n=%d&sort=desc"
        "&p=1&mode=0&serviceId=tvcctv" % (col_id, n))
    out = []
    for it in ((d.get("data") or {}).get("list") or []):
        t = re.sub(r"^\s*《[^》]+》\s*", "", it.get("title") or "").strip()
        t = re.sub(r"^\d{6,8}(\s+\d{3,4})?\s*", "", t).strip()
        if t:
            out.append(NewsItem(t, it.get("url") or "", name, "新闻"))
    return out


def fetch_cctv_news():
    """《新闻联播》节目简介拆条，得到当日最高级别要闻"""
    d = net.get_json(
        "http://api.cntv.cn/NewVideo/getVideoListByColumn?id=TOPC1451528971114112"
        "&n=6&sort=desc&p=1&mode=0&serviceId=tvcctv")
    out = []
    for ep in ((d.get("data") or {}).get("list") or []):
        brief, url = ep.get("brief") or "", ep.get("url") or ""
        for line in re.split(r"[；;]", brief):
            line = re.sub(r"^(本期节目主要内容|主要内容)[:：]?\s*", "", line).strip()
            line = re.sub(r"^\s*\d+[\.、)\s]+", "", line).strip()
            line = re.sub(r"^《[^》]+》", "", line).strip()
            line = re.sub(r"^\d{4}年\d{1,2}月\d{1,2}日", "", line).strip()
            if len(line) < 5:
                continue
            out.append(NewsItem(line, url, "央视", "新闻"))
    if not out:
        raise RuntimeError("央视接口无数据")
    return dedupe(out)[:MAX_PER_SOURCE]


def fetch_cctv_finance():
    out = []
    try:
        out += _cctv_column("TOPC1451533782742171", "央视财经", 8)
    except Exception:                                       # noqa: BLE001
        pass
    try:
        out += _cctv_column("TOPC1451533652476962", "央视财经", 8)
    except Exception:                                       # noqa: BLE001
        pass
    if not out:
        raise RuntimeError("央视财经接口无数据")
    return dedupe(out)[:MAX_PER_SOURCE]


def fetch_sina_nba():
    html = net.get_text("https://sports.sina.com.cn/nba/")
    pairs = re.findall(
        r'<a[^>]*href="(https?://sports\.sina\.com\.cn/(?:nba|basketball)/[^"]+)"[^>]*>'
        r'([^<]{6,80})</a>', html)
    out = []
    for url, title in pairs:
        title = title.strip()
        if not title or title.startswith("javascript"):
            continue
        out.append(NewsItem(title, url, "新浪NBA", "体育"))

    def dk(it):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", it.url)
        return m.groups() if m else ("0000", "00", "00")
    out.sort(key=dk, reverse=True)
    return dedupe(out)[:MAX_PER_SOURCE]


def fetch_people_military():
    html = net.get_text("http://military.people.com.cn/")
    pairs = re.findall(
        r'<a[^>]*href="(https?://military\.people\.com\.cn/[^"]+)"[^>]*>([^<]{8,80})</a>',
        html)
    out = []
    for url, title in pairs:
        title = title.strip()
        if not title or "12377" in url or "beian" in url:
            continue
        out.append(NewsItem(title, url, "人民网军事", "军事"))

    def dk(it):
        m = re.search(r"/(\d{4})/(\d{4})/", it.url)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        m = re.search(r"(\d{4})/(\d{2})/(\d{2})", it.url)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    out.sort(key=dk, reverse=True)
    return dedupe(out)[:MAX_PER_SOURCE]


# ===========================================================================
# Source 定义
# ===========================================================================

class Source:
    def __init__(self, sid, name, category, fetcher, builtin=True, desc="",
                 custom=None, default_on=True):
        self.id = sid
        self.name = name
        self.category = category
        self.fetcher = fetcher
        self.builtin = builtin
        self.desc = desc or ""
        self.custom = custom or {}
        self.default_on = default_on

        self.on = default_on
        self.state = "idle"          # idle / ok / fail / testing / cooled
        self.last_error = ""
        self.last_ms = 0.0
        self.ok_count = 0
        self.fail_count = 0
        self.consecutive_fails = 0
        self.cooldown_until = 0.0
        self.item_count = 0

    # ------------------------------------------------------------ 健康度
    @property
    def total(self):
        return self.ok_count + self.fail_count

    @property
    def success_rate(self):
        return (self.ok_count / self.total) if self.total else 0.0

    @property
    def health(self):
        """0~1 综合健康分，用于排序与自动降级"""
        if self.total == 0:
            return 0.5
        base = self.success_rate
        if self.consecutive_fails >= CIRCUIT_FAILS:
            base *= 0.3
        return round(base, 3)

    @property
    def is_cooled(self):
        return time.time() < self.cooldown_until

    def record_ok(self, ms, count):
        self.state = "ok"
        self.last_error = ""
        self.last_ms = ms
        self.ok_count += 1
        self.consecutive_fails = 0
        self.cooldown_until = 0.0
        self.item_count = count

    def record_fail(self, ms, err):
        self.state = "fail"
        self.last_error = str(err)[:120]
        self.last_ms = ms
        self.fail_count += 1
        self.consecutive_fails += 1
        self.item_count = 0
        if self.consecutive_fails >= CIRCUIT_FAILS:
            self.cooldown_until = time.time() + CIRCUIT_COOLDOWN
            self.state = "cooled"

    def reset_circuit(self):
        self.consecutive_fails = 0
        self.cooldown_until = 0.0
        self.state = "idle"

    def __repr__(self):
        return "<Source %s/%s>" % (self.id, self.name)


# ---------------------------------------------------------------------------
# 内置源注册表
# ---------------------------------------------------------------------------

BUILTIN_DEFS = [
    # id, 名称, 分类, 抓取器, 说明
    ("toutiao", "头条热榜", "新闻", fetch_toutiao, "今日头条实时热榜"),
    ("weibo", "微博热搜", "新闻", fetch_weibo, "微博实时热搜榜"),
    ("baidu", "百度热搜", "新闻", lambda: fetch_baidu("realtime", "百度", "新闻"), "百度实时热搜"),
    ("tencent", "腾讯新闻", "新闻", fetch_tencent, "腾讯新闻热榜"),
    ("zhihu", "知乎热榜", "新闻", fetch_zhihu, "知乎全站热榜"),
    ("cctv_news", "央视新闻", "新闻", fetch_cctv_news, "《新闻联播》当日要闻拆条"),
    ("ifeng", "凤凰网资讯", "新闻",
     lambda: parse_html_items("https://news.ifeng.com/", "凤凰网"), "凤凰网首页要闻"),
    ("ithome", "IT之家", "科技", lambda: parse_rss_items("https://www.ithome.com/rss/", "IT之家"),
     "IT之家 RSS（科技数码）"),
    ("sspai", "少数派", "科技", lambda: parse_rss_items("https://sspai.com/feed", "少数派"),
     "少数派 RSS（效率工具）"),
    ("kr36", "36氪热榜", "科技", fetch_36kr, "36氪热门文章榜"),
    ("baidu_finance", "百度财经", "财经", lambda: fetch_baidu("finance", "百度财经", "财经"), "百度财经热搜"),
    ("cctv_finance", "央视财经", "财经", fetch_cctv_finance, "经济信息联播 + 经济半小时"),
    ("eastmoney", "东方财富", "财经",
     lambda: parse_html_items("https://finance.eastmoney.com/", "东方财富"), "东方财富首页财经要闻"),
    ("people_finance", "人民网财经", "财经",
     lambda: parse_html_items("http://finance.people.com.cn/", "人民网财经"), "人民网财经频道要闻"),
    ("sina_nba", "新浪NBA", "体育", fetch_sina_nba, "新浪 NBA 频道最新报道"),
    ("baidu_sports", "百度体育", "体育", lambda: fetch_baidu("sports", "百度体育", "体育"), "百度体育热搜"),
    ("people_mil", "人民网军事", "军事", fetch_people_military, "人民网军事频道"),
    # 中国军网必须开 must_have_date：首页导航项（国防教育/军事记者…）会被日期规则滤掉
    ("pla_mil", "中国军网", "军事",
     lambda: parse_html_items("http://www.81.cn/", "中国军网", must_have_date=True),
     "中国军网首页要闻（已过滤导航项）"),
    ("bilibili", "B站热门", "视频", fetch_bilibili, "B站全站热门（受网络限制时可能不可用）"),
    ("guancha_video", "观察者网视频", "视频",
     lambda: parse_html_items("https://www.guancha.cn/video", "观察者网"), "观察者网视频频道"),
]

# 页面里偶有的榜单说明/运营文案，不是真正的新闻标题
_JUNK = re.compile(
    r"(用户最关注|每\d+\s*分钟更新|榜单介绍|榜单规则|热榜规则|点击查看详情|"
    r"数据来源于|本榜单|^\.{2,}$|^\-+$)")


def clean_items(items):
    """剔除非新闻性质的噪声标题"""
    out = []
    for it in items or []:
        t = (it.title or "").strip()
        if not t or len(t) < 4:
            continue
        if _JUNK.search(t):
            continue
        out.append(it)
    return out


def build_builtin_sources():
    return [Source(sid, name, cat, fn, builtin=True, desc=desc)
            for (sid, name, cat, fn, desc) in BUILTIN_DEFS]


def make_custom_source(defn):
    """按持久化定义构造自定义源"""
    mode = defn.get("mode", "html")
    sid = defn.get("id") or ("custom_%s" % abs(hash(defn.get("url", ""))))
    name = defn.get("name") or sid
    url = defn.get("url", "")
    cat = defn.get("category") or "自定义"
    if mode == "json":
        fn = lambda: parse_json_items(url, name)
    elif mode == "json_post":
        if "36kr" in url or "36氪" in name:
            fn = fetch_36kr
        else:
            fn = lambda: parse_json_post_items(
                url, name, body={"partner_id": "wap",
                                 "param": {"siteId": 1, "platformId": 2}})
    elif mode == "rss":
        fn = lambda: parse_rss_items(url, name)
    else:
        fn = lambda: parse_html_items(url, name)
    return Source(sid, name, cat, fn, builtin=False, desc=url, custom=defn)


# ===========================================================================
# 模板库（AI 添加源 / 源修复时推荐）
# ===========================================================================

T = lambda name, kw, cat, url, mode: dict(
    name=name, keywords=kw, category=cat, url=url, mode=mode)

AI_TEMPLATES = [
    T("36氪", ["36氪", "36kr", "创投", "科技"], "科技",
      "https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot", "json_post"),
    T("IT之家", ["IT之家", "ithome", "数码", "科技", "手机"], "科技",
      "https://www.ithome.com/rss/", "rss"),
    T("少数派", ["少数派", "sspai", "效率", "工具"], "科技",
      "https://sspai.com/feed", "rss"),
    T("虎嗅", ["虎嗅", "huxiu", "商业", "科技"], "科技", "https://www.huxiu.com/", "html"),
    T("爱范儿", ["爱范儿", "ifanr", "数码", "科技"], "科技", "https://www.ifanr.com/", "html"),
    T("钛媒体", ["钛媒体", "tmtpost", "创投", "科技"], "科技", "https://www.tmtpost.com/", "html"),
    T("中关村在线", ["中关村在线", "zol", "数码", "电脑"], "科技", "https://www.zol.com.cn/", "html"),
    T("网易新闻", ["网易", "163", "新闻"], "新闻", "https://news.163.com/", "html"),
    T("凤凰网资讯", ["凤凰", "ifeng", "新闻", "资讯"], "新闻", "https://news.ifeng.com/", "html"),
    T("澎湃新闻", ["澎湃", "thepaper", "新闻"], "新闻", "https://www.thepaper.cn/", "html"),
    T("新华网", ["新华", "news.cn", "新华社"], "新闻", "http://www.news.cn/", "html"),
    T("环球网", ["环球", "huanqiu", "国际"], "新闻", "https://www.huanqiu.com/", "html"),
    T("中国新闻网", ["中新网", "chinanews", "新闻"], "新闻", "https://www.chinanews.com.cn/", "html"),
    T("参考消息", ["参考消息", "cankaoxiaoxi", "国际"], "新闻", "https://www.cankaoxiaoxi.com/", "html"),
    T("人民网", ["人民网", "people", "新闻"], "新闻", "http://www.people.com.cn/", "html"),
    T("界面新闻", ["界面", "jiemian", "财经", "新闻"], "新闻", "https://www.jiemian.com/", "html"),
    T("第一财经", ["第一财经", "yicai", "财经"], "财经", "https://www.yicai.com/", "html"),
    T("东方财富", ["东方财富", "eastmoney", "股票", "基金"], "财经", "https://finance.eastmoney.com/", "html"),
    T("新浪财经", ["新浪财经", "sina", "股票"], "财经", "https://finance.sina.com.cn/", "html"),
    T("雪球", ["雪球", "xueqiu", "投资", "股票"], "财经", "https://xueqiu.com/", "html"),
    T("虎扑", ["虎扑", "hupu", "篮球", "体育"], "体育", "https://bbs.hupu.com/", "html"),
    T("直播吧", ["直播吧", "zhibo8", "足球", "篮球"], "体育", "https://www.zhibo8.cc/", "html"),
    T("懂球帝", ["懂球帝", "dongqiudi", "足球"], "体育", "https://www.dongqiudi.com/", "html"),
    T("腾讯体育", ["腾讯体育", "sports.qq", "NBA"], "体育", "https://sports.qq.com/", "html"),
    T("新浪军事", ["新浪军事", "mil.sina", "武器"], "军事", "https://mil.news.sina.com.cn/", "html"),
    T("环球军事", ["环球军事", "mil.huanqiu", "军事"], "军事", "https://mil.huanqiu.com/", "html"),
    T("游民星空", ["游民", "gamersky", "游戏", "单机"], "游戏", "https://www.gamersky.com/", "html"),
    T("3DM游戏", ["3DM", "3dmgame", "游戏"], "游戏", "https://www.3dmgame.com/", "html"),
    T("什么值得买", ["值得买", "smzdm", "优惠", "购物"], "消费", "https://www.smzdm.com/", "html"),
    T("汽车之家", ["汽车之家", "autohome", "汽车"], "汽车", "https://www.autohome.com.cn/", "html"),
    T("懂车帝", ["懂车帝", "dongchedi", "汽车"], "汽车", "https://www.dongchedi.com/", "html"),
]

RECOMMEND_BY_CATEGORY = {
    "科技": ["IT之家", "36氪", "虎嗅", "少数派", "爱范儿"],
    "新闻": ["网易新闻", "澎湃新闻", "凤凰网资讯", "新华网", "中国新闻网"],
    "财经": ["第一财经", "东方财富", "新浪财经", "界面新闻", "雪球"],
    "体育": ["虎扑", "直播吧", "懂球帝", "腾讯体育"],
    "军事": ["新浪军事", "环球军事"],
    "视频": [],
    "游戏": ["游民星空", "3DM游戏"],
    "消费": ["什么值得买"],
    "汽车": ["汽车之家", "懂车帝"],
}


def match_templates(query, sources=None):
    """关键词匹配模板，返回 (模板列表, 是否为推荐而非命中)"""
    q = (query or "").strip()
    if not q:
        return [], False
    scored = []
    for t in AI_TEMPLATES:
        sc = 0
        if q in t["name"]:
            sc += 10
        for kw in t["keywords"]:
            if q in kw or kw in q:
                sc += 5
        if q.lower() in t["url"].lower():
            sc += 3
        if sc:
            scored.append((sc, t))
    scored.sort(key=lambda x: -x[0])
    if scored:
        return [t for _, t in scored[:12]], False

    # 无命中 -> 按当前已有源的分类推荐
    cats = [s.category for s in (sources or []) if s.on]
    rec = []
    for c in dict.fromkeys(cats):
        for nm in RECOMMEND_BY_CATEGORY.get(c, []):
            t = next((x for x in AI_TEMPLATES if x["name"] == nm), None)
            if t and t not in rec:
                rec.append(t)
    return rec[:10], True


def probe_source(url, source_name="探测"):
    """探测 URL 可解析结构，返回 (mode, 样例条数, 说明)"""
    try:
        resp = net.get(url)
    except Exception as e:                                  # noqa: BLE001
        return "html", 0, "无法访问：%s" % e
    ctype = (resp.headers.get("Content-Type") or "").lower()
    head = resp.content[:2000].decode("utf-8", errors="ignore").lstrip("\ufeff \t\r\n").lower()
    if "json" in ctype or head.startswith("{"):
        mode = "json"
    elif head.startswith("<?xml") or "<rss" in head or "<feed" in head:
        mode = "rss"
    else:
        mode = "html"
    try:
        if mode == "json":
            n = len(parse_json_items(url, source_name, 5))
        elif mode == "rss":
            n = len(parse_rss_items(url, source_name, 5))
        else:
            n = len(parse_html_items(url, source_name, 5))
    except Exception as e:                                  # noqa: BLE001
        return mode, 0, "解析失败：%s" % e
    desc = {"json": "JSON 接口", "rss": "RSS/Atom 订阅源", "html": "网页链接抓取"}[mode]
    return mode, n, "%s，样例解析 %d 条" % (desc, n)
