#!/usr/bin/env python3
"""
预跑脚本：读取今日 token_usage.jsonl，输出 Haiku 消耗汇总，注入给 Sonnet cron job。
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
today = datetime.now(CST).strftime("%Y-%m-%d")
log_file = Path.home() / ".hermes" / "token_usage.jsonl"

haiku_input = 0
haiku_output = 0
haiku_calls = 0

if log_file.exists():
    for line in log_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if entry.get("ts", "").startswith(today) and entry.get("model", "").startswith("claude-haiku"):
                haiku_input += entry.get("input_tokens", 0)
                haiku_output += entry.get("output_tokens", 0)
                haiku_calls += 1
        except Exception:
            continue

# Haiku 定价：$0.80/1M input, $4/1M output
haiku_cost = haiku_input * 0.80 / 1_000_000 + haiku_output * 4 / 1_000_000

print(json.dumps({
    "date": today,
    "haiku_calls": haiku_calls,
    "haiku_input_tokens": haiku_input,
    "haiku_output_tokens": haiku_output,
    "haiku_cost_usd": round(haiku_cost, 6),
}, ensure_ascii=False))
