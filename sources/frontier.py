"""
frontier.py — 大厂前沿 RSS 解析（读本地 rss-feeds XML，近3天，全量保留）
fetch() -> List[Article]
"""
import hashlib
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

from models import Article

FEEDS_DIR = Path("/home/ubuntu/rss-feeds/feeds")
FRONTIER_SOURCES_FILE = Path.home() / ".hermes" / "frontier_sources.yaml"
MAX_AGE_DAYS = 3


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _load_sources() -> list[dict]:
    """从 frontier_sources.yaml 读取源列表"""
    import yaml
    with open(FRONTIER_SOURCES_FILE) as f:
        config = yaml.safe_load(f)
    return config.get("sources", [])


def _parse_date(date_str: str):
    """解析日期字符串，返回 datetime（UTC）。失败返回 None。"""
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str.strip())
    except Exception:
        pass
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def _is_fresh(dt, max_age_hours: int) -> bool:
    if dt is None:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600 < max_age_hours


def _parse_rss(xml_text: str, source_name: str) -> list[dict]:
    """解析 RSS 2.0 feed，返回 [{title, url, date_str, summary}]"""
    items = []
    try:
        root = ET.fromstring(xml_text)
        # RSS 2.0
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            date_str = (item.findtext("pubDate") or
                        item.findtext("{http://purl.org/dc/elements/1.1/}date") or "")
            summary = re.sub(r"<[^>]+>", "", (item.findtext("description") or "")).strip()
            if title and url:
                items.append({"title": title, "url": url,
                               "date_str": date_str, "summary": summary})
    except Exception as e:
        print(f"  [WARN] parse rss failed for {source_name}: {e}", file=sys.stderr)
    return items


def fetch() -> list:
    """读取所有 frontier 源的本地 XML，返回 Article 列表"""
    try:
        sources = _load_sources()
    except Exception as e:
        print(f"[frontier] 读取源配置失败: {e}", file=sys.stderr)
        return []

    max_age_hours = MAX_AGE_DAYS * 24
    articles = []

    for src in sources:
        name = src.get("name", "")
        feed_file_name = src.get("feed_file", "")
        feed_path = FEEDS_DIR / feed_file_name

        if not feed_path.exists():
            print(f"[frontier] {name}: 文件不存在 {feed_path}", file=sys.stderr)
            continue

        try:
            xml_text = feed_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"[frontier] {name}: 读取失败 {e}", file=sys.stderr)
            continue

        raw_items = _parse_rss(xml_text, name)
        count = 0
        for item in raw_items:
            dt = _parse_date(item["date_str"])
            if not _is_fresh(dt, max_age_hours):
                continue
            articles.append(Article(
                id=_make_id(item["url"]),
                title=item["title"],
                url=item["url"],
                source=name,
                block="frontier",
                published=dt or datetime.now(timezone.utc),
                summary=item["summary"],
            ))
            count += 1

        print(f"[frontier] {name}: {count} 条", file=sys.stderr)

    return articles
