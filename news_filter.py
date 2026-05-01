#!/usr/bin/env python3
"""
新闻三步过滤脚本
Step 1: 抓取原始数据 (news_fetch.py)
Step 2: Haiku 过滤广告/无关内容 (参考 MEMORY.md)
Step 3: Haiku 兴趣打分，各板块取固定条数
输出当日 MD 文件路径
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERMES_DIR = Path.home() / ".hermes"
MEMORY_FILE = HERMES_DIR / "MEMORY.md"
FETCH_SCRIPT = HERMES_DIR / "scripts" / "news_fetch.py"
STATE_FILE = HERMES_DIR / "news_state.json"
DIGESTS_DIR = HERMES_DIR / "digests"

CST = timezone(timedelta(hours=8))

SECTION_LIMITS = {
    "热点": 10,
    "新闻": 8,
    "论文": 5,
    "Blog": 999,
    "播客": 999,
}

SECTION_TITLES = {
    "热点": "一、热点",
    "新闻": "二、新闻",
    "论文": "三、论文",
    "Blog": "四、Blog",
    "播客": "五、播客",
}

def get_api_key():
    """从 .env 读取 ANTHROPIC_TOKEN"""
    env_file = HERMES_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                if line.startswith("ANTHROPIC_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    if token:
                        return token
        except Exception as e:
            print(f"[WARN] .env read failed: {e}", file=sys.stderr)
    return os.environ.get("ANTHROPIC_TOKEN", "") or os.environ.get("ANTHROPIC_API_KEY", "")

def read_memory():
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text()
    return ""

def call_haiku(prompt, max_tokens=2000):
    """调用 claude-haiku-4-5"""
    api_key = get_api_key()
    if not api_key:
        print("[WARN] No API key found, skipping Haiku call", file=sys.stderr)
        return None

    payload = json.dumps({
        "model": "claude-haiku-4-5",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "content-type": "application/json",
        }
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        # 记录 token 用量
        usage = result.get("usage", {})
        if usage:
            import datetime
            log_entry = json.dumps({
                "ts": datetime.datetime.utcnow().isoformat(),
                "model": "claude-haiku-4-5",
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }, ensure_ascii=False)
            token_log = Path.home() / ".hermes" / "token_usage.jsonl"
            with open(token_log, "a") as f:
                f.write(log_entry + "\n")
            print(f"[Token] haiku in={usage.get('input_tokens',0)} out={usage.get('output_tokens',0)}", file=sys.stderr)
        return result["content"][0]["text"]
    except Exception as e:
        print(f"[WARN] Haiku call failed: {e}", file=sys.stderr)
        return None

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {"seen_ids": []}

def save_state(state):
    state["seen_ids"] = state["seen_ids"][-500:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def fetch_raw_data():
    result = subprocess.run(
        [sys.executable, str(FETCH_SCRIPT)],
        capture_output=True, text=True, timeout=180
    )
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return json.loads(result.stdout)

def step1_filter(all_items, memory):
    """Haiku 过滤广告/无关内容，热点板块直接跳过"""
    if not all_items:
        return []

    trend_items = [i for i in all_items if i.get("section") == "热点"]
    other_items = [i for i in all_items if i.get("section") != "热点"]

    if not other_items:
        print(f"[Step 1] 热点直通: {len(trend_items)} 条，无其他内容", file=sys.stderr)
        return trend_items

    titles_text = "\n".join(
        f"{i+1}. [{item['source']}] {item['title'][:80]}"
        for i, item in enumerate(other_items)
    )

    prompt = f"""你是新闻过滤助手。根据用户偏好，从标题列表中选出值得保留的编号。

用户偏好档案：
{memory}

标题列表：
{titles_text}

任务：过滤掉明显不符合用户兴趣的内容（广告/娱乐八卦/体育/无实质内容的官方通稿等），保留其余所有条目。
宁可多留，不要误删。

只输出需要保留的编号，逗号分隔，例如：1,3,5,7
不要任何解释。"""

    result = call_haiku(prompt, max_tokens=500)
    if not result:
        return trend_items + other_items

    kept_indices = set()
    for n in re.findall(r'\d+', result):
        idx = int(n) - 1
        if 0 <= idx < len(other_items):
            kept_indices.add(idx)

    kept_others = [other_items[i] for i in sorted(kept_indices)]
    kept = trend_items + kept_others
    print(f"[Step 1] 热点直通: {len(trend_items)} 条，其他过滤: {len(other_items)} -> {len(kept_others)} 条", file=sys.stderr)
    return kept

def step2_aggregate(items):
    """关键词聚合去重，0 token"""
    def normalize(title):
        return re.sub(r'[^\w]', '', title)[:10]

    seen = set()
    result = []
    for item in items:
        fp = normalize(item["title"])
        if fp not in seen:
            seen.add(fp)
            result.append(item)

    print(f"[Step 2] 聚合: {len(items)} -> {len(result)} 条", file=sys.stderr)
    return result

def step3_score_and_limit(items, memory):
    """Haiku 兴趣打分，各板块取固定条数"""
    by_section = {}
    for item in items:
        s = item["section"]
        by_section.setdefault(s, []).append(item)

    final = {}
    for section, section_items in by_section.items():
        limit = SECTION_LIMITS.get(section, 5)

        if limit >= 999 or len(section_items) <= limit:
            final[section] = section_items
            continue

        titles_text = "\n".join(
            f"{i+1}. {item['title'][:80]}"
            for i, item in enumerate(section_items)
        )

        interest_rules = ""
        in_section = False
        for line in memory.split("\n"):
            if "感兴趣的主题" in line:
                in_section = True
            elif line.startswith("## ") and in_section:
                in_section = False
            if in_section:
                interest_rules += line + "\n"

        prompt = f"""根据以下兴趣偏好，从{section}板块标题中选出最值得推荐的 {limit} 条。

兴趣偏好：
{interest_rules}

标题列表：
{titles_text}

输出最值得推荐的 {limit} 个编号，按重要性排列，逗号分隔。只输出数字。"""

        result = call_haiku(prompt, max_tokens=200)
        if not result:
            final[section] = section_items[:limit]
            continue

        selected = []
        for n in re.findall(r'\d+', result):
            idx = int(n) - 1
            if 0 <= idx < len(section_items) and idx not in selected:
                selected.append(idx)
            if len(selected) >= limit:
                break

        for i in range(len(section_items)):
            if i not in selected:
                selected.append(i)
            if len(selected) >= limit:
                break

        final[section] = [section_items[i] for i in selected[:limit]]
        print(f"[Step 3] {section}: {len(section_items)} -> {len(final[section])} 条", file=sys.stderr)

    return final

def write_md(final, today, source_status=None):
    """将过滤结果写入 MD 文件，返回路径"""
    DIGESTS_DIR.mkdir(exist_ok=True)
    md_path = DIGESTS_DIR / f"{today}.md"

    lines = [f"# {today} 新闻摘要\n"]
    n = 1
    for section in ["热点", "新闻", "论文", "Blog", "播客"]:
        items = final.get(section, [])
        if not items:
            continue
        lines.append(f"## {SECTION_TITLES[section]}\n")
        for item in items:
            title = item.get("title", "")
            source = item.get("source", "")
            summary = item.get("summary") or item.get("content", "")
            url = item.get("url", "")
            source_type = item.get("source_type", "rss")

            lines.append(f"### {n}. 【{source}】{title}")
            if summary and not item.get("no_update"):
                lines.append(summary[:300])
            if url:
                lines.append(f"🔗 {url} ({source_type})")
            if item.get("article_key"):
                lines.append(f"📄 {item['article_key']}")
            lines.append("")
            n += 1

    # 源状态汇报
    if source_status:
        empty_sources = [name for name, count in source_status.items() if count == 0]
        if empty_sources:
            lines.append("## ⚠️ 今日无内容的源\n")
            for name in empty_sources:
                lines.append(f"- {name}")
            lines.append("")

    md_content = "\n".join(lines)
    md_path.write_text(md_content, encoding="utf-8")
    return md_path

def write_index_json(final):
    """保留 news_last_digest.json 供兼容"""
    index_map = {}
    n = 1
    for section in ["热点", "新闻", "论文", "Blog", "播客"]:
        for item in final.get(section, []):
            index_map[str(n)] = {
                "title": item["title"],
                "url": item.get("url", ""),
                "source": item["source"],
                "section": section,
                "source_type": item.get("source_type", "rss"),
                "content": item.get("content", ""),
            }
            n += 1
    (HERMES_DIR / "news_last_digest.json").write_text(
        json.dumps(index_map, ensure_ascii=False, indent=2)
    )

def main():
    today = datetime.now(CST).strftime("%Y-%m-%d")
    memory = read_memory()

    print("[Fetch] 抓取原始数据...", file=sys.stderr)
    try:
        raw_data = fetch_raw_data()
    except Exception as e:
        print(f"[ERROR] fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    source_status = raw_data.pop("_source_status", {})

    total_raw = sum(len(v) for v in raw_data.values())
    print(f"[Fetch] 原始: {total_raw} 条", file=sys.stderr)

    if total_raw == 0:
        print("[WARN] 今日暂无新内容", file=sys.stderr)
        return

    # 去重
    state = load_state()
    seen_ids = set(state["seen_ids"])

    all_items = []
    for section, items in raw_data.items():
        for item in items:
            if item.get("url") not in seen_ids:
                all_items.append({**item, "section": section})

    print(f"[Dedup] 去重后: {len(all_items)} 条", file=sys.stderr)

    # Step 1: Haiku 过滤
    filtered = step1_filter(all_items, memory)

    # Step 2: 聚合
    aggregated = step2_aggregate(filtered)

    # 重新按板块分组
    by_section = {}
    for item in aggregated:
        s = item.pop("section")
        by_section.setdefault(s, []).append(item)

    # Step 3: 打分截取
    scored_items = [{**item, "section": s}
                    for s, items in by_section.items() for item in items]
    final = step3_score_and_limit(scored_items, memory)

    # 更新 state
    hot_news_urls = [
        i["url"] for s in ["热点", "新闻", "论文"] for i in raw_data.get(s, []) if i.get("url")
    ]
    shown_urls = [
        item["url"] for s in ["Blog", "播客"] for item in final.get(s, []) if item.get("url")
    ]
    state["seen_ids"] = list(seen_ids | set(hot_news_urls) | set(shown_urls))
    save_state(state)

    # 写 MD 文件（附源状态）
    md_path = write_md(final, today, source_status)

    # 写兼容 JSON
    write_index_json(final)

    total_final = sum(len(v) for v in final.values())
    print(f"[Done] 最终输出: {total_final} 条，MD 已写入: {md_path}", file=sys.stderr)
    print(str(md_path))

if __name__ == "__main__":
    main()
