# -*- coding: utf-8 -*-
"""第二批候选源探测（JSON 优先），并打印 HTML 源全量标题以评估质量"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nhv4.sources import parse_html_items, parse_json_items  # noqa: E402

JSON_CANDIDATES = [
    ("baidu-military", "https://top.baidu.com/api/board?platform=wise&tab=military"),
    ("baidu-game", "https://top.baidu.com/api/board?platform=wise&tab=game"),
    ("baidu-ent", "https://top.baidu.com/api/board?platform=wise&tab=entertainment"),
    ("baidu-teleplay", "https://top.baidu.com/api/board?platform=wise&tab=teleplay"),
    ("baidu-car", "https://top.baidu.com/api/board?platform=wise&tab=car"),
    ("v2ex", "https://www.v2ex.com/api/topics/hot.json"),
    ("ithome-json", "https://api.ithome.com/json/newslist/"),
]

HTML_DUMP = [
    ("eastmoney", "https://finance.eastmoney.com/"),
    ("ifeng", "https://news.ifeng.com/"),
]


def main():
    print("=== JSON 候选 ===")
    for name, url in JSON_CANDIDATES:
        try:
            items = parse_json_items(url, name, 25)
            print("  %-16s %3d 条  样例: %s" % (name, len(items),
                                                 items[0].title[:36] if items else "-"))
        except Exception as e:                              # noqa: BLE001
            print("  %-16s FAIL %s" % (name, str(e)[:56]))

    print("\n=== HTML 全量标题 ===")
    for name, url in HTML_DUMP:
        try:
            items = parse_html_items(url, name, 25)
            print("  [%s] %d 条" % (name, len(items)))
            for it in items[:12]:
                print("      - %s" % it.title[:52])
        except Exception as e:                              # noqa: BLE001
            print("  [%s] FAIL %s" % (name, str(e)[:56]))


if __name__ == "__main__":
    main()
