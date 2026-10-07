# 新闻热点速览 v4.0.1

一个聚合多平台热榜的桌面应用。v4 不是 v3 的补丁，而是按「内核 / 界面分离」重写的版本。

> 需要 Python 3.8+，且**必须带 Tk 组件**（官方 python.org 安装包自带；
> 部分精简版 / 嵌入式 Python 没有 tkinter，那样图形界面起不来）。

---

## 相比 v3 的变化

| | v3 | v4 |
|---|---|---|
| 代码结构 | 单个 1700 行文件 | 分层包：`core` / `ui` / `sources` / `store` |
| 启动 | 每次空白等待网络 | **秒开**：先渲染本地归档，后台静默刷新 |
| 去重 | 仅标题完全相同 | **跨源事件聚合**，多源报道合并为一条并标注「N 源在报」 |
| 历史 | 不留存 | SQLite 归档，保留 30 天，可回溯任意一天 |
| 检索 | 只过滤当前列表 | **全文检索**（FTS5 trigram 分词，适配中文） |
| 趋势 | 无 | 记录每次刷新名次/热度，标注 新上榜 / 飙升 / 降温 |
| 订阅 | 无 | 关键词订阅，命中高亮并置顶 |
| 主题 | 6 套浅色 | 8 套，含 3 套深色 |
| 数据源可靠性 | 失败就红 | 成功率统计 + 连续失败自动熔断冷却 |
| 附加 | — | 命令行模式、5 种导出、HiDPI 适配 |

---

## 目录结构

```
news_hotspots_v4/
├── news_hotspots_v4.py      入口（GUI / --cli 两种模式）
├── requirements.txt         依赖
├── build.py                 一键打包
├── 新闻热点速览.spec         PyInstaller 配置
├── setup_v4.iss             Inno Setup 安装脚本
├── app.ico
├── samples/                 示例导出结果
├── nhv4/                    程序包
│   ├── config.py            配置与路径（数据放 %APPDATA%/NewsHotspots）
│   ├── models.py            NewsItem / Trend
│   ├── cluster.py           跨源事件聚合（shingle 倒排索引 + 并查集）
│   ├── net.py               网络层（连接池 / 编码嗅探 / 正文提取）
│   ├── store.py             SQLite：归档、热度历史、全文检索、收藏
│   ├── sources.py           数据源注册表 + 内置抓取器 + 模板库
│   ├── fetcher.py           并发抓取引擎（熔断 / 健康度）
│   ├── core.py              业务核心：秒开、趋势、订阅、筛选
│   ├── export.py            导出 HTML / MD / TXT / CSV / JSON
│   ├── theme.py             主题
│   └── ui/                  widgets · cards · reader · dialogs · app
└── tools/                   开发脚本
    ├── probe_sources.py     数据源体检（条数 / 耗时 / 错误）
    ├── probe_health.py      板块条目数 + 阅读器正文提取成功率
    ├── smoke_test.py        内核冒烟测试（22 项断言）
    ├── gui_smoke.py         界面冒烟测试（需 tkinter）
    └── button_test.py      按钮全量点击测试（遍历界面上每个按钮）
```

---

## 运行

```bash
pip install requests pillow

# 图形界面
python news_hotspots_v4.py

# 命令行（无界面，适合定时任务）
python news_hotspots_v4.py --cli --top 20
python news_hotspots_v4.py --cli --board 科技 --export html --out 日报.html
```

## 打包

```bash
python build.py            # 生成 dist/新闻热点速览.exe
python build.py --clean    # 清理后重新打包
```
再用 Inno Setup 编译 `setup_v4.iss` 得到安装程序。

## 自检

```bash
python tools/probe_sources.py   # 体检每个数据源的可用性与耗时
python tools/smoke_test.py      # 内核链路 22 项断言
```

---

## 内置数据源（20 个，均已实测通过）

| 分类 | 数据源 |
|---|---|
| 新闻 | 头条热榜、微博热搜、百度热搜、腾讯新闻、知乎热榜、央视新闻、凤凰网资讯 |
| 科技 | IT之家（RSS）、少数派（RSS）、36氪热榜 |
| 财经 | 百度财经、央视财经、东方财富、人民网财经 |
| 体育 | 新浪NBA、百度体育 |
| 军事 | 人民网军事、中国军网 |
| 视频 | B站热门、观察者网视频 |

抓取逻辑优先级：官方 JSON 接口 > RSS > HTML 链接抽取。

> v3 的「财联社电报」接口已失效（404），v4 移除；抖音热榜在部分网络环境被拦截，也未纳入。
> B站在部分网络环境（企业代理）下不可达，此时视频板块由观察者网视频支撑。
> 数据源一旦失败会如实报出并在健康提示里标红，**不会**用其他分类的数据冒充。

### 内置阅读器的边界

正文提取对服务端渲染的页面有效（IT之家、少数派、凤凰网、东方财富、人民网、中国军网、
观察者网、头条移动端等）。以下几类读不到，会提示改用「浏览器打开」：

- 知乎 —— 站点返回 403
- 36氪、百度搜索页 —— 正文由脚本动态加载，静态 HTML 是空壳
- 部分视频站在受限网络下被代理拦截

头条的桌面版是纯 JS 空壳，程序会自动改走移动端（`m.toutiao.com`）取服务端渲染的正文。

---

## 数据存储

全部用户数据位于 `%APPDATA%\NewsHotspots\`（Linux/macOS 为 `~/NewsHotspots/`）：

- `archive.db` —— 历史归档、热度/名次日志、收藏、订阅
- `settings_v4.json` —— 界面与数据源配置（**与 v3 的 settings.json 分开**，避免继承旧版失效的数据源 id）
- `exports/` —— 默认导出目录
- `logs/app.log` —— 运行日志

## 注意事项

- 数据源为第三方公开接口，随时可能变动；`tools/probe_sources.py` 可随时体检。
- 首次启动没有历史快照，不会显示「新上榜」标记（因为没有可比对的基线），第二次刷新起正常。
- 连续失败 3 次的源会熔断 10 分钟，避免拖慢整体刷新。
