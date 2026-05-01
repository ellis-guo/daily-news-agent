#!/bin/bash
# Step 2 wrapper: news_filter.py，最多重试3次，失败写 pipeline_error.txt

SCRIPT="/home/ubuntu/.hermes/scripts/news_filter.py"
ERROR_FLAG="/home/ubuntu/.hermes/pipeline_error.txt"
LOG="/home/ubuntu/.hermes/logs/news_filter.log"
MAX_TRIES=3
RETRY_WAIT=60

# 清除上次的 error flag
rm -f "$ERROR_FLAG"

for i in $(seq 1 $MAX_TRIES); do
    echo "[run_step2] 第 $i 次尝试 $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
    /usr/bin/python3 "$SCRIPT" >> "$LOG" 2>&1
    EXIT_CODE=$?

    # 检查今日 MD 是否生成且有实质内容（行数 > 5）
    MD_FILE="/home/ubuntu/.hermes/digests/$(TZ='Asia/Shanghai' date +%Y-%m-%d).md"
    if [ -f "$MD_FILE" ] && [ $(wc -l < "$MD_FILE") -gt 5 ]; then
        echo "[run_step2] 成功，MD 已生成: $MD_FILE" >> "$LOG"
        exit 0
    fi

    echo "[run_step2] 第 $i 次失败（exit=$EXIT_CODE，MD 不存在或内容不足），等待 ${RETRY_WAIT}s..." >> "$LOG"
    if [ $i -lt $MAX_TRIES ]; then
        sleep $RETRY_WAIT
    fi
done

# 三次都失败
MSG="[$(date '+%Y-%m-%d %H:%M:%S')] Step 2 (news_filter) 连续 ${MAX_TRIES} 次失败，今日 MD 未生成。请检查 news_filter.log。"
echo "$MSG" > "$ERROR_FLAG"
echo "[run_step2] $MSG" >> "$LOG"
exit 1
