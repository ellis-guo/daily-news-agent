"""
wechatrss.py — wechat-download-api RSS 拉取（公众号综合新闻）

替换 wewerss.py 时，只需修改 pipeline.py 一行：
  from sources import trends, wechatrss as wewerss, frontier

接口与 wewerss.py 完全兼容：
  fetch() -> (List[Article], List[str])

订阅源无需在 news_sources.yaml 配置，直接从
http://localhost:5000/api/rss/subscriptions 读取。
新增/删除公众号只需在 wechat-download-api 管理界面操作即可。
"""

import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from models import Article

API_BASE = "http://localhost:5000"
MAX_AGE_HOURS = 72


# ─── 工具函数 ──────────────────────────────────────────────


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def _fetch_url(url: str, timeout: int = 10) -> str | None:
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [WARN] fetch failed: {url}: {e}", file=sys.stderr)
        return None


def _get_subscriptions() -> list[dict]:
    """从 wechat-download-api 获取已订阅公众号列表"""
    data = _fetch_url(f"{API_BASE}/api/rss/subscriptions")
    if not data:
        return []
    try:
        result = json.loads(data)
        return result.get("data", [])
    except Exception as e:
        print(f"[wechatrss] 解析订阅列表失败: {e}", file=sys.stderr)
        return []


def _is_fresh(date_str: str, max_age_hours: int) -> bool:
    """判断文章是否在 max_age_hours 时间窗口内（支持 RFC 2822 / ISO 8601）"""
    if not date_str:
        return False
    # RFC 2822（RSS 标准，如 "Mon, 04 May 2026 04:01:53 +0000"）
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(date_str.strip())
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600 < max_age_hours
    except Exception:
        pass
    # ISO 8601 fallback
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 3600 < max_age_hours
        except Exception:
            continue
    print(f"  [WARN] is_fresh: 无法解析日期 '{date_str}'", file=sys.stderr)
    return False


def _extract_summary(desc_html: str) -> str:
    """从 RSS description HTML 中提取首条有意义的纯文本摘要"""
    if not desc_html:
        return ""
    # wechat-download-api 的 description 是 <![CDATA[...]]>，ET 已自动解包
    # 取第一个文本长度 > 10 的 <p> 内容
    p_texts = re.findall(r"<p[^>]*>(.*?)</p>", desc_html, re.DOTALL)
    for p in p_texts:
        clean = re.sub(r"<[^>]+>", "", p).strip()
        if len(clean) > 10:
            return clean[:200]
    # fallback：直接去掉所有标签
    plain = re.sub(r"<[^>]+>", "", desc_html).strip()
    return plain[:200]


def _parse_rss(xml_text: str, source_name: str) -> list[dict]:
    """解析 RSS 2.0 feed，返回 [{title, url, summary, date_str}]"""
    items = []
    try:
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            print(f"  [WARN] no <channel> in feed: {source_name}", file=sys.stderr)
            return items
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            url = (item.findtext("link") or "").strip()
            date_str = (item.findtext("pubDate") or "").strip()
            desc_html = item.findtext("description") or ""
            summary = _extract_summary(desc_html)
            if title and url:
                items.append({
                    "title": title,
                    "url": url,
                    "summary": summary,
                    "date_str": date_str,
                })
    except Exception as e:
        print(f"  [WARN] parse rss failed for {source_name}: {e}", file=sys.stderr)
    return items


# ─── 主入口 ───────────────────────────────────────────────


def fetch() -> tuple[list, list]:
    """
    拉取所有 wechat-download-api 订阅公众号，返回 (Article 列表, 失败源名列表)。
    接口与 wewerss.fetch() 完全兼容。
    """
    subscriptions = _get_subscriptions()
    if not subscriptions:
        print("[wechatrss] 获取订阅列表失败或为空", file=sys.stderr)
        return [], ["__subscriptions_api__"]

    articles: list[Article] = []
    failed_sources: list[str] = []

    for sub in subscriptions:
        fakeid = sub.get("fakeid", "")
        name = sub.get("nickname", fakeid)
        if not fakeid:
            continue

        # API 最多返回 MAX_ARTICLES_PER_FEED=10 条，取全量再做时间过滤
        rss_url = f"{API_BASE}/api/rss/{fakeid}?limit=10"
        xml_text = _fetch_url(rss_url)
        if xml_text is None:
            print(f"[wechatrss] {name}: 获取失败", file=sys.stderr)
            failed_sources.append(name)
            continue

        raw_items = _parse_rss(xml_text, name)
        count = 0
        for item in raw_items:
            if not _is_fresh(item["date_str"], MAX_AGE_HOURS):
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

        print(f"[wechatrss] {name}: {count} 条", file=sys.stderr)

    return articles, failed_sources
