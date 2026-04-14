#!/usr/bin/env python3
"""
新闻自动收集脚本
读取 ~/.hermes/news_sources.yaml，抓取各来源，输出结构化 JSON 供 Hermes 处理
"""

import json
import os
import re
import sqlite3
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERMES_DIR = Path.home() / ".hermes"
SOURCES_FILE = HERMES_DIR / "news_sources.yaml"
STATE_FILE = HERMES_DIR / "news_state.json"  # 记录已推送 ID，去重用

# 北京时间
CST = timezone(timedelta(hours=8))


def load_yaml_simple(path):
    """极简 YAML 解析（只处理本文件格式，避免依赖 pyyaml）"""
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"seen_ids": []}


def save_state(state):
    # 只保留最近 500 条 ID
    state["seen_ids"] = state["seen_ids"][-500:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def is_fresh(pub_date_str, max_age_hours=24):
    """判断文章是否在 max_age_hours 小时内（默认严格 24 小时）"""
    if not pub_date_str:
        return True
    try:
        for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(pub_date_str.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                return age_hours < max_age_hours
            except:
                continue
    except:
        pass
    return True


def fetch_url(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  [WARN] fetch failed: {url}: {e}", file=sys.stderr)
        return None


def parse_rss(xml_text, source_name, max_items=5, max_age_hours=24):
    """解析 RSS/Atom，返回 [{title, url, date, source}]"""
    items = []
    if not xml_text:
        return items
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall(".//atom:entry", ns) or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        if entries:
            for e in entries[:max_items * 2]:
                title = (e.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                link_el = e.find("{http://www.w3.org/2005/Atom}link")
                url = (link_el.get("href") if link_el is not None else "") or ""
                # 用 published 判断时效，updated 可能是编辑更新不代表新文章
                date = e.findtext("{http://www.w3.org/2005/Atom}published") or \
                       e.findtext("{http://www.w3.org/2005/Atom}updated") or ""
                if title and url and is_fresh(date, max_age_hours):
                    items.append({"title": title, "url": url, "date": date[:10], "source": source_name, "source_type": "rss"})
                if len(items) >= max_items:
                    break
        else:
            for item in root.findall(".//item")[:max_items * 2]:
                title = (item.findtext("title") or "").strip()
                url = (item.findtext("link") or "").strip()
                date = item.findtext("pubDate") or item.findtext("dc:date") or ""
                if title and url and is_fresh(date, max_age_hours):
                    items.append({"title": title, "url": url, "date": date[:16], "source": source_name, "source_type": "rss"})
                if len(items) >= max_items:
                    break
    except Exception as e:
        print(f"  [WARN] parse RSS failed for {source_name}: {e}", file=sys.stderr)
    return items


def fetch_trends(config):
    """从 TrendRadar SQLite 读取今日热点"""
    items = []
    db_dir = Path(config.get("db_path", "~/TrendRadar/output/news")).expanduser()
    today = datetime.now(CST).strftime("%Y-%m-%d")
    db_path = db_dir / f"{today}.db"

    if not db_path.exists():
        print(f"  [WARN] TrendRadar DB not found: {db_path}", file=sys.stderr)
        return items

    platforms = config.get("platforms", [])
    max_items = config.get("max_items", 10)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        placeholders = ",".join("?" * len(platforms)) if platforms else ""
        where = f"WHERE platform_id IN ({placeholders})" if platforms else ""
        rows = cur.execute(
            f"SELECT title, url, platform_id, rank FROM news_items {where} "
            f"ORDER BY crawl_count DESC, rank ASC LIMIT {max_items * 3}",
            platforms if platforms else []
        ).fetchall()
        conn.close()

        seen_titles = set()
        for row in rows:
            title = row["title"].strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                items.append({
                    "title": title,
                    "url": row["url"] or "",
                    "source": f"热榜·{row['platform_id']}",
                    "date": today,
                    "source_type": "trend",
                })
            if len(items) >= max_items:
                break
    except Exception as e:
        print(f"  [WARN] TrendRadar read failed: {e}", file=sys.stderr)
    return items


def fetch_caixin():
    """抓财新首页新闻列表"""
    items = []
    env_text = (HERMES_DIR / ".env").read_text() if (HERMES_DIR / ".env").exists() else ""
    m = re.search(r'CAIXIN_COOKIE="([^"]+)"', env_text)
    if not m:
        print("  [WARN] CAIXIN_COOKIE not found", file=sys.stderr)
        return items

    cookie = m.group(1)
    html = fetch_url("https://www.caixin.com", headers={"Cookie": cookie})
    if not html:
        return items

    today = datetime.now(CST).strftime("%Y-%m-%d")
    seen = set()
    for url, title in re.findall(
        r'href="(https://www\.caixin\.com/\d{4}-\d{2}-\d{2}/\d+\.html)"[^>]*>([^<]{8,80})',
        html
    ):
        title = title.strip()
        if title and title not in seen:
            seen.add(title)
            items.append({"title": title, "url": url, "date": today, "source": "财新", "source_type": "caixin"})
        if len(items) >= 8:
            break
    return items


def fetch_jike(url, max_age_hours=24):
    """抓即刻用户动态"""
    import json as json_mod
    items = []
    html = fetch_url(url)
    if not html:
        return items

    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if not m:
        return items

    try:
        data = json_mod.loads(m.group(1))
        posts = data["props"]["pageProps"].get("posts", [])
        for p in posts:
            if p.get("type") != "ORIGINAL_POST":
                continue
            action_time = p.get("actionTime", "")
            if not is_fresh(action_time, max_age_hours):
                continue
            content = p.get("content", "").strip()
            post_id = p.get("id", "")
            post_url = f"https://web.okjike.com/originalPost/{post_id}"
            if content:
                items.append({
                    "title": content[:100],
                    "content": content,  # 完整正文，摘要时直接用
                    "url": post_url,
                    "date": action_time[:10],
                    "source": "hidecloud 即刻",
                    "source_type": "jike",
                })
    except Exception as e:
        print(f"  [WARN] Jike parse failed: {e}", file=sys.stderr)
    return items


def fetch_dario(max_age_days=30):
    """爬 darioamodei.com 文章列表"""
    items = []
    html = fetch_url("https://darioamodei.com")
    if not html:
        return items

    seen = set()
    for href, title in re.findall(r'href="(/essays/[^"]+)"[^>]*>\s*([^<]{10,120})', html):
        title = title.strip()
        if title and title not in seen:
            seen.add(title)
            items.append({
                "title": title,
                "url": f"https://darioamodei.com{href}",
                "date": "",
                "source": "Dario Amodei",
            })
    return items[:5]


def main():
    try:
        config = load_yaml_simple(SOURCES_FILE)
    except Exception as e:
        print(f"ERROR: cannot load {SOURCES_FILE}: {e}", file=sys.stderr)
        sys.exit(1)

    # 全量返回，去重由 news_filter.py 统一处理
    seen_ids = set()
    results = {}

    # 一、热点
    print("Fetching trends...", file=sys.stderr)
    if config.get("trends", {}).get("enabled"):
        items = fetch_trends(config["trends"])
        results["热点"] = items
        print(f"  trends: {len(items)} items", file=sys.stderr)

    # 二、新闻
    news_items = []
    print("Fetching news...", file=sys.stderr)
    for src in config.get("news", []):
        if src.get("type") == "scrape" and src.get("id") == "caixin":
            items = fetch_caixin()
        elif src.get("type") == "rss":
            xml = fetch_url(src["url"])
            items = parse_rss(xml, src["name"], src.get("max_items", 3), src.get("max_age_hours", 24))
        else:
            items = []
        new_items = [i for i in items if i["url"] not in seen_ids]
        news_items.extend(new_items)
        print(f"  {src['name']}: {len(new_items)} new items", file=sys.stderr)
    results["新闻"] = news_items

    # 三、论文
    paper_items = []
    print("Fetching papers...", file=sys.stderr)
    for src in config.get("papers", []):
        xml = fetch_url(src["url"])
        items = parse_rss(xml, src["name"], src.get("max_items", 5), src.get("max_age_hours", 24))
        new_items = [i for i in items if i["url"] not in seen_ids]
        paper_items.extend(new_items)
        print(f"  {src['name']}: {len(new_items)} new items", file=sys.stderr)
    results["论文"] = paper_items

    # 四、Blog（无更新时每个源加占位）
    blog_items = []
    print("Fetching blogs...", file=sys.stderr)
    for src in config.get("blogs", []):
        if src.get("type") == "jike":
            items = fetch_jike(src["url"], src.get("max_age_hours", 24))
        elif src.get("type") == "scrape" and src.get("id") == "dario":
            items = fetch_dario(src.get("max_age_hours", 24 * 30))
        elif src.get("type") == "rss":
            xml = fetch_url(src["url"])
            items = parse_rss(xml, src["name"], src.get("max_items", 10), src.get("max_age_hours", 24))
        else:
            items = []
        new_items = [i for i in items if i["url"] not in seen_ids]
        if new_items:
            blog_items.extend(new_items)
        else:
            # 无更新时加占位条目
            blog_items.append({
                "title": "（今日无更新）",
                "url": "",
                "date": "",
                "source": src["name"],
                "no_update": True,
            })
        print(f"  {src['name']}: {len(new_items)} new items", file=sys.stderr)
    results["Blog"] = blog_items

    # 五、播客（无更新时每个源加占位）
    podcast_items = []
    print("Fetching podcasts...", file=sys.stderr)
    for src in config.get("podcasts", []):
        xml = fetch_url(src["url"])
        items = parse_rss(xml, src["name"], src.get("max_items", 5), src.get("max_age_hours", 24))
        new_items = [i for i in items if i["url"] not in seen_ids]
        if new_items:
            podcast_items.extend(new_items)
        else:
            podcast_items.append({
                "title": "（今日无更新）",
                "url": "",
                "date": "",
                "source": src["name"],
                "no_update": True,
            })
        print(f"  {src['name']}: {len(new_items)} new items", file=sys.stderr)
    results["播客"] = podcast_items

    # 注意：state 更新由 news_filter.py 统一管理，这里不写

    # 输出 JSON 供 Hermes 读取
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import json
    main()
