# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 导出

支持 HTML（自包含样式报告）/ Markdown / TXT / CSV / JSON
"""

import csv
import datetime
import json
import os

from .config import APP_NAME, VERSION, export_dir

CSS = """
:root{--bg:#f4f6f9;--card:#fff;--fg:#1f2937;--sub:#64748b;--accent:#3b82f6;
--border:#e5e9f0;--tag:#eff6ff;--tagfg:#2563eb;}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;background:var(--bg);color:var(--fg);
font-family:"Microsoft YaHei UI","PingFang SC","Noto Sans CJK SC",sans-serif;
-webkit-font-smoothing:antialiased;}
.wrap{max-width:860px;margin:0 auto}
.hero{background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;border-radius:16px;
padding:28px 30px;margin-bottom:24px;box-shadow:0 10px 30px rgba(59,130,246,.25)}
.hero h1{margin:0 0 6px;font-size:26px;letter-spacing:.5px}
.hero p{margin:0;opacity:.9;font-size:13px}
.stat{display:flex;gap:22px;margin-top:16px;flex-wrap:wrap}
.stat div{font-size:12px;opacity:.92}.stat b{display:block;font-size:20px;margin-bottom:2px}
h2{font-size:15px;margin:26px 0 12px;padding-left:10px;border-left:4px solid var(--accent)}
ol{list-style:none;padding:0;margin:0}
li{background:var(--card);border:1px solid var(--border);border-radius:12px;
padding:14px 16px;margin-bottom:10px;display:flex;gap:14px;align-items:flex-start;
transition:box-shadow .15s}
li:hover{box-shadow:0 4px 16px rgba(15,23,42,.08)}
.rank{flex:0 0 30px;height:30px;border-radius:9px;background:var(--tag);color:var(--tagfg);
font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center}
.rank.top{background:#ef4444;color:#fff}
.body{flex:1;min-width:0}
.t{font-size:14.5px;line-height:1.55;font-weight:600;word-break:break-word}
.t a{color:inherit;text-decoration:none}.t a:hover{color:var(--accent)}
.m{margin-top:7px;font-size:12px;color:var(--sub);display:flex;gap:8px;flex-wrap:wrap;
align-items:center}
.tag{background:var(--tag);color:var(--tagfg);padding:2px 8px;border-radius:6px;font-size:11px}
.badge{padding:2px 7px;border-radius:6px;font-size:11px;font-weight:600}
.b-new{background:#dbeafe;color:#2563eb}.b-surge{background:#fee2e2;color:#dc2626}
.b-up{background:#fef3c7;color:#b45309}.b-down{background:#f1f5f9;color:#64748b}
.src{font-size:11px;color:var(--sub)}
footer{margin-top:32px;text-align:center;color:var(--sub);font-size:12px}
"""

BADGE_CLASS = {"new": "b-new", "surge": "b-surge", "up": "b-up",
               "down": "b-down", "drop": "b-down", "flat": ""}


def _safe(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def default_filename(fmt):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    name = "热点速览_%s.%s" % (ts, fmt)
    return os.path.join(export_dir(), name)


def export_html(entries, path, title=None, subtitle=""):
    title = title or "%s %s" % (APP_NAME, datetime.datetime.now().strftime("%Y-%m-%d"))
    groups = {}
    for e in entries:
        groups.setdefault(e.cluster.category, []).append(e)

    stats = dict(total=len(entries), clusters=len(groups),
                 sources=len({s for e in entries for s in e.sources}))

    p = []
    p.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>")
    p.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    p.append("<title>%s</title><style>%s</style></head><body><div class='wrap'>" %
             (_safe(title), CSS))
    p.append("<div class='hero'><h1>%s</h1>" % _safe(title))
    p.append("<p>%s</p>" % _safe(subtitle or datetime.datetime.now().strftime(
        "%Y年%m月%d日 %H:%M 生成 · %s v%s") % (APP_NAME, VERSION) if False else
        datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M 生成") + " · %s v%s" % (APP_NAME, VERSION)))
    p.append("<div class='stat'><div><b>%d</b>事件</div><div><b>%d</b>板块</div>"
             "<div><b>%d</b>数据源</div></div></div>" %
             (stats["total"], stats["clusters"], stats["sources"]))

    for cat in sorted(groups.keys()):
        p.append("<h2>%s</h2><ol>" % _safe(cat))
        for i, e in enumerate(groups[cat], 1):
            c = e.cluster
            cls = "rank top" if i <= 3 else "rank"
            badge = ""
            if e.trend.kind != "flat" and e.trend.label:
                bc = BADGE_CLASS.get(e.trend.style, "")
                badge = "<span class='badge %s'>%s</span>" % (bc, _safe(e.trend.label))
            if c.source_count > 1:
                badge += "<span class='badge b-new'>%d源</span>" % c.source_count
            title_html = (_safe(c.title) if not c.url
                          else "<a href='%s' target='_blank'>%s</a>" %
                          (_safe(c.url), _safe(c.title)))
            srcs = " · ".join(c.sources[:6])
            heat = ("<span class='tag'>🔥 %s</span>" % _safe(c.heat_display)
                    if c.heat_display else "")
            p.append("<li><div class='%s'>%d</div><div class='body'>"
                     "<div class='t'>%s</div>"
                     "<div class='m'>%s<span class='src'>%s</span>%s%s</div>"
                     "</div></li>" %
                     (cls, i, title_html, heat, _safe(srcs),
                      "<span class='src'>· %s</span>" % c.time_display,
                      badge))
        p.append("</ol>")

    p.append("<footer>由 %s v%s 生成</footer></div></body></html>" % (APP_NAME, VERSION))
    html = "".join(p)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def export_markdown(entries, path, title=None):
    title = title or "%s %s" % (APP_NAME, datetime.datetime.now().strftime("%Y-%m-%d"))
    lines = ["# %s" % title,
             "",
             "> 生成时间：%s　|　共 %d 个事件" %
             (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), len(entries)),
             ""]
    groups = {}
    for e in entries:
        groups.setdefault(e.cluster.category, []).append(e)
    for cat in sorted(groups.keys()):
        lines.append("## %s" % cat)
        lines.append("")
        for i, e in enumerate(groups[cat], 1):
            c = e.cluster
            t = ("[%s](%s)" % (c.title.replace("[", "(").replace("]", ")"), c.url)
                 if c.url else c.title)
            marks = []
            if e.trend.label:
                marks.append(e.trend.label)
            if c.source_count > 1:
                marks.append("%d源" % c.source_count)
            if c.heat_display:
                marks.append("热度 %s" % c.heat_display)
            marks.append("、".join(c.sources[:5]))
            lines.append("%d. %s" % (i, t))
            lines.append("   - %s" % " · ".join(marks))
        lines.append("")
    txt = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)
    return path


def export_txt(entries, path, title=None):
    title = title or "%s %s" % (APP_NAME, datetime.datetime.now().strftime("%Y-%m-%d"))
    lines = [title, "=" * 60,
             "生成时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
             "共 %d 个事件" % len(entries), ""]
    groups = {}
    for e in entries:
        groups.setdefault(e.cluster.category, []).append(e)
    for cat in sorted(groups.keys()):
        lines.append("[%s]" % cat)
        for i, e in enumerate(groups[cat], 1):
            c = e.cluster
            tag = ("[%s]" % e.trend.label) if e.trend.label else ""
            multi = ("[%d源]" % c.source_count) if c.source_count > 1 else ""
            lines.append("%3d. %s %s%s" % (i, c.title, tag, multi))
            lines.append("     来源：%s" % "、".join(c.sources[:6]))
            if c.url:
                lines.append("     链接：%s" % c.url)
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def export_csv(entries, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["排名", "分类", "标题", "来源数", "来源", "热度", "时间", "链接"])
        for e in entries:
            c = e.cluster
            w.writerow([e.rank, c.category, c.title, c.source_count,
                        "、".join(c.sources), c.heat_display or "",
                        c.time_display, c.url])
    return path


def export_json(entries, path):
    data = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "app": APP_NAME, "version": VERSION, "count": len(entries),
        "items": [{
            "rank": e.rank,
            "title": e.cluster.title,
            "category": e.cluster.category,
            "sources": e.cluster.sources,
            "source_count": e.cluster.source_count,
            "heat": e.cluster.heat,
            "url": e.cluster.url,
            "trend": e.trend.kind,
            "time": e.cluster.time_display,
            "related": [{"source": it.source, "title": it.title, "url": it.url}
                        for it in e.cluster.items],
        } for e in entries],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


EXPORTERS = {
    "html": (export_html, "网页报告", ".html", "HTML 文件"),
    "md": (export_markdown, "Markdown", ".md", "Markdown 文件"),
    "txt": (export_txt, "纯文本", ".txt", "文本文件"),
    "csv": (export_csv, "表格 CSV", ".csv", "CSV 文件"),
    "json": (export_json, "结构化 JSON", ".json", "JSON 文件"),
}


def export(fmt, entries, path=None, **kw):
    if fmt not in EXPORTERS:
        raise ValueError("不支持的格式：%s" % fmt)
    fn = EXPORTERS[fmt][0]
    return fn(entries, path or default_filename(fmt), **kw)
