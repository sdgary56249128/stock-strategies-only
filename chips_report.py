"""盤後籌碼通知（本 fork 自訂）

週一到週五 16:30 由 mac/run.zsh chips 執行；也可手動：uv run python chips_report.py
內容：外資台指期淨未平倉＋今日 BUY/WATCH 的三大法人買賣超。只顯示，不影響分數。
FinMind 實測：期貨法人約 15:00、個股法人約 16:10～16:20 更新；還沒更新就每 5 分鐘等，最多 2 小時。
"""

import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from stock_strategies.chips_view import chips_line, futures_line, futures_oi, stock_chips
from stock_strategies.notify import send_telegram
from stock_strategies.sheet import read_latest_signals, read_watchlist
from stock_strategies.trading_calendar import should_skip, taipei_today

WEEKDAY = "一二三四五六日"


def _md(s) -> str:
    return str(s).replace("*", "").replace("_", "").replace("`", "").replace("[", "")


def wait_for_today_chips(max_minutes: int = 120, every_minutes: int = 5) -> bool:
    today = taipei_today().isoformat()
    for i in range(max_minutes // every_minutes + 1):
        c = stock_chips("2330")
        if c and c["date"] == today:
            return True
        if i == 0:
            print(f"  → 今日法人資料還沒更新，每 {every_minutes} 分鐘檢查一次")
        time.sleep(every_minutes * 60)
    return False


def build_report(today, fut: str | None, picks: list[dict]) -> str:
    lines = [f"🏦 *盤後籌碼* {today:%m/%d}（{WEEKDAY[today.weekday()]}）", ""]
    lines.append(fut or "🌐 外資台指期資料暫時取不到")
    lines.append("")
    if not picks:
        lines.append("📋 今日沒有 BUY/WATCH")
    else:
        buy = sum(1 for p in picks if p["chips"] and p["chips"]["foreign"] > 0)
        sell = sum(1 for p in picks if p["chips"] and p["chips"]["foreign"] < 0)
        lines.append(f"📋 *今日 BUY/WATCH 法人動向*（外資買超 {buy} 檔｜賣超 {sell} 檔）")
        lines.append("")
        picks = sorted(picks, key=lambda p: -(sum((p["chips"] or {}).get(k, 0) for k in ("foreign", "trust", "dealer"))))
        for p in picks:
            dot = "🟢" if p["action"] == "BUY" else "🟡"
            lines.append(f"{dot} {p['action']} {p['stock_id']} {_md(p['name'])}（{p['category']}）{p['score']}分")
            lines.append("    " + (chips_line(p["chips"]) or "🏦 法人資料取不到"))
    lines.append("")
    lines.append("_依三大法人合計買超排序｜籌碼僅供參考，不影響選股分數_")
    return "\n".join(lines)


def main():
    if should_skip():
        print("📅 今天台股休市，不發盤後籌碼")
        return
    today = taipei_today()
    if not wait_for_today_chips():
        print("⚠️ 等不到今日法人資料，用現有資料發送", file=sys.stderr)
    cat = {str(w["stock_id"]): w.get("category") or "其他" for w in read_watchlist()}
    signals = [s for s in read_latest_signals(limit=300)
               if s.get("date") == today.isoformat() and str(s.get("action")).upper() in ("BUY", "WATCH")]
    picks = []
    for s in signals:
        sid = str(s["stock_id"])
        picks.append({"stock_id": sid, "name": s.get("name", ""), "action": str(s["action"]).upper(),
                      "score": s.get("signal_score", ""), "category": cat.get(sid, "其他"),
                      "chips": stock_chips(sid)})
        time.sleep(0.3)
    text = build_report(today, futures_line(futures_oi()), picks)
    for i in range(0, len(text), 3900):
        send_telegram(text[i:i + 3900])
    print(f"✅ 盤後籌碼已發送（{len(picks)} 檔）")


if __name__ == "__main__":
    main()
