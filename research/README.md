# 策略研究紀錄（本 fork 自訂）

收集外部看到的選股／交易策略，記錄規則、來源、回測結果與結論。
**這裡的策略都不會影響每天的選股**；確認有效、也決定採用後，才會另外改到正式流程。

- 每個策略一個檔案：`strategies/<英文-id>.md`（檔名只用英文，見 AGENTS.md）
- 回測程式放 `research/`，結果寫回該策略檔的「回測結果」
- 狀態：`待回測` → `回測中` → `有效`／`無效`／`參考` → `已採用`

## 策略總表

| ID | 名稱 | 來源 | 類型 | 狀態 | 結論 |
|---|---|---|---|---|---|
| [current-v3](strategies/current-v3.md) | 目前使用中（原作者 V3.2） | 原作者 kevin801221 | 綜合評分 | 已採用 | 每天 14:30 選股使用中 |
| [xq-macd-bb-ma20](strategies/xq-macd-bb-ma20.md) | MACD 翻紅＋布林開口＋站上 20MA | XQ 全球贏家 FB 2026-11-16 | 順勢 | 待回測 | — |
| [atr-trailing-exit](strategies/atr-trailing-exit.md) | ATR 移動停損（出場） | Chandelier Exit | 出場規則 | 有效（初步） | ATR×3 明顯優於現行 +10%/-8%，12 年中 11 年較好 |
| [revenue-momentum](strategies/revenue-momentum.md) | 月營收動能 | 台股常見 | 基本面動能 | 待回測 | — |
| [trust-buying-streak](strategies/trust-buying-streak.md) | 投信連續買超 | 台股常見 | 籌碼 | 待回測 | — |
| [relative-strength](strategies/relative-strength.md) | 相對強度排名 | 動能效果 | 動能 | 待回測 | — |
| [high-52w-breakout](strategies/high-52w-breakout.md) | 52 週新高突破 | George & Hwang | 順勢／突破 | 待回測 | — |
| [pullback-rsi](strategies/pullback-rsi.md) | 多頭拉回買進（RSI2） | Larry Connors | 均值回歸 | 待回測 | — |
| [margin-retreat](strategies/margin-retreat.md) | 融資減少、股價上漲 | 台股常見 | 籌碼 | 待回測 | — |
| [foreign-holding-up](strategies/foreign-holding-up.md) | 外資持股比例上升 | 台股常見 | 籌碼 | 待回測 | — |
| [value-yield](strategies/value-yield.md) | 低本益比＋高殖利率 | 價值投資 | 價值 | 待回測 | — |
| [ma-squeeze-breakout](strategies/ma-squeeze-breakout.md) | 均線糾結後突破 | 台股常見 | 型態 | 待回測 | — |
| [seasonality](strategies/seasonality.md) | 季節性（作帳、元月、除息） | 日曆效應 | 時間 | 待回測 | — |
| [market-timing-plus](strategies/market-timing-plus.md) | 大盤擇時加強版 | 現行濾鏡延伸 | 濾鏡 | 待回測 | — |
| [position-sizing](strategies/position-sizing.md) | 資金控管 | 風險管理 | 風險管理 | 待回測 | — |
