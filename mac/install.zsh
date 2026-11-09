#!/bin/zsh
# 安裝／更新 Mac 上的選股排程（週一到週五 08:00 盤前快報、14:30 收盤選股、16:30 盤後籌碼）
DIR=${0:A:h}
for job in premarket daily chips; do
  cp "$DIR/com.uq.stock-$job.plist" ~/Library/LaunchAgents/
  launchctl bootout gui/$(id -u)/com.uq.stock-$job 2>/dev/null
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.uq.stock-$job.plist && echo "✅ com.uq.stock-$job"
done
