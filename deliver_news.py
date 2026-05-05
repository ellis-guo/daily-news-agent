#!/usr/bin/env python3
"""
读取今日 news MD 文件，直接输出内容。
"""
import sys
import datetime
from pathlib import Path

today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
path = Path.home() / ".hermes" / "digests" / f"{today}-news.md"

if not path.exists():
    print(f"ERROR: {path} not found")
    sys.exit(1)

print(path.read_text(encoding="utf-8").strip())
