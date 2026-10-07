# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 网络层

要点：
- 每线程独立 Session（requests.Session 非严格线程安全），复用连接池显著提速
- https 被重置时自动降级 http 重试（部分央视/人民网站点的常见现象）
- 编码嗅探：utf-8 / gbk / gb18030 / big5
"""

import re
import threading

import requests
from requests.adapters import HTTPAdapter

from .config import HEADERS, TIMEOUT

_local = threading.local()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        ad = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
        s.mount("http://", ad)
        s.mount("https://", ad)
        _local.s = s
    return s


def _decode(raw):
    for enc in ("utf-8", "gbk", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore")


def get(url, referer=None, timeout=TIMEOUT, retry=1, ua=None):
    """GET，返回 Response；失败抛 requests.RequestException"""
    headers = None
    if referer or ua:
        headers = {}
        if referer:
            headers["Referer"] = referer
        if ua:
            headers["User-Agent"] = ua
    last = None
    for attempt in range(retry + 1):
        try:
            r = session().get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            # https 被重置 -> 降级 http
            if url.startswith("https://") and _is_conn_error(e):
                alt = "http://" + url[len("https://"):]
                try:
                    r = session().get(alt, headers=headers, timeout=timeout)
                    r.raise_for_status()
                    return r
                except requests.RequestException as e2:
                    last = e2
    raise last


def _is_conn_error(e):
    return isinstance(e, (requests.exceptions.ConnectionError,
                          requests.exceptions.SSLError,
                          requests.exceptions.ReadTimeout))


def get_json(url, referer=None, timeout=TIMEOUT, retry=1):
    r = get(url, referer=referer, timeout=timeout, retry=retry)
    try:
        return r.json()
    except ValueError:
        # 部分接口外层套了 jsonp 或带 BOM
        txt = _decode(r.content).strip()
        m = re.search(r"^[^(]*\((.*)\)\s*;?$", txt, re.S)
        import json
        return json.loads(m.group(1) if m else txt)


def get_text(url, referer=None, timeout=TIMEOUT, retry=1):
    return _decode(get(url, referer=referer, timeout=timeout, retry=retry).content)


def post_json(url, body=None, referer=None, timeout=TIMEOUT, headers=None):
    h = dict(HEADERS)
    if referer:
        h["Referer"] = referer
    if headers:
        h.update(headers)
    r = session().post(url, headers=h, json=body or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
             "Mobile/15E148 Safari/604.1")


def normalize_article_url(url):
    """桌面版是纯 JS 空壳、移动端才服务端渲染正文的站点，改指向移动端

    实测：www.toutiao.com/article/<id>/ 一个 <p> 都没有，
          而 m.toutiao.com/i<id>/ 有完整段落。
    """
    if not url:
        return url
    m = re.match(r"(?i)^https?://(?:www\.)?toutiao\.com/(?:article|w|group)/(\d+)", url)
    if m:
        return "https://m.toutiao.com/i%s/" % m.group(1)
    return url


def _unescape(s):
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", "\""), ("&#39;", "'"), ("&ldquo;", "\u201c"),
                 ("&rdquo;", "\u201d"), ("&mdash;", "\u2014"), ("&hellip;", "\u2026")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _meta_desc(html):
    """取 og:description / meta description，作为正文拿不到时的兜底摘要"""
    pats = [
        r"(?is)<meta[^>]+property=[\"']og:description[\"'][^>]+content=[\"']([^\"']+)[\"']",
        r"(?is)<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:description[\"']",
        r"(?is)<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']+)[\"']",
        r"(?is)<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+name=[\"']description[\"']",
        r"(?is)<meta[^>]+name=[\"']twitter:description[\"'][^>]+content=[\"']([^\"']+)[\"']",
    ]
    for pat in pats:
        m = re.search(pat, html)
        if m:
            d = _unescape(m.group(1))
            if len(d) >= 12:
                return d
    return ""


def _ld_json_body(html):
    """从 JSON-LD 里挖 articleBody"""
    import json
    best = ""

    def walk(o):
        nonlocal best
        if isinstance(o, dict):
            v = o.get("articleBody")
            if isinstance(v, str) and len(v) > len(best):
                best = v
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    for m in re.finditer(
            r"(?is)<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", html):
        try:
            walk(json.loads(m.group(1).strip()))
        except Exception:                                   # noqa: BLE001
            continue
    return _unescape(best) if best else ""


def _split_paras(seg):
    """从一段 HTML 里切出段落：<p> 优先，否则按 <br> / 块级标签闭合切"""
    paras = [_unescape(re.sub(r"<[^>]+>", "", p))
             for p in re.findall(r"(?is)<p[^>]*>(.*?)</p>", seg)]
    paras = [p for p in paras if len(p) >= 15]
    if paras:
        return paras
    raw = re.sub(r"(?is)<br\s*/?>", "\n", seg)
    raw = re.sub(r"(?is)</(?:div|p|section|h\d|li|blockquote|td)>", "\n", raw)
    parts = [_unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in raw.split("\n")]
    return [p for p in parts if len(p) >= 15]


_CONTAINER_PATS = [
    r"(?is)<article[^>]*>(.*?)</article>",
    r"(?is)<(?:div|section)[^>]*(?:class|id)=[\"'][^\"']*"
    r"(?:article[-_]?content|post[-_]?content|articleContent|"
    r"content[-_]?article|article[-_]?detail|content[-_]?detail|"
    r"news[-_]?content|article[-_]?body|post[-_]?body|rich_media_content|"
    r"article[-_]?content[-_]?text|entry[-_]?content|main[-_]?content|"
    r"content[-_]?main)[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
    r"(?is)<(?:div|section)[^>]*(?:class|id)=[\"'][^\"']*"
    r"(?:content|article|post|news|detail|text|body)[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
]

_NOISE = re.compile(r"(版权声明|责任编辑|点击查看|扫一扫|分享到|来源[:：]|原标题[:：]|"
                    r"特别声明|本文由|免责声明|广告声明|微信公众|打开APP|下载客户端)")


def _extract_from_html(html, url):
    """返回 (段落, 图片, 视频, 备注, 摘要)"""
    vids = []
    for mm in re.finditer(r"(?is)<(?:video|iframe)[^>]*>", html):
        tag = mm.group(0)
        for attr in ("src", "data-src", "data-vid", "data-original"):
            sm = re.search(attr + "=[\"']([^\"']+)[\"']", tag)
            if sm and sm.group(1).startswith("http"):
                vids.append(sm.group(1))
                break
    html = re.sub(r"(?is)<(script|style|noscript|iframe)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)

    best_seg, best_paras = None, []
    for pat in _CONTAINER_PATS:
        for m in re.finditer(pat, html):
            seg, paras = m.group(1), _split_paras(m.group(1))
            if len(paras) > len(best_paras):
                best_paras, best_seg = paras, seg
        if best_paras:
            break                       # 命中更高优先级的容器就不需要更宽的匹配

    note = ""
    if not best_paras:
        body = _ld_json_body(html)
        if body:
            best_paras = [body[i:i + 400] for i in range(0, len(body), 400)][:12]
            note = "正文取自页面结构化数据"
    if not best_paras:
        # 注意这里必须是捕获组，\1 才能引用；写成 (?:...) 会报 invalid group reference
        page = re.sub(r"(?is)<(header|nav|footer)[^>]*>.*?</\1>", " ", html)
        whole = _split_paras(page)
        if whole:
            best_paras = whole[:30]
    if not best_paras:
        # 最后兜底：整页去标签后按固定长度切块。
        # 搜索结果页、纯文本页靠这个才能显示出东西，所以必须留着。
        body = _unescape(re.sub(r"<[^>]+>", " ", re.sub(
            r"(?is)<(header|nav|footer)[^>]*>.*?</\1>", " ", html)))
        if len(re.findall(r"[\u4e00-\u9fa5]", body)) >= 60:
            best_paras = [body[i:i + 300] for i in range(0, min(len(body), 2400), 300)]
            note = "正文由整页文本兜底提取，建议用「浏览器打开」核对原文"

    try:
        from urllib.parse import urlparse
        p0 = urlparse(url)
        base = "%s://%s" % (p0.scheme, p0.netloc)
    except Exception:                                       # noqa: BLE001
        base = ""

    imgs = []
    for mm in re.finditer(r"(?is)<img[^>]*>", best_seg or html):
        sm = re.search(r"(?:src|data-src|data-original)=[\"']([^\"']+)[\"']", mm.group(0))
        if not sm:
            continue
        p = sm.group(1).strip()
        if p.startswith("//"):
            p = "https:" + p
        elif p.startswith("/") and base:
            p = base + p
        elif not p.startswith("http") and base:
            p = base + "/" + p.lstrip("/")
        if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")) or "image" in p.lower():
            imgs.append(p)

    clean = [p for p in best_paras if len(p) >= 15 and not _NOISE.search(p[:40])]

    # 质量闸门：抓到的是验证页 / 导航碎片时，中文量会极低。
    # 这种"成功"比明确报错更糟——用户会以为看到的就是正文。
    cn = sum(len(re.findall(r"[\u4e00-\u9fa5]", p)) for p in clean)
    if cn < 40:
        return [], imgs[:6], vids[:5], note, _meta_desc(html)
    return clean[:30], imgs[:6], vids[:5], note, _meta_desc(html)


def _brief_err(e):
    s = str(e)
    if "403" in s:
        return "原文站点拒绝访问（403），请点右上角「浏览器打开」"
    if "ProxyError" in s or "proxy" in s.lower():
        return "网络被代理或防火墙拦截，请点右上角「浏览器打开」"
    if "SSLError" in s:
        return "该站点 HTTPS 握手失败，请点右上角「浏览器打开」"
    return "无法访问原文：%s" % s[:80]


def extract_article(url, timeout=8):
    """
    抓取并提取正文。
    返回 (段落 or None, 图片URL, 视频URL, 错误 or None, 备注)
    """
    if not url:
        return None, [], [], "该条目无原文链接", ""

    norm = normalize_article_url(url)
    tries = []
    if norm != url:
        tries.append((norm, MOBILE_UA))     # 移动端 SSR 版优先
    tries.append((url, None))               # 原地址
    tries.append((url if norm == url else norm,
                  MOBILE_UA if norm == url else None))

    err, desc = None, ""
    for u, ua in tries:
        try:
            r = get(u, timeout=timeout, ua=ua)
        except Exception as e:                              # noqa: BLE001
            err = err or _brief_err(e)
            continue
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "json" in ctype or r.content[:1] in (b"{", b"["):
            return None, [], [], "该来源为数据接口，无独立文章正文", ""
        paras, imgs, vids, note, d = _extract_from_html(_decode(r.content), u)
        if d and not desc:
            desc = d
        if paras:
            return paras, imgs, vids, None, note

    # 拿不到正文但有摘要：至少让阅读器有内容可看
    if desc:
        return [desc], [], [], None, "仅取到摘要，完整正文请用「浏览器打开」"
    return (None, [], [],
            err or "该站正文由脚本动态加载，内置阅读器读不到，请点右上角「浏览器打开」", "")
