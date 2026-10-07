# -*- coding: utf-8 -*-
"""
新闻热点速览 v4 · 主题

v3 只有浅色，v4 补齐深色。每个主题统一 16 个语义色槽：
bg 窗口底 / panel 侧栏底 / card 卡片底 / card2 卡片次级底
fg 主文字 / sub 次文字 / weak 弱文字
accent 主强调 / accent2 辅强调 / onaccent 强调底之上的文字
input 输入底 / select 选中底 / hover 悬停 / border 边框
danger 危险 / ok 成功 / warn 警告
tag 标签底 / tagfg 标签字
"""

THEMES = {
    # ---------------------------------------------------------- 浅色
    "清爽蓝": dict(
        dark=False, bg="#eef1f5", panel="#f8fafc", card="#ffffff", card2="#f7f9fc",
        fg="#1f2937", sub="#64748b", weak="#94a3b8",
        accent="#3b82f6", accent2="#22d3ee", onaccent="#ffffff",
        input="#ffffff", select="#dbeafe", hover="#f1f5f9", border="#e2e8f0",
        danger="#ef4444", ok="#10b981", warn="#f59e0b",
        tag="#eff6ff", tagfg="#2563eb"),
    "薄荷绿": dict(
        dark=False, bg="#eef4f0", panel="#f7faf8", card="#ffffff", card2="#f6faf7",
        fg="#1f2937", sub="#64748b", weak="#94a3b8",
        accent="#10b981", accent2="#34d399", onaccent="#ffffff",
        input="#ffffff", select="#d1fae5", hover="#f1f7f3", border="#e2e8f0",
        danger="#ef4444", ok="#10b981", warn="#f59e0b",
        tag="#ecfdf5", tagfg="#059669"),
    "薰衣草": dict(
        dark=False, bg="#f1eef6", panel="#f9f8fb", card="#ffffff", card2="#f8f6fa",
        fg="#1f2937", sub="#64748b", weak="#94a3b8",
        accent="#8b5cf6", accent2="#c084fc", onaccent="#ffffff",
        input="#ffffff", select="#ede9fe", hover="#f5f3f8", border="#e5e0ee",
        danger="#ef4444", ok="#10b981", warn="#f59e0b",
        tag="#f5e8ff", tagfg="#7c3aed"),
    "暖阳橙": dict(
        dark=False, bg="#f5f2ee", panel="#fbf9f7", card="#ffffff", card2="#faf7f4",
        fg="#1f2937", sub="#6b7280", weak="#9ca3af",
        accent="#f59e0b", accent2="#fb923c", onaccent="#ffffff",
        input="#ffffff", select="#fef3c7", hover="#f6f3ef", border="#e8e3db",
        danger="#ef4444", ok="#10b981", warn="#f59e0b",
        tag="#fffbeb", tagfg="#b45309"),
    "石墨灰": dict(
        dark=False, bg="#eceff3", panel="#f5f7fa", card="#ffffff", card2="#f6f8fa",
        fg="#1f2937", sub="#64748b", weak="#94a3b8",
        accent="#64748b", accent2="#94a3b8", onaccent="#ffffff",
        input="#ffffff", select="#e2e8f0", hover="#f1f5f9", border="#dbe1e8",
        danger="#ef4444", ok="#10b981", warn="#f59e0b",
        tag="#f1f5f9", tagfg="#475569"),
    # ---------------------------------------------------------- 深色
    "午夜蓝": dict(
        dark=True, bg="#0f1520", panel="#141c2b", card="#1a2332", card2="#151d2b",
        fg="#e6edf6", sub="#8fa3bd", weak="#64748b",
        accent="#4f9cf9", accent2="#22d3ee", onaccent="#ffffff",
        input="#111a26", select="#1e3a5f", hover="#1f2937", border="#263347",
        danger="#f87171", ok="#34d399", warn="#fbbf24",
        tag="#1c2b42", tagfg="#7cb7f7"),
    "暗夜紫": dict(
        dark=True, bg="#13111c", panel="#191624", card="#201c2e", card2="#1b1827",
        fg="#eae6f5", sub="#a094b8", weak="#6f6685",
        accent="#a78bfa", accent2="#e879f9", onaccent="#ffffff",
        input="#17141f", select="#332a4d", hover="#251f36", border="#2c2740",
        danger="#fb7185", ok="#34d399", warn="#fbbf24",
        tag="#2a2340", tagfg="#c4b5fd"),
    "极夜黑": dict(
        dark=True, bg="#0b0c0e", panel="#121316", card="#17181c", card2="#131418",
        fg="#e8eaed", sub="#9aa0a6", weak="#6b7075",
        accent="#60a5fa", accent2="#38bdf8", onaccent="#0b0c0e",
        input="#0e0f12", select="#1c2733", hover="#1d1f24", border="#24262b",
        danger="#f87171", ok="#34d399", warn="#fbbf24",
        tag="#1b1e24", tagfg="#93c5fd"),
}

THEME_NAMES = list(THEMES.keys())

# 趋势徽章配色（按语义走主题槽）
TREND_COLORS = {
    "new":   "accent",
    "surge": "danger",
    "up":    "warn",
    "down":  "sub",
    "drop":  "sub",
    "flat":  "weak",
}


def get(name):
    return THEMES.get(name) or THEMES["清爽蓝"]


def resolve_fonts(root):
    """按运行环境回退可用字体，返回 (正文字体, 等宽字体)"""
    import os
    import tkinter.font as tkfont
    if os.name == "nt":
        default_family, fixed = "Microsoft YaHei UI", "Consolas"
    else:
        default_family, fixed = "Noto Sans CJK SC", "DejaVu Sans Mono"
    try:
        avail = set(tkfont.families(root))
    except Exception:                                       # noqa: BLE001
        return default_family, fixed
    if os.name == "nt":
        if "Microsoft YaHei UI" in avail:
            return "Microsoft YaHei UI", "Consolas"
        if "Microsoft YaHei" in avail:
            return "Microsoft YaHei", "Consolas"
        return default_family, fixed
    for cand in ("Noto Sans CJK SC", "WenQuanYi Zen Hei", "PingFang SC",
                 "Droid Sans Fallback", "Noto Sans", "Helvetica"):
        if cand in avail:
            default_family = cand
            break
    fixed = "Courier" if "Courier" in avail else default_family
    return default_family, fixed
