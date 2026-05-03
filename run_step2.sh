#!/bin/bash
# run_step2.sh — pipeline.py 重试 wrapper（3次，60s间隔）
# 成功标准：MD 文件存在且行数 > 5

SCRIPTS_DIR="$HOME/.hermes/scripts"
DIGESTS_DIR="$HOME/.hermes/digests"
TODAY=$(TZ='Asia/Shanghai' date +%Y-%m-%d)
MD_FILE="$DIGESTS_DIR/$TODAY.md"
ERROR_FILE="$HOME/.hermes/pipeline_error.txt"
LOG_FILE="$HOME/.hermes/logs/pipeline.log"

mkdir -p "$HOME/.hermes/logs"

# 清除旧错误标记
rm -f "$ERROR_FILE"

for attempt in 1 2 3; do
    echo "[run_step2] attempt $attempt/3 at $(date)" >> "$LOG_FILE" 2>&1
    python3 "$SCRIPTS_DIR/pipeline.py" >> "$LOG_FILE" 2>&1

    if [ -f "$MD_FILE" ] && [ "$(wc -l < "$MD_FILE")" -gt 5 ]; then
        echo "[run_step2] success on attempt $attempt" >> "$LOG_FILE"
        exit 0
    fi

    echo "[run_step2] attempt $attempt failed, MD not ready" >> "$LOG_FILE"
    if [ $attempt -lt 3 ]; then
        sleep 60
    fi
done

echo "[run_step2] all 3 attempts failed" >> "$LOG_FILE"
echo "pipeline.py (Step2) 连续3次失败，请检查 $LOG_FILE" > "$ERROR_FILE"
exit 1
