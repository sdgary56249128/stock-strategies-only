"""每週選股週報（本 fork 自訂）

週五收盤選股後由 mac/run.zsh 執行；也可手動：uv run python weekly_report.py
內容：本週每日 BUY/WATCH 數、重複出現的 WATCH（分數變化）、族群熱度、WATCH 追蹤成績。
"""

from collections import Counter, defaultdict
from datetime import date, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from stock_strategies.notify import send_telegram
from stock_strategies.performance_watch import read_watch_performance
from stock_strategies.sheet import get_gsheet, read_watchlist
from stock_strategies.trading_calendar import taipei_today

WEEKDAY = "一二三四五六日"


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _md(s: str) -> str:
    return str(s).replace("*", "").replace("_", "").replace("`", "").replace("[", "")


def build_report(signals: list[dict], watchlist: list[dict], perf: list[dict], today) -> str | None:
    monday = today - timedelta(days=today.weekday())
    week = [s for s in signals if monday.isoformat() <= str(s.get("date", "")) <= today.isoformat()]
    if not week:
        return None
    days = sorted({s["date"] for s in week})
    cat = {str(w["stock_id"]): w.get("category") or "其他" for w in watchlist}

    lines = [f"📅 *選股週報* {monday:%m/%d}～{today:%m/%d}（{len(days)} 個交易日）", ""]

    lines.append("📊 *每日訊號*")
    for d in days:
        c = Counter(s["action"] for s in week if s["date"] == d)
        wd = WEEKDAY[date.fromisoformat(d).weekday()]
        lines.append(f"{d[5:].replace('-', '/')}（{wd}）BUY {c.get('BUY', 0)} | WATCH {c.get('WATCH', 0)} | SKIP {c.get('SKIP', 0)}")
    lines.append("")

    hits = defaultdict(list)
    for s in sorted(week, key=lambda s: s["date"]):
        if s["action"] in ("BUY", "WATCH"):
            hits[str(s["stock_id"])].append(s)
    ranked = sorted(hits.items(), key=lambda x: (-len(x[1]), -(_f(x[1][-1]["signal_score"]) or 0)))
    if ranked:
        lines.append("🔁 *本週常出現*（出現天數｜分數變化）")
        for sid, ss in ranked[:10]:
            first, last = _f(ss[0]["signal_score"]) or 0, _f(ss[-1]["signal_score"]) or 0
            arrow = "↗" if last > first + 1 else "↘" if last < first - 1 else "→"
            buy = "，含 BUY" if any(s["action"] == "BUY" for s in ss) else ""
            lines.append(f"• {sid} {_md(ss[-1]['name'])}（{cat.get(sid, '其他')}）{len(ss)}/{len(days)} 天｜{first:.0f} {arrow} {last:.0f}{buy}")
        lines.append("")

    heat = Counter(cat.get(str(s["stock_id"]), "其他") for s in week if s["action"] in ("BUY", "WATCH"))
    if heat:
        lines.append("🔥 *族群熱度*（BUY＋WATCH 次數）")
        lines.append("、".join(f"{c} {n}" for c, n in heat.most_common(8)))
        lines.append("")

    lines.append("📈 *WATCH 追蹤成績*")
    t5 = [_f(r.get("t5_ret")) for r in perf]
    t5 = [x for x in t5 if x is not None]
    t20 = [_f(r.get("t20_ret")) for r in perf if str(r.get("status")) == "完成"]
    t20 = [x for x in t20 if x is not None]
    lines.append(f"追蹤中 {sum(1 for r in perf if str(r.get('status')) != '完成')} 筆，累計 {len(perf)} 筆")
    if t5:
        lines.append(f"T+5：{len(t5)} 筆，上漲比例 {sum(x > 0 for x in t5) / len(t5) * 100:.0f}%，平均 {sum(t5) / len(t5):+.2f}%")
    if t20:
        lines.append(f"T+20：{len(t20)} 筆，上漲比例 {sum(x > 0 for x in t20) / len(t20) * 100:.0f}%，平均 {sum(t20) / len(t20):+.2f}%")
    stop = sum(1 for r in perf if str(r.get("hit_stop")).upper() == "Y")
    target = sum(1 for r in perf if str(r.get("hit_target")).upper() == "Y")
    lines.append(f"觸及停利 {target} 次｜觸及停損 {stop} 次")
    if not t5:
        lines.append("_T+5 數據要累積滿 5 個交易日才會出現_")
    lines.append("")
    lines.append("_僅供參考，投資決策請自行判斷_")
    return "\n".join(lines)


def main():
    signals = get_gsheet().worksheet("Signals").get_all_records()
    report = build_report(signals, read_watchlist(), read_watch_performance(), taipei_today())
    if report is None:
        print("本週沒有選股紀錄，不發週報")
        return
    send_telegram(report)
    print("✅ 週報已發送")


if __name__ == "__main__":
    main()
