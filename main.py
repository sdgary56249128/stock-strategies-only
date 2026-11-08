"""
V3.2 每日選股訊號系統

新增：
- 回測以「訊號日隔天開盤價」為進場（符合真實可執行）
- 大盤濾鏡：加權指數跌破月線時，BUY 自動降為 WATCH
- 夜盤情緒濾鏡：昨晚台指期夜盤大跌時，BUY 進一步降為 WATCH（風控）
- 成績單：自動追蹤每個 BUY 在 T+1/T+5/T+10/T+20 的實際表現

執行: uv run python main.py
"""

import os
import sys
import time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from stock_strategies.sheet import (
    read_watchlist,
    append_signals,
    read_performance,
    write_performance,
)
from stock_strategies.evaluate import evaluate
from stock_strategies.notify import send_telegram, format_messages
from stock_strategies.market import get_market_state, apply_market_filter
from stock_strategies.night_session import (
    get_night_session,
    apply_night_filter,
    night_filter_note,
)
from stock_strategies.performance import update_performance, summary as perf_summary


REQUIRED_ENV = [
    "FINMIND_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GOOGLE_SHEET_ID",
    "GOOGLE_CREDS_JSON",
]


def main():
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"❌ 缺少環境變數: {missing}", file=sys.stderr)
        sys.exit(1)

    # fork 自訂：休市日不跑（盤前快報已經發過休市通知）
    from stock_strategies.trading_calendar import should_skip
    if should_skip():
        print("📅 今天台股休市，不執行選股")
        return

    # fork 自訂：Mac 上快取會保留，原本「前一天的價格也算新鮮」會讓 14:30 用到昨天收盤；
    # 改成每次都增量抓當天資料，並等 FinMind 更新今日收盤價（mac/run.zsh 設 WAIT_FOR_DATA=1）
    from stock_strategies.config import CACHE_FRESH_DAYS
    CACHE_FRESH_DAYS["daily"] = 0
    if os.environ.get("WAIT_FOR_DATA") == "1":
        from stock_strategies.trading_calendar import wait_for_today_prices
        if not wait_for_today_prices():
            print("⚠️ 等不到今日收盤價，用現有資料執行", file=sys.stderr)

    # 1. 讀取 watchlist
    print(f"[{datetime.now()}] 讀取 watchlist...")
    watchlist = read_watchlist()
    print(f"  → {len(watchlist)} 檔啟用中")

    # 2. 取得大盤狀態（濾鏡）
    print("取得大盤狀態...")
    market = get_market_state()
    print(f"  → {market['note']}")

    # 2b. 取得昨晚夜盤（情緒風控濾鏡）
    print("取得昨晚夜盤...")
    night = get_night_session()
    night_note = night_filter_note(night)
    print(f"  → {night_note}")

    # 3. 個股評分
    results = []
    for i, row in enumerate(watchlist, 1):
        sid = str(row["stock_id"])
        name = row.get("name", "")
        print(f"[{i}/{len(watchlist)}] {sid} {name}")
        r = evaluate(sid, name)
        if r:
            results.append(r)
        time.sleep(0.6)

    # 4. 套用大盤濾鏡：跌破月線時 BUY 一律降為 WATCH
    downgraded = apply_market_filter(results, market)
    if downgraded:
        print(f"⚠️ 大盤跌破月線，{downgraded} 檔 BUY 已自動降為 WATCH")

    # 4b. 套用夜盤情緒濾鏡：昨晚夜盤大跌時 BUY 進一步降為 WATCH
    night_downgraded = apply_night_filter(results, night)
    if night_downgraded:
        print(f"🌙 昨晚夜盤大跌，{night_downgraded} 檔 BUY 已自動降為 WATCH")

    order = {"BUY": 0, "WATCH": 1, "SKIP": 2, "ERROR": 3}
    results.sort(key=lambda x: (order.get(x.get("action"), 4), -x.get("signal_score", 0)))

    buy_count = sum(1 for r in results if r["action"] == "BUY")
    watch_count = sum(1 for r in results if r["action"] == "WATCH")
    print(f"\n{buy_count} BUY, {watch_count} WATCH")

    # 5. 寫回 Signals 分頁
    print("寫回 Google Sheet (Signals)...")
    append_signals(results)

    # 6. 更新 Performance 成績單（追蹤舊 BUY + 附上今日新 BUY）
    print("更新 Performance 成績單...")
    try:
        existing_perf = read_performance()
        updated_perf = update_performance(existing_perf, results)
        write_performance(updated_perf)
        stats = perf_summary(updated_perf)
        if stats["count"] > 0:
            print(
                f"  → 已完成追蹤 {stats['count']} 筆 | "
                f"T+20 勝率 {stats['winrate_t20']}% | "
                f"平均報酬 {stats['avg_t20']}% | "
                f"觸及停利 {stats['hit_target']} 次 / 停損 {stats['hit_stop']} 次"
            )
        else:
            print("  → 尚未有完成追蹤的訊號（需累積 20 交易日）")
    except Exception as e:
        print(f"⚠️ Performance 追蹤失敗: {e}", file=sys.stderr)
        stats = None

    # fork 自訂：WATCH 也追蹤 T+5/T+10/T+20（WatchPerformance 分頁）
    try:
        from stock_strategies.performance_watch import update_watch_performance
        ws = update_watch_performance(results)
        print(f"  → WATCH 追蹤：已完成 {ws['count']} 筆")
    except Exception as e:
        print(f"⚠️ WATCH 追蹤失敗: {e}", file=sys.stderr)

    # 7. 發送 Telegram
    print("發送 Telegram...")
    for msg in format_messages(results, watchlist, market=market, night_note=night_note):
        send_telegram(msg)
        time.sleep(0.5)

    # 8. 若有累積的成績單，額外推一則摘要
    if stats and stats["count"] >= 5:
        send_telegram(_format_perf_message(stats))

    print("✅ 完成")


def _format_perf_message(stats: dict) -> str:
    lines = [
        "📈 *系統成績單（累積追蹤）*",
        "",
        f"已完成追蹤訊號: {stats['count']} 筆",
        f"T+20 勝率: {stats['winrate_t20']}%",
        f"T+20 平均報酬: {stats['avg_t20']}%",
        f"觸及停利 +{int(0.10 * 100)}%: {stats['hit_target']} 次",
        f"觸及停損 -{int(0.08 * 100)}%: {stats['hit_stop']} 次",
        "",
        "_完整紀錄見 Google Sheet『Performance』分頁_",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
