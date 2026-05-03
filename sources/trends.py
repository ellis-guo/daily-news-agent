"""
trends.py — TrendRadar 适配器 + 正则过滤
fetch() -> List[Article]
"""
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from models import Article
from filters.regex_filter import filter_trends

CST = timezone(timedelta(hours=8))

DB_DIR = Path.home() / "TrendRadar" / "output" / "news"

# 各平台的中文显示名
PLATFORM_LABELS = {
    "weibo":          "微博",
    "zhihu":          "知乎",
    "baidu":          "百度",
    "toutiao":        "头条",
    "wallstreetcn-hot": "华尔街见闻",
}

PLATFORMS = list(PLATFORM_LABELS.keys())
MAX_ITEMS = 10  # 过滤后目标条数


def _make_id(url: str) -> str:
    import hashlib
    return hashlib.md5(url.encode()).hexdigest()[:8]


def fetch() -> list:
    """从 TrendRadar SQLite 读取今日热点，正则过滤后返回 Article 列表"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    db_path = DB_DIR / f"{today}.db"

    if not db_path.exists():
        print(f"[trends] DB 不存在: {db_path}", file=sys.stderr)
        return []

    raw = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        placeholders = ",".join("?" * len(PLATFORMS))
        rows = cur.execute(
            f"SELECT title, url, platform_id, rank FROM news_items "
            f"WHERE platform_id IN ({placeholders}) "
            f"ORDER BY crawl_count DESC, rank ASC LIMIT {MAX_ITEMS * 5}",
            PLATFORMS
        ).fetchall()
        conn.close()

        seen_titles: set[str] = set()
        for row in rows:
            title = (row["title"] or "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                raw.append({
                    "title": title,
                    "url": row["url"] or "",
                    "platform": row["platform_id"],
                    "rank": row["rank"],
                })
    except Exception as e:
        print(f"[trends] 读取失败: {e}", file=sys.stderr)
        return []

    # 正则过滤 + 来源权重截取
    filtered = filter_trends(raw, n=MAX_ITEMS)

    articles = []
    now = datetime.now(timezone.utc)
    for item in filtered:
        label = PLATFORM_LABELS.get(item["platform"], item["platform"])
        url = item["url"] or f"https://s.weibo.com/weibo?q={item['title']}"
        articles.append(Article(
            id=_make_id(url),
            title=item["title"],
            url=url,
            source=label,
            block="trend",
            published=now,
        ))

    print(f"[trends] {len(raw)} 条原始 -> 过滤后 {len(articles)} 条", file=sys.stderr)
    return articles
