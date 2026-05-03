# Daily News Agent v4.0 设计文档

> 状态：待实施
> 最后更新：2026-05-03
> 确认人：Ellis

---

## 一、目录结构

```
~/.hermes/scripts/
  models.py                  # Article dataclass，统一数据模型
  state.py                   # StateManager，封装 news_state.json
  pipeline.py                # 主流程，组装各模块
  sources/
    __init__.py
    trends.py                # TrendRadar 适配器 + 正则过滤
    frontier.py              # rss-feeds XML 解析（只列标题链接，不抓全文）
    wewerss.py               # WeWeRSS atom 拉取（每源最多5条）
  filters/
    __init__.py
    regex_filter.py          # 热点正则过滤 + 来源权重截取
  renderers/
    __init__.py
    markdown.py              # 生成 MD 文件，唯一知道 MD 格式的模块

  wechat_fetch.py            # Step4：预取综合新闻全文，回填MD
  run_step2.sh               # pipeline.py 重试 wrapper（3次，60s间隔）
  run_step3.sh               # wechat_fetch.py 重试 wrapper（3次，30s间隔）
  token_summary.py           # 汇总 token，写 daily_token_report.json（不变）
  token_report.py            # 读 report，供 token cron 注入（不变）

~/.hermes/articles/
  YYYY-MM-DD/
    {key}.md                 # 综合新闻全文（wechat_fetch 预取）
    frontier/
      {key}.md               # 大厂前沿全文（用户触发精读时按需 Playwright 抓取）

~/.hermes/digests/
  YYYY-MM-DD.md              # 每日聚合 MD

~/.hermes/pipeline_status.json   # 各模块错误/状态（统一）
```

---

## 二、信息源配置文件

### news_sources.yaml（原有，综合新闻部分更新）

综合新闻板块（wewe-rss，每源最多5条，近3天）：
- 36氪:              http://163.192.58.250:4000/feeds/MP_WXS_3264997043.atom
- 机器之心:           http://163.192.58.250:4000/feeds/MP_WXS_3073282833.atom
- 新智元:             http://163.192.58.250:4000/feeds/MP_WXS_3271041950.atom
- 宝玉AI:             http://163.192.58.250:4000/feeds/MP_WXS_3957812448.atom
- 数字生命卡兹克:      http://163.192.58.250:4000/feeds/MP_WXS_3223096120.atom
- 人人都是产品经理:    http://163.192.58.250:4000/feeds/MP_WXS_2399106260.atom
- 孤独大脑:           http://163.192.58.250:4000/feeds/MP_WXS_2398022876.atom

### frontier_sources.yaml（新增）

大厂前沿板块（rss-feeds 生成，近3天，全量保留）：
- anthropic_engineering
- anthropic_news
- anthropic_red
- anthropic_research
- claude
- deepmind_blog
- google_ai
- openai_news

feed 文件路径：/home/ubuntu/rss-feeds/feeds/feed_{name}.xml

---

## 三、Article 数据模型（models.py）

```python
@dataclass
class Article:
    id: str             # md5(url)[:8]
    title: str
    url: str
    source: str         # "36氪" / "Anthropic Engineering" 等
    block: str          # "trend" / "frontier" / "news"
    published: datetime
    summary: str = ""
    full_content_path: str = ""   # 本地路径，不存正文本体
```

---

## 四、模块职责边界

| 模块 | 对外暴露 | 内部隐藏 |
|------|---------|---------|
| state.py | `is_seen(url)` / `mark_seen(url)` / `mark_batch(urls)` | JSON格式、文件路径 |
| trends.py | `fetch() -> List[Article]` | TrendRadar DB路径、字段名 |
| frontier.py | `fetch() -> List[Article]` | XML解析逻辑、frontier_sources.yaml路径 |
| wewerss.py | `fetch() -> List[Article]` | atom格式、WeWeRSS地址、每源5条限制 |
| regex_filter.py | `filter(articles, n=10) -> List[Article]` | 黑名单规则、来源权重 |
| markdown.py | `write(sections, path)` / `read_by_index(path, n) -> Article` | MD格式、全局编号逻辑 |
| pipeline.py | 主入口 `run()` | 模块组装顺序 |

**失败约定（Defensive Coding）**：
- 每个 fetch/filter 函数捕获所有异常，失败返回空列表
- 失败时向 pipeline_status.json 写入自己的 error 字段
- 不向上 raise，主流程继续跑其他模块

---

## 五、热点正则过滤规则（regex_filter.py）

### 第一层：黑名单关键词（直接丢弃）
- 娱乐/明星：选秀、出道、演唱会、恋爱、离婚、出轨、粉丝、爱豆
- 体育：夺冠、世界杯、奥运、赛季、球队、球员
- 低价值：星座、鸡汤、养生

### 第二层：来源权重截取（总计10条）
优先级：知乎热榜 > 微博热搜 > 百度热搜
同一话题跨平台命中，保留权重最高来源的一条（标题相似度去重）。

---

## 六、pipeline_status.json 格式

```json
{
  "date": "2026-05-04",
  "modules": {
    "trends":       {"status": "ok",    "count": 10, "error": null},
    "frontier":     {"status": "error", "count": 0,  "error": "XML parse failed: anthropic_engineering"},
    "wewerss":      {"status": "ok",    "count": 23, "error": null},
    "wechat_fetch": {"status": "ok",    "fetched": 18, "skipped": 5, "error": null}
  },
  "updated_at": "2026-05-04T23:42:01Z"
}
```

Sonnet 日报第一步读此文件，有 error 字段则在日报末尾附上。

---

## 七、MD 文件格式

```markdown
# 2026-05-04 新闻摘要

## 一、热点
### 1. 【知乎】标题
🔗 URL (trend)

### 2. 【微博】标题
🔗 URL (trend)

## 二、大厂前沿
### 11. 【Anthropic Engineering】标题
🔗 URL (frontier)

### 12. 【OpenAI News】标题
🔗 URL (frontier)

## 三、综合新闻
### 19. 【36氪】标题
摘要前200字...
🔗 URL (rss)
📄 a1b2c3d4

## ❌ 模块异常
- frontier: XML parse failed: anthropic_engineering

## ⚠️ 今日无内容
- 孤独大脑
```

编号全局连续，markdown.py 独占写入权。

---

## 八、Cron Schedule（重排后，北京时间 UTC+8）

### 系统 crontab（UTC）

```cron
# Step1: 热点抓取
0  23 * * *  cd /home/ubuntu/TrendRadar && .venv/bin/python -m trendradar >> ~/.hermes/logs/trendradar.log 2>&1

# Step2: 大厂前沿 RSS 拉取（快，不抓全文）
5  23 * * *  cd /home/ubuntu/rss-feeds && uv run feed_generators/run_all_feeds.py >> ~/.hermes/logs/rss-feeds.log 2>&1

# Step3: pipeline.py（热点+大厂前沿+综合新闻 → MD）
20 23 * * *  /bin/bash /home/ubuntu/.hermes/scripts/run_step2.sh

# Step4: wechat_fetch.py（综合新闻全文预取，回填MD）
40 23 * * *  /bin/bash /home/ubuntu/.hermes/scripts/run_step3.sh
```

### Hermes cron（UTC，北京次日早晨）

```
0  0 * * *  e9471bb242bb  日报推送（script: token_summary.py）
10 0 * * *  d62d5de141cc  Token 汇报（只用 file toolset）
```

---

## 九、日报推送消息顺序（防 iLink 限制）

Sonnet cron 内部，消息间 sleep 15s：

```
第0步：read_file pipeline_status.json，有 error 则在对应消息末尾附注
  ↓
消息1：热点（10条简短列表）
  ↓ sleep 15s
消息2：大厂前沿（标题+链接列表，末尾提示"回复 精读 N 可获取全文解读"）
  ↓ sleep 15s
消息3：综合新闻日报 + 每日精选1篇（从综合新闻板块选，读 articles/{key}.md）
  ↓（10分钟后独立 cron）
消息4：Token 消耗汇报
```

---

## 十、按需精读流程（用户触发）

用户发 `精读 3`：

1. 读今日 MD，用 `markdown.read_by_index(path, 3)` 取 Article
2. 判断 block：
   - `frontier` → Playwright 抓全文 → 存 `articles/YYYY-MM-DD/frontier/{key}.md` → 摘要发回
   - `news` → 读已有 `articles/YYYY-MM-DD/{key}.md` → 摘要发回
   - `trend` → web_search 搜标题找权威报道 → 摘要发回
3. 格式：有温度的开场 + 核心内容 + 补充声音/背景 + 原文链接

---

## 十一、待废弃的旧文件（实施时删除或归档）

| 旧文件 | 替代 |
|--------|------|
| `news_fetch.py` | `sources/trends.py` + `sources/frontier.py` + `sources/wewerss.py` |
| `news_filter.py` | `pipeline.py` + `filters/regex_filter.py` |

`wechat_fetch.py` / `run_step2.sh` / `run_step3.sh` / `token_summary.py` / `token_report.py` 保留，按需更新。

---

## 十二、手动重跑命令（更新后）

```bash
TODAY=$(TZ='Asia/Shanghai' date +%Y-%m-%d)

# 清状态（必须同时清 MD 和 state）
rm -f ~/.hermes/news_state.json ~/.hermes/digests/${TODAY}.md ~/.hermes/pipeline_status.json

# Step1: TrendRadar
cd /home/ubuntu/TrendRadar && timeout 120 .venv/bin/python -m trendradar

# Step2: rss-feeds
cd /home/ubuntu/rss-feeds && uv run feed_generators/run_all_feeds.py

# Step3: pipeline
python3 ~/.hermes/scripts/pipeline.py

# Step4: wechat_fetch
python3 ~/.hermes/scripts/wechat_fetch.py

# Step5: 日报推送
hermes cron run e9471bb242bb

# Step6: Token 汇报（10分钟后或手动立即）
hermes cron run d62d5de141cc

# 查看结果
cat ~/.hermes/digests/${TODAY}.md
cat ~/.hermes/pipeline_status.json
```
