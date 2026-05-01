#!/bin/bash
# Step 3 wrapper: wechat_fetch.py，最多重试3次，失败追加 pipeline_error.txt

SCRIPT="/home/ubuntu/.hermes/scripts/wechat_fetch.py"
ERROR_FLAG="/home/ubuntu/.hermes/pipeline_error.txt"
LOG="/home/ubuntu/.hermes/logs/wechat_fetch.log"
MAX_TRIES=3
RETRY_WAIT=30

for i in $(seq 1 $MAX_TRIES); do
    echo "[run_step3] 第 $i 次尝试 $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
    /usr/bin/python3 "$SCRIPT" >> "$LOG" 2>&1
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

# 三次都失败，追加到 error flag
MSG="[$(date '+%Y-%m-%d %H:%M:%S')] Step 3 (wechat_fetch) 连续 ${MAX_TRIES} 次失败。请检查 wechat_fetch.log。"
echo "$MSG" >> "$ERROR_FLAG"
echo "[run_step3] $MSG" >> "$LOG"
exit 1
