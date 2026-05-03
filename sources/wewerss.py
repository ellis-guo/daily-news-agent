"""
wewerss.py — WeWeRSS Atom 拉取（公众号综合新闻）
fetch() -> List[Article]
"""
import hashlib
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

from models import Article

CST = timezone(timedelta(hours=8))
SOURCES_FILE = Path.home() / ".hermes" / "news_sources.yaml"

MAX_ITEMS_PER_SOURCE = 5
MAX_AGE_HOURS = 72


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _load_sources() -> list[dict]:
    """从 news_sources.yaml 读取 wewerss 源列表"""
    import yaml
    with open(SOURCES_FILE) as f:
        config = yaml.safe_load(f)
    return config.get("wewerss", [])


def _fetch_url(url: str, timeout: int = 15, retries: int = 2):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
    for attempt in range(retries + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            if attempt < retries:
                time.sleep(3)
                print(f"  [WARN] retry {attempt+1}/{retries}: {url}", file=sys.stderr)
            else:
                print(f"  [WARN] fetch failed: {url}: {e}", file=sys.stderr)
    return None


def _is_fresh(date_str: str, max_age_hours: int) -> bool:
    if not date_str:
        return False
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str.strip())
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600 < max_age_hours
    except Exception:
        pass
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 3600 < max_age_hours
        except Exception:
            continue
    print(f"  [WARN] is_fresh: 无法解析日期 '{date_str}'", file=sys.stderr)
    return False


def _parse_atom(xml_text: str, source_name: str) -> list[dict]:
    """解析 Atom feed，返回 [{title, url, summary, date_str}]"""
    items = []
    try:
        root = ET.fromstring(xml_text)
        ns = "http://www.w3.org/2005/Atom"
        entries = root.findall(f"{{{ns}}}entry")
        for e in entries:
            title = (e.findtext(f"{{{ns}}}title") or "").strip()
            link_el = e.find(f"{{{ns}}}link")
            url = (link_el.get("href") if link_el is not None else "") or ""
            date_str = (e.findtext(f"{{{ns}}}published") or
                        e.findtext(f"{{{ns}}}updated") or "")
            summary = (e.findtext(f"{{{ns}}}summary") or "").strip()
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            if title and url:
                items.append({"title": title, "url": url,
                               "summary": summary, "date_str": date_str})
    except Exception as e:
        print(f"  [WARN] parse atom failed for {source_name}: {e}", file=sys.stderr)
    return items


def fetch() -> list:
    """拉取所有 wewerss 公众号源，返回 Article 列表"""
    try:
        sources = _load_sources()
    except Exception as e:
        print(f"[wewerss] 读取源配置失败: {e}", file=sys.stderr)
        return []

    articles = []
    for src in sources:
        name = src.get("name", "")
        url = src.get("url", "")
        max_age = src.get("max_age_hours", MAX_AGE_HOURS)

        xml = _fetch_url(url)
        if xml is None:
            print(f"[wewerss] {name}: 获取失败", file=sys.stderr)
            continue

        raw_items = _parse_atom(xml, name)
        count = 0
        for item in raw_items:
            if count >= MAX_ITEMS_PER_SOURCE:
                break
            if not _is_fresh(item["date_str"], max_age):
                continue
            articles.append(Article(
                id=_make_id(item["url"]),
                title=item["title"],
                url=item["url"],
                source=name,
                block="news",
                published=datetime.now(timezone.utc),
                summary=item["summary"],
            ))
            count += 1

        print(f"[wewerss] {name}: {count} 条", file=sys.stderr)
        # WeWeRSS 限流保护
        time.sleep(5)

    return articles
