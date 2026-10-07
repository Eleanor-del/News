# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 全局配置与路径管理

所有用户数据（设置、数据库、日志、导出文件）统一存放在用户目录下的
NewsHotspots 文件夹，避免与程序安装目录耦合，也便于升级时保留数据。
"""

import json
import os
import sys
import threading

APP_NAME = "新闻热点速览"
VERSION = "4.0.1"
APP_ID = "NewsHotspots"

# ---------------------------------------------------------------- 网络
TIMEOUT = 9                 # 单源请求超时（秒）
RETRY = 1                   # 失败重试次数（不含首发）
MAX_PER_SOURCE = 30         # 单源最多取条数
MAX_TOTAL = 900             # 单次刷新总上限
CIRCUIT_FAILS = 3           # 连续失败 N 次后熔断
CIRCUIT_COOLDOWN = 600.0    # 熔断冷却时间（秒）

# ---------------------------------------------------------------- 刷新
DEFAULT_REFRESH = 300       # 默认自动刷新间隔（秒）
REFRESH_OPTIONS = [
    ("关闭", 0),
    ("1 分钟", 60),
    ("5 分钟", 300),
    ("15 分钟", 900),
    ("30 分钟", 1800),
    ("1 小时", 3600),
]

# ---------------------------------------------------------------- 聚合与趋势
CLUSTER_THRESHOLD = 0.52    # 标题相似度阈值（Jaccard，含子串奖励）
SHINGLE_N = 2               # 中文二元切分长度
RANK_SURGE = 5              # 名次上升 ≥ N 视为「飙升」
RANK_DROP = 5               # 名次下降 ≥ N 视为「降温」
HEAT_SURGE_RATIO = 1.8      # 热度放大倍数视为「爆」
HISTORY_DAYS = 30           # 历史归档保留天数

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "*/*",
}


# ---------------------------------------------------------------- 路径

def _user_base():
    if os.name == "nt":
        return os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.expanduser("~")


def _fallback_dir():
    """打包后 exe 所在目录 / 源码所在目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(os.path.dirname(__file__)))


def data_dir():
    """用户数据根目录，优先 %APPDATA%/NewsHotspots"""
    d = os.path.join(_user_base(), APP_ID)
    try:
        os.makedirs(d, exist_ok=True)
        return d
    except OSError:
        pass
    d = os.path.join(_fallback_dir(), "data")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


def settings_path():
    # 与 v3 的 settings.json 分开存放：v3 记录的 disabled / removed 用的是旧版数据源
    # id（如 baidu_realtime），直接继承会让 v4 莫名其妙少掉几个源。
    return os.path.join(data_dir(), "settings_v4.json")


def db_path():
    return os.path.join(data_dir(), "archive.db")


def log_path():
    d = os.path.join(data_dir(), "logs")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = data_dir()
    return os.path.join(d, "app.log")


def export_dir():
    d = os.path.join(data_dir(), "exports")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        d = data_dir()
    return d


# ---------------------------------------------------------------- 设置持久化

DEFAULT_SETTINGS = {
    "theme": "清爽蓝",
    "layout": "single",        # single | double
    "auto_refresh": DEFAULT_REFRESH,
    "sort": "rank",            # rank | heat | time | sources
    "board": "全部",
    "density": "comfortable",  # comfortable | compact
    "disabled": [],            # 被停用的数据源 id
    "removed": [],             # 被删除的内置数据源 id
    "custom": [],              # 自定义数据源定义
    "subscriptions": [],       # 关注关键词
    "pin_subscription": True,  # 命中订阅词是否置顶
    "start_minimized": False,
    "window": {"w": 1240, "h": 800},
}

_lock = threading.Lock()


def load_settings():
    st = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            st.update(saved)
    except Exception:
        pass
    return st


def save_settings(st):
    with _lock:
        try:
            tmp = settings_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False, indent=2)
            os.replace(tmp, settings_path())
        except OSError:
            pass


# ---------------------------------------------------------------- 日志

def log(msg):
    try:
        import datetime
        line = "[%s] %s\n" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
