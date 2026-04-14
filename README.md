# 每日新闻 Agent README

## 这是什么

每天早上 8 点（温哥华时间）自动推送新闻到微信。
包含热点、财新、公众号、论文、Blog、播客五个板块。
回复编号可获取详细摘要。

---

## 日常使用

**正常情况什么都不用做，每天 8 点自动推送。**

收到推送后：
- 回复数字编号获取摘要，例如：`3 7 12`
- 一次最多 5 条

---

## 文件在哪

```
~/.hermes/
├── news_sources.yaml        ← 信息源（增删源改这里）
├── news_digest_prompt.txt   ← 推送格式模板
├── MEMORY.md                ← 兴趣偏好（影响过滤）
├── SOUL.md                  ← 微信 bot 行为指令
├── news_state.json          ← 去重记录（自动维护）
├── news_last_digest.json    ← 最新一期编号映射
└── scripts/
    ├── news_fetch.py        ← 抓取
    └── news_filter.py       ← 过滤（主入口）

~/TrendRadar/                ← 热点抓取服务
~/wewerss/                   ← 公众号 RSS 服务
```

---

## 常用操作

**手动触发推送（测试用）：**
```bash
rm ~/.hermes/news_state.json   # 清去重，否则没有新内容
hermes cron run e9471bb242bb
```

**只看抓取结果不推送：**
```bash
python3 ~/.hermes/scripts/news_filter.py 2>&1 | head -20
```

**修改兴趣偏好：**
编辑 `~/.hermes/MEMORY.md`，改完立即生效，无需重启。

**增加信息源：**
1. 编辑 `~/.hermes/news_sources.yaml`
2. `rm ~/.hermes/news_state.json`
3. 跑一次测试确认能抓到

**添加公众号：**
1. 打开 `http://192.9.158.168:4000`（授权码 `wewe2026`）
2. 粘贴公众号任意一篇文章链接添加
3. 复制 RSS 地址填入 `news_sources.yaml`

---

## 排障

**热点为空：**
```bash
ls ~/TrendRadar/output/news/   # 看今日 DB 是否存在
# 没有 → 手动跑
cd ~/TrendRadar && timeout 120 .venv/bin/python -m trendradar
```

**财新没内容（Cookie 过期）：**
浏览器登录 caixin.com → F12 → Console → 输入 `document.cookie` → 复制 → 更新 `~/.hermes/.env` 的 `CAIXIN_COOKIE`

**推送没到微信：**
```bash
hermes gateway status
hermes gateway start   # 如果停了
```

**WeWe RSS 挂了：**
```bash
cd ~/wewerss && sudo docker compose restart
```

---

## 凭证速查

| 凭证 | 位置 | 有效期 |
|------|------|--------|
| 财新 Cookie | `~/.hermes/.env` CAIXIN_COOKIE | 数周～数月 |
| 财新账号 | `~/.hermes/.env` CAIXIN_USER/PASS | 长期 |
| WeWe RSS | `~/wewerss/docker-compose.yml` auth code: wewe2026 | 长期 |
| Anthropic token | `~/.hermes/auth.json` | 自动刷新 |
| Oracle 公网 IP | 192.9.158.168 | 长期 |

---

## 定时任务

| 任务 | 时间 | 说明 |
|------|------|------|
| TrendRadar 抓取 | 每天 7:00am 温哥华 | 系统 crontab |
| 新闻推送 | 每天 8:00am 温哥华 | Hermes cron e9471bb242bb |

BC 省已永久 UTC-7，无夏令时，无需季节性调整。
