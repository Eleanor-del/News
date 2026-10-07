# -*- coding: utf-8 -*-
"""候选源探测：测试待补数据源的可用性"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nhv4.sources import (parse_html_items, parse_json_items,  # noqa: E402
                          parse_rss_items)

CANDIDATES = [
    ("cls-nodeapi", "json", "https://www.cls.cn/nodeapi/telegraphList?app=CailianpressWeb&os=web&sv=8.4.6&rn=30"),
    ("cls-v3", "json", "https://www.cls.cn/v3/depth/home/assembled/1000"),
    ("douyin", "json", "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/"),
    ("sina-rss", "rss", "http://rss.sina.com.cn/news/marquee/ddt.xml"),
    ("xinhua-rss", "rss", "http://www.xinhuanet.com/politics/news_politics.xml"),
    ("huxiu-rss", "rss", "https://www.huxiu.com/rss/0.xml"),
    ("people-rss", "rss", "http://www.people.com.cn/rss/politics.xml"),
    ("zaobao-rss", "rss", "https://plink.anyfeeder.com/zaobao/realtime"),
    ("netease-html", "html", "https://news.163.com/"),
    ("thepaper-html", "html", "https://www.thepaper.cn/"),
    ("hupu-html", "html", "https://bbs.hupu.com/"),
    ("eastmoney-html", "html", "https://finance.eastmoney.com/"),
    ("gamersky-html", "html", "https://www.gamersky.com/"),
    ("dongqiudi-html", "html", "https://www.dongqiudi.com/"),
    ("ifeng-html", "html", "https://news.ifeng.com/"),
]


def main():
    print("%-16s %-6s %6s  %s" % ("候选", "模式", "条数", "样例 / 错误"))
    print("-" * 96)
    for name, mode, url in CANDIDATES:
        try:
            if mode == "json":
                items = parse_json_items(url, name, 25)
            elif mode == "rss":
                items = parse_rss_items(url, name, 25)
            else:
                items = parse_html_items(url, name, 25)
            sample = items[0].title[:44] if items else "(空)"
            print("%-16s %-6s %6d  %s" % (name, mode, len(items), sample))
        except Exception as e:                              # noqa: BLE001
            print("%-16s %-6s %6s  FAIL %s" % (name, mode, "-", str(e)[:60]))


if __name__ == "__main__":
    main()
