#!/usr/bin/env python3
"""
Token 汇报脚本：读取 daily_token_report.json，生成今日消耗汇报消息。
挂在 token-report cron job 的 script 字段，输出 JSON 注入给 Sonnet。
"""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
today = datetime.now(CST).strftime("%Y-%m-%d")

report_file = Path.home() / ".hermes" / "daily_token_report.json"

if not report_file.exists():
    data = {"error": "daily_token_report.json 不存在，今日 pipeline 可能未运行"}
else:
    data = json.loads(report_file.read_text())

# 顺带检查 wechat-download-api 登录状态
try:
    resp = urllib.request.urlopen("http://localhost:5000/api/admin/status", timeout=5)
    status = json.loads(resp.read().decode())
    expire_time_ms = status.get("expireTime", 0)
    is_expired = status.get("isExpired", True)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    hours_left = (expire_time_ms - now_ms) / 1000 / 3600
    data["wechat_login"] = {
        "is_expired": is_expired,
        "hours_left": round(hours_left, 1),
        "account": status.get("nickname", ""),
    }
except Exception as e:
    data["wechat_login"] = {"error": str(e)}

print(json.dumps(data, ensure_ascii=False))
