# 目前使用中：原作者 V3.2 綜合評分

- **來源**：原作者 kevin801221/stock-strategies-only（fork 後**未修改評分邏輯**）
- **狀態**：已採用（每天 14:30 選股）
- **參數位置**：`stock_strategies/config.py`、`stock_strategies/evaluate.py`

## 規則

- 分數 = 基本面 × 權重 + 技術面 × 權重 + 回測勝率 × 權重
  - 基本面：近兩年 EPS、ROE 達門檻 → 100 分，否則 40 分
  - 技術面：均線、RSI、MACD 等，加上量價型態加分
  - 回測：同一套條件在該股過去的勝率
- BUY：總分與技術分都達門檻；50 分以上為 WATCH；其餘 SKIP
- 大盤濾鏡：加權指數跌破月線 → BUY 降為 WATCH
- 夜盤濾鏡：昨晚台指期夜盤大跌 → BUY 降為 WATCH
- 出場（Performance 追蹤用）：停利 +10%、停損 -8%，追蹤 T+5／T+10／T+20

## fork 加上的（只顯示、不影響分數）

三大法人買賣超、外資台指期口數、昨晚美股

## 實際成績

見 Google Sheet `Performance`（BUY）與 `WatchPerformance`（WATCH）分頁、每週五週報。
