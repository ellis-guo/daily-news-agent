#!/usr/bin/env python3
"""
Token 汇报脚本：读取 daily_token_report.json，生成今日消耗汇报消息。
挂在 token-report cron job 的 script 字段，输出 JSON 注入给 Sonnet。
"""
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
today = datetime.now(CST).strftime("%Y-%m-%d")

report_file = Path.home() / ".hermes" / "daily_token_report.json"

if not report_file.exists():
    print(json.dumps({"error": "daily_token_report.json 不存在，今日 pipeline 可能未运行"}))
else:
    data = json.loads(report_file.read_text())
    print(json.dumps(data, ensure_ascii=False))
