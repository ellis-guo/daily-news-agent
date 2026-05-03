#!/bin/bash
# Step 4 wrapper: wechat_fetch.py，最多重试3次
# 失败时向 pipeline_status.json 追加 wechat_fetch 错误字段

SCRIPT="/home/ubuntu/.hermes/scripts/wechat_fetch.py"
VENV_PYTHON="/home/ubuntu/wechat-article-to-markdown/.venv/bin/python"
STATUS_FILE="/home/ubuntu/.hermes/pipeline_status.json"
LOG="/home/ubuntu/.hermes/logs/wechat_fetch.log"
MAX_TRIES=3
RETRY_WAIT=30

mkdir -p "/home/ubuntu/.hermes/logs"

for i in $(seq 1 $MAX_TRIES); do
    echo "[run_step3] 第 $i 次尝试 $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
    "$VENV_PYTHON" "$SCRIPT" >> "$LOG" 2>&1
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "[run_step3] 成功" >> "$LOG"
        exit 0
    fi

    echo "[run_step3] 第 $i 次失败（exit=$EXIT_CODE），等待 ${RETRY_WAIT}s..." >> "$LOG"
    if [ $i -lt $MAX_TRIES ]; then
        sleep $RETRY_WAIT
    fi
done

# 三次都失败，向 pipeline_status.json 注入 wechat_fetch 错误
MSG="wechat_fetch 连续 ${MAX_TRIES} 次失败，请检查 wechat_fetch.log"
echo "[run_step3] $MSG" >> "$LOG"

# 用 python 安全地更新 json（避免 jq 依赖）
python3 - <<EOF
import json, pathlib, datetime
f = pathlib.Path("$STATUS_FILE")
if f.exists():
    try:
        data = json.loads(f.read_text())
    except Exception:
        data = {}
else:
    data = {}

data.setdefault("modules", {})
data["modules"]["wechat_fetch"] = {
    "status": "error",
    "fetched": 0,
    "skipped": 0,
    "error": "$MSG"
}
data["updated_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
f.write_text(json.dumps(data, ensure_ascii=False, indent=2))
EOF

exit 1
