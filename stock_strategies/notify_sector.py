"""依族群分則的 Telegram 通知（本 fork 自訂）

每個 category 一則訊息：族群強弱 → BUY → WATCH → SKIP 一行帶過，
量價解讀併在每檔底下。獨立成檔，減少與原作者 notify.py 的合併衝突。
"""

import numpy as np

from .chips_view import chips_line
from .notify import _explain_why, _format_stock_detail, _trend_emoji

TG_LIMIT = 3900  # Telegram 單則上限 4096，留緩衝

VOLUME_GLOSSARY = [
    "📖 *量價字典速查*",
    "• 倍量柱 = 今日量 ≥ 昨日 2x（主力點火）",
    "• 梯量柱 = 連續 3 日量能遞增（健康上攻）",
    "• 縮量柱 = 下跌時量能遞減（洗盤，主力未退）",
    "• 低量柱 = 極限窒息量（拋壓耗盡）",
    "• 放量滯漲 = 高檔爆量但 K 收黑（主力倒貨）",
]

_ORDER = {"BUY": 0, "WATCH": 1}


def _volume_lines(s: dict) -> list[str]:
    c = s.get("components", {})
    patterns = c.get("volume_patterns") or []
    if not patterns:
        return []
    lines = [f"🔬 量能: {' + '.join(patterns)}"]
    if "放量滯漲" in patterns:
        lines.append("⚠️ 放量滯漲 — 留意主力倒貨")
    if c.get("volume_verdict"):
        lines.append(f"結論: {c['volume_verdict']}")
    return lines


def _split(text: str) -> list[str]:
    """超過 Telegram 長度就在空行處切開"""
    if len(text) <= TG_LIMIT:
        return [text]
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > TG_LIMIT:
            parts.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts


def format_sector_messages(signals: list[dict], watchlist: list[dict]) -> list[str]:
    cat_map = {str(w["stock_id"]): w.get("category") or "其他" for w in watchlist}
    sectors: dict[str, list[dict]] = {}
    for s in signals:
        sectors.setdefault(cat_map.get(str(s["stock_id"]), "其他"), []).append(s)

    def avg_chg(stocks):
        vals = [s["trend"]["chg_5d"] for s in stocks if s.get("trend", {}).get("chg_5d") is not None]
        return float(np.mean(vals)) if vals else 0.0

    messages = []
    quiet = []  # 全部 SKIP 的族群合併成一則
    for cat, stocks in sorted(sectors.items(), key=lambda x: avg_chg(x[1]), reverse=True):
        avg = avg_chg(stocks)
        buys = [s for s in stocks if s.get("action") == "BUY"]
        watches = [s for s in stocks if s.get("action") == "WATCH"]
        others = [s for s in stocks if s.get("action") not in _ORDER]
        if not buys and not watches:
            quiet.append(f"{_trend_emoji(avg)} *{cat}* 5日{avg:+.1f}%｜" + ", ".join(
                f"{s['stock_id']}{s['name']}({s.get('signal_score', '—')})" for s in others
            ))
            continue

        lines = [
            f"{_trend_emoji(avg)} *{cat}* ({len(stocks)}檔) 5日均漲{avg:+.1f}%",
            f"BUY {len(buys)} | WATCH {len(watches)} | SKIP {len(others)}",
            "",
        ]
        for s in sorted(buys + watches, key=lambda s: (_ORDER[s["action"]], -s.get("signal_score", 0))):
            tag = "🟢 BUY" if s["action"] == "BUY" else "🟡 WATCH"
            lines.append(tag)
            lines.extend(_format_stock_detail(s))
            if chips_line(s.get("chips")):
                lines.append(chips_line(s["chips"]))
            why = _explain_why(s)
            lines.append(f"💡 為何買: {why}" if s["action"] == "BUY" else f"❓ 差在: {why}")
            lines.extend(_volume_lines(s))
            lines.append("")
        if others:
            lines.append("⚪ " + ", ".join(
                f"{s['stock_id']}{s['name']}({s.get('signal_score', '—')})" for s in others
            ))
        messages.extend(_split("\n".join(lines).rstrip()))
    if quiet:
        head = f"⚪ *其他族群*（{len(quiet)} 個，今日全部 SKIP）"
        messages.extend(_split("\n\n".join([head, *quiet])))
    return messages
