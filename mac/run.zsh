#!/bin/zsh
# fork 自訂：Mac launchd 排程執行選股（GitHub 免費排程常延遲數小時）
#   zsh mac/run.zsh premarket   # 08:00 夜盤盤前快報
#   zsh mac/run.zsh daily       # 14:30 收盤選股
#   zsh mac/run.zsh chips       # 16:30 盤後籌碼
# 失敗時推 Telegram；紀錄在 ~/Library/Logs/stock-<job>.log

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
REPO=${0:A:h:h}
JOB=$1
case $JOB in
  premarket) SCRIPT=premarket.py; NAME="夜盤盤前快報" ;;
  daily)     SCRIPT=main.py;      NAME="收盤選股"; export WAIT_FOR_DATA=1 ;;
  chips)     SCRIPT=chips_report.py; NAME="盤後籌碼" ;;
  *) echo "用法: zsh mac/run.zsh premarket|daily|chips"; exit 2 ;;
esac
LOG=~/Library/Logs/stock-$JOB.log
cd "$REPO" || exit 1

# wait up to 2 minutes for the network after wake from sleep
for i in {1..24}; do
  curl -s -m5 -o /dev/null https://api.telegram.org && break
  sleep 5
done

{
  echo "── $(date '+%F %T') 開始 $NAME"
  uv run python "$SCRIPT"
  code=$?
  echo "── $(date '+%F %T') 結束 exit=$code"
  # 週五選股跑完接著發週報
  if [[ $JOB == daily && $code == 0 && $(date +%u) == 5 ]]; then
    echo "── $(date '+%F %T') 開始 週報"
    uv run python weekly_report.py
    code=$?
    NAME="週報"
    echo "── $(date '+%F %T') 結束 exit=$code"
  fi
} >> "$LOG" 2>&1

if [[ $code != 0 ]]; then
  tail_text=$(tail -8 "$LOG")
  uv run python -c '
import sys
from dotenv import load_dotenv; load_dotenv(".env")
from stock_strategies.notify import send_telegram
name, log = sys.argv[1], sys.argv[2]
send_telegram(f"❌ Mac 排程執行失敗：{name}\n\n{log[-1500:]}\n\n👉 回 Claude 說「選股排程失敗了」".replace("*", "").replace("_", " ").replace("`", "")
)' "$NAME" "$tail_text" >> "$LOG" 2>&1
fi
exit $code
