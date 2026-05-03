#!/usr/bin/env python3
"""
pipeline.py — 主流程，组装各模块
替代原 news_fetch.py + news_filter.py
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 把 scripts 目录加到 sys.path，让子模块可以 import
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

from state import StateManager
from renderers.markdown import write as write_md
from sources import trends, wewerss, frontier

CST = timezone(timedelta(hours=8))
HERMES_DIR = Path.home() / ".hermes"
DIGESTS_DIR = HERMES_DIR / "digests"
STATUS_FILE = HERMES_DIR / "pipeline_status.json"


def _write_status(modules: dict):
    today = datetime.now(CST).strftime("%Y-%m-%d")
    status = {
        "date": today,
        "modules": modules,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2))
    return status


def run():
    today = datetime.now(CST).strftime("%Y-%m-%d")
    md_path = DIGESTS_DIR / f"{today}.md"

    state = StateManager()
    modules = {}

    # ── 1. 热点 ──────────────────────────────────────────
    print("[pipeline] Step1: 抓取热点...", file=sys.stderr)
    try:
        trend_articles = trends.fetch()
        # 热点不做 state 去重（每天重新拉，排行榜性质）
        modules["trends"] = {"status": "ok", "count": len(trend_articles), "error": None}
    except Exception as e:
        print(f"[pipeline] trends 异常: {e}", file=sys.stderr)
        trend_articles = []
        modules["trends"] = {"status": "error", "count": 0, "error": str(e)}

    # ── 2. 大厂前沿 ───────────────────────────────────────
    print("[pipeline] Step2: 抓取大厂前沿...", file=sys.stderr)
    try:
        frontier_articles_raw = frontier.fetch()
        frontier_articles = [a for a in frontier_articles_raw if not state.is_seen(a.url)]
        modules["frontier"] = {"status": "ok", "count": len(frontier_articles), "error": None}
    except Exception as e:
        print(f"[pipeline] frontier 异常: {e}", file=sys.stderr)
        frontier_articles = []
        modules["frontier"] = {"status": "error", "count": 0, "error": str(e)}

    # ── 3. 综合新闻 ───────────────────────────────────────
    print("[pipeline] Step3: 抓取综合新闻...", file=sys.stderr)
    try:
        news_articles_raw, wewerss_failed = wewerss.fetch()
        news_articles = [a for a in news_articles_raw if not state.is_seen(a.url)]
        error_msg = f"以下源获取失败: {', '.join(wewerss_failed)}" if wewerss_failed else None
        modules["wewerss"] = {"status": "ok" if not wewerss_failed else "partial",
                              "count": len(news_articles), "error": error_msg}
    except Exception as e:
        print(f"[pipeline] wewerss 异常: {e}", file=sys.stderr)
        news_articles = []
        modules["wewerss"] = {"status": "error", "count": 0, "error": str(e)}

    total = len(trend_articles) + len(frontier_articles) + len(news_articles)
    print(f"[pipeline] 合计: 热点 {len(trend_articles)} + 前沿 {len(frontier_articles)} + 新闻 {len(news_articles)} = {total} 条", file=sys.stderr)

    if total == 0:
        print("[pipeline] 今日暂无内容，写空 MD", file=sys.stderr)

    # ── 4. 更新 state（frontier + news 去重，热点不记）────
    state.mark_batch([a.url for a in frontier_articles if a.url])
    state.mark_batch([a.url for a in news_articles if a.url])
    state.save()

    # ── 5. 写 MD ─────────────────────────────────────────
    sections = {
        "trend":    trend_articles,
        "frontier": frontier_articles,
        "news":     news_articles,
    }
    status = _write_status(modules)
    write_md(sections, md_path, status)

    print(f"[pipeline] MD 已写入: {md_path}", file=sys.stderr)
    print(str(md_path))


if __name__ == "__main__":
    run()
