#!/usr/bin/env python3
"""
新闻三步过滤脚本
Step 1: 抓取原始数据 (news_fetch.py)
Step 2: Haiku 过滤广告/无关内容 (参考 MEMORY.md)
Step 3: Haiku 兴趣打分，各板块取固定条数
输出最终 JSON 供 cron job prompt 格式化
"""

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

HERMES_DIR = Path.home() / ".hermes"
MEMORY_FILE = HERMES_DIR / "MEMORY.md"
FETCH_SCRIPT = HERMES_DIR / "scripts" / "news_fetch.py"
STATE_FILE = HERMES_DIR / "news_state.json"

SECTION_LIMITS = {
    "热点": 10,
    "新闻": 8,
    "论文": 5,
    "Blog": 999,
    "播客": 999,
}

def get_api_key():
    """从 auth.json 读取 OAuth token（用作 x-api-key）"""
    auth_file = HERMES_DIR / "auth.json"
    if auth_file.exists():
        try:
            auth = json.loads(auth_file.read_text())
            entries = auth.get("credential_pool", {}).get("anthropic", [])
            if entries:
                token = entries[0].get("access_token", "")
                if token and token != "***":
                    return token
        except Exception as e:
            print(f"[WARN] auth.json read failed: {e}", file=sys.stderr)
    # fallback: env var
    return os.environ.get("ANTHROPIC_API_KEY", "")

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
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
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
        capture_output=True, text=True, timeout=120
    )
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return json.loads(result.stdout)

def step1_filter(all_items, memory):
    """Haiku 过滤广告/无关内容，热点板块直接跳过"""
    if not all_items:
        return []

    # 热点单独处理，不经过 Haiku 过滤
    trend_items = [i for i in all_items if i.get("section") == "热点"]
    other_items = [i for i in all_items if i.get("section") != "热点"]

    if not other_items:
        print(f"[Step 1] 热点直通: {len(trend_items)} 条，无其他内容", file=sys.stderr)
        return trend_items

    titles_text = "\n".join(
        f"{i+1}. [{item['source']}] {item['title'][:80]}"
        for i, item in enumerate(other_items)
    )

    filter_rules = ""
    in_section = False
    for line in memory.split("\n"):
        if "不感兴趣" in line or "过滤掉" in line:
            in_section = True
        elif line.startswith("## ") and in_section:
            in_section = False
        if in_section:
            filter_rules += line + "\n"

    prompt = f"""根据以下规则，从标题列表中选出需要【保留】的编号。

过滤规则：
{filter_rules}

标题列表：
{titles_text}

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

        # 补足不够的
        for i in range(len(section_items)):
            if i not in selected:
                selected.append(i)
            if len(selected) >= limit:
                break

        final[section] = [section_items[i] for i in selected[:limit]]
        print(f"[Step 3] {section}: {len(section_items)} -> {len(final[section])} 条", file=sys.stderr)

    return final

def main():
    memory = read_memory()

    print("[Fetch] 抓取原始数据...", file=sys.stderr)
    try:
        raw_data = fetch_raw_data()
    except Exception as e:
        print(f"[ERROR] fetch failed: {e}", file=sys.stderr)
        sys.exit(1)

    total_raw = sum(len(v) for v in raw_data.values())
    print(f"[Fetch] 原始: {total_raw} 条", file=sys.stderr)

    if total_raw == 0:
        print(json.dumps({"message": "今日暂无新内容"}, ensure_ascii=False))
        return

    # 去重
    state = load_state()
    seen_ids = set(state["seen_ids"])

    # 扁平化，带板块标签
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
    all_urls = [i["url"] for items in raw_data.values() for i in items if i.get("url")]
    state["seen_ids"] = list(seen_ids | set(all_urls))
    save_state(state)

    # 保存编号映射
    index_map = {}
    n = 1
    for section in ["热点", "新闻", "论文", "Blog", "播客"]:
        for item in final.get(section, []):
            index_map[str(n)] = {
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "section": section,
                "source_type": item.get("source_type", "rss"),
                "content": item.get("content", ""),  # 即刻完整正文
            }
            n += 1
    (HERMES_DIR / "news_last_digest.json").write_text(
        json.dumps(index_map, ensure_ascii=False, indent=2)
    )

    # 按板块顺序输出
    ordered = {s: final[s] for s in ["热点", "新闻", "论文", "Blog", "播客"]
               if final.get(s)}

    total_final = sum(len(v) for v in ordered.values())
    print(f"[Done] 最终输出: {total_final} 条", file=sys.stderr)
    print(json.dumps(ordered, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
