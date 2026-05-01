#!/usr/bin/env python3
"""
预跑脚本：汇总今日所有 LLM token 消耗。
- Haiku：读 token_usage.jsonl
- Sonnet cron / weixin：读 state.db sessions 表
输出 JSON 供 cron job 注入上下文。
"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
today = datetime.now(CST).strftime("%Y-%m-%d")

# ── Haiku（来自 token_usage.jsonl）──────────────────────────
log_file = Path.home() / ".hermes" / "token_usage.jsonl"
haiku_input = haiku_output = haiku_calls = 0

if log_file.exists():
    for line in log_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if e.get("ts", "").startswith(today) and "haiku" in e.get("model", "").lower():
                haiku_input += e.get("input_tokens", 0)
                haiku_output += e.get("output_tokens", 0)
                haiku_calls += 1
        except Exception:
            continue

# ── Sonnet（来自 state.db）──────────────────────────────────
state_db = Path.home() / ".hermes" / "state.db"
cron_input = cron_output = cron_cache_r = cron_cache_w = cron_calls = 0
chat_input = chat_output = chat_cache_r = chat_cache_w = chat_calls = 0

if state_db.exists():
    try:
        conn = sqlite3.connect(str(state_db))
        c = conn.cursor()
        day_start = datetime.strptime(today, "%Y-%m-%d").replace(tzinfo=CST).timestamp()
        day_end = day_start + 86400
        c.execute("""
            SELECT source,
                   SUM(input_tokens), SUM(output_tokens),
                   SUM(cache_read_tokens), SUM(cache_write_tokens),
                   COUNT(*)
            FROM sessions
            WHERE started_at >= ? AND started_at < ?
            GROUP BY source
        """, (day_start, day_end))
        for source, inp, out, cache_r, cache_w, cnt in c.fetchall():
            inp = inp or 0; out = out or 0
            cache_r = cache_r or 0; cache_w = cache_w or 0
            if source == "cron":
                cron_input, cron_output, cron_cache_r, cron_cache_w, cron_calls = inp, out, cache_r, cache_w, cnt
            elif source == "weixin":
                chat_input, chat_output, chat_cache_r, chat_cache_w, chat_calls = inp, out, cache_r, cache_w, cnt
        conn.close()
    except Exception as e:
        pass

# ── 费用计算 ─────────────────────────────────────────────────
# Haiku: $0.80/1M input, $4/1M output
# Sonnet 3.5: $3/1M input, $3.75/1M cache_write, $0.30/1M cache_read, $15/1M output
haiku_cost = haiku_input * 0.80/1_000_000 + haiku_output * 4/1_000_000
cron_cost  = (cron_input * 3.0 + cron_cache_w * 3.75 + cron_cache_r * 0.30) / 1_000_000 + cron_output * 15/1_000_000
chat_cost  = (chat_input * 3.0 + chat_cache_w * 3.75 + chat_cache_r * 0.30) / 1_000_000 + chat_output * 15/1_000_000
total_cost = haiku_cost + cron_cost + chat_cost

result = {
    "date": today,
    "haiku": {"calls": haiku_calls, "input": haiku_input, "output": haiku_output, "cost_usd": round(haiku_cost, 6)},
    "cron":  {"calls": cron_calls, "input": cron_input, "cache_r": cron_cache_r, "cache_w": cron_cache_w, "output": cron_output, "cost_usd": round(cron_cost, 4)},
    "chat":  {"calls": chat_calls, "input": chat_input, "cache_r": chat_cache_r, "cache_w": chat_cache_w, "output": chat_output, "cost_usd": round(chat_cost, 4)},
    "total_cost_usd": round(total_cost, 4),
}

# 写到 daily_token_report.json 供汇报 cron 读取
report_file = Path.home() / ".hermes" / "daily_token_report.json"
report_file.write_text(json.dumps(result, ensure_ascii=False, indent=2))

print(json.dumps(result, ensure_ascii=False))
