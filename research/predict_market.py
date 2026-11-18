"""大盤方向預測（研究用，不影響每天選股）

uv run --with scikit-learn --with tabulate python research/predict_market.py

問題：每天 08:00（開盤前）用當時已知的資訊，預測加權指數
  - gap：今天開盤 vs 昨天收盤（跳空方向；只能參考，無法交易）
  - oc ：今天收盤 vs 今天開盤（開盤買、收盤賣）
  - d5 ：5 個交易日後收盤 vs 今天開盤
特徵（全部只用 d-1 收盤／前一晚美股，避免偷看未來）：
  台股技術：加權指數 1/5/20 日報酬、距月線/季線、RSI14、20 日波動
  美股：費半、那斯達克、標普、台積電 ADR 前一晚漲跌；VIX、VXN 水準與變化
  匯率：美元兌台幣 5 日變化（正 = 台幣貶）
  籌碼：大盤融資餘額 1/5 日變化、三大法人合計買賣超（當日、5 日）、外資台指期淨未平倉與變化
驗證：逐年 walk-forward（用 Y 年以前的資料訓練、預測 Y 年），2020～2026 每年重訓
樣本：2018-07 起（外資期貨資料從 2018/06 開始）
P/C ratio 沒有現成歷史資料，第一版不納入
"""

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MKT = DATA / "market"
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT.parent / ".env")
except ImportError:
    pass

FM_URL = "https://api.finmindtrade.com/api/v4/data"
YAHOO = ["^VIX", "^VXN", "^SOX", "^IXIC", "^GSPC", "TSM", "TWD=X"]


# ---------------- 資料 ----------------

def yahoo_hist(sym: str) -> pd.Series:
    f = MKT / f"yahoo_{sym.strip('^').replace('=', '_')}.parquet"
    if not f.exists() or time.time() - f.stat().st_mtime > 6 * 3600:
        j = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                         params={"period1": 1388534400, "period2": int(time.time()), "interval": "1d"},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=60).json()
        res = j["chart"]["result"][0]
        tz = res["meta"].get("gmtoffset", 0)
        df = pd.DataFrame({
            "date": [datetime.fromtimestamp(t + tz, timezone.utc).strftime("%Y-%m-%d") for t in res["timestamp"]],
            "close": res["indicators"]["quote"][0]["close"]}).dropna()
        MKT.mkdir(parents=True, exist_ok=True)
        df.to_parquet(f)
    df = pd.read_parquet(f).drop_duplicates("date", keep="last")
    return pd.Series(df["close"].values, index=pd.to_datetime(df["date"])).sort_index()


def finmind_hist(dataset: str, data_id: str = "", start: str = "2015-01-01") -> pd.DataFrame:
    f = MKT / f"{dataset}_{data_id or 'all'}.parquet"
    if not f.exists() or time.time() - f.stat().st_mtime > 6 * 3600:
        p = {"dataset": dataset, "start_date": start}
        if data_id:
            p["data_id"] = data_id
        j = requests.get(FM_URL, params=p, timeout=120,
                         headers={"Authorization": f"Bearer {os.environ['FINMIND_TOKEN']}"}).json()
        MKT.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(j.get("data", [])).to_parquet(f)
    return pd.read_parquet(f)


def taiex() -> pd.DataFrame:
    df = pd.read_parquet(DATA / "TaiwanStockPrice" / "TAIEX.parquet")
    df = df.rename(columns={"max": "high", "min": "low"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates("date", keep="last").set_index("date").sort_index()
    return df[["open", "high", "low", "close"]].astype(float)


# ---------------- 特徵 ----------------

def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + up / dn)


def build() -> pd.DataFrame:
    tw = taiex()
    c = tw["close"]
    feat = pd.DataFrame(index=tw.index)
    # --- 台股技術（d-1 收盤）---
    tech = pd.DataFrame({
        "tw_ret1": c.pct_change(), "tw_ret5": c.pct_change(5), "tw_ret20": c.pct_change(20),
        "tw_ma20": c / c.rolling(20).mean() - 1, "tw_ma60": c / c.rolling(60).mean() - 1,
        "tw_rsi14": rsi(c), "tw_vol20": c.pct_change().rolling(20).std(),
    })
    feat = feat.join(tech.shift(1))

    # --- 美股：取「台股 d 日之前最後一個美股交易日」的資料 ---
    def us_asof(s: pd.Series, name: str, level: bool = False):
        df = pd.DataFrame({f"{name}_ret1": s.pct_change()})
        if level:
            df[f"{name}_lvl"] = s
            df[f"{name}_chg1"] = s.diff()
            df[f"{name}_z60"] = (s - s.rolling(60).mean()) / s.rolling(60).std()
        df.index = df.index + pd.Timedelta(days=1)  # 美股 t 日收盤 → 台股 t+1 日以後可用
        return pd.merge_asof(pd.DataFrame(index=tw.index), df.sort_index(), left_index=True,
                             right_index=True, direction="backward")

    for sym, name, lvl in [("^SOX", "sox", False), ("^IXIC", "ixic", False), ("^GSPC", "spx", False),
                           ("TSM", "tsm", False), ("^VIX", "vix", True), ("^VXN", "vxn", True)]:
        feat = feat.join(us_asof(yahoo_hist(sym), name, lvl))
    fx = yahoo_hist("TWD=X")
    fxd = pd.DataFrame({"twd_chg5": fx.pct_change(5)})
    fxd.index = fxd.index + pd.Timedelta(days=1)
    feat = feat.join(pd.merge_asof(pd.DataFrame(index=tw.index), fxd.sort_index(), left_index=True,
                                   right_index=True, direction="backward"))

    # --- 台股籌碼（d-1）---
    m = finmind_hist("TaiwanStockTotalMarginPurchaseShortSale")
    m = m[m["name"] == "MarginPurchaseMoney"].copy()
    m["date"] = pd.to_datetime(m["date"])
    bal = m.drop_duplicates("date", keep="last").set_index("date")["TodayBalance"].astype(float).sort_index()
    inst = finmind_hist("TaiwanStockTotalInstitutionalInvestors")
    inst = inst[inst["name"] == "total"].copy()
    inst["date"] = pd.to_datetime(inst["date"])
    net = inst.drop_duplicates("date", keep="last").set_index("date")
    net = ((net["buy"].astype(float) - net["sell"].astype(float)) / 1e8).sort_index()
    fut = finmind_hist("TaiwanFuturesInstitutionalInvestors", "TX")
    fut = fut[fut["institutional_investors"] == "外資"].copy()
    fut["date"] = pd.to_datetime(fut["date"])
    fut = fut.drop_duplicates("date", keep="last").set_index("date").sort_index()
    oi = (fut["long_open_interest_balance_volume"].astype(float)
          - fut["short_open_interest_balance_volume"].astype(float))
    chips = pd.DataFrame({
        "margin_chg1": bal.pct_change(), "margin_chg5": bal.pct_change(5),
        "inst_net": net, "inst_net5": net.rolling(5).sum(),
        "fut_oi": oi / 1e4, "fut_oi_chg1": oi.diff() / 1e4, "fut_oi_chg5": oi.diff(5) / 1e4,
    })
    feat = feat.join(chips.reindex(tw.index).shift(1))

    # --- 目標 ---
    # 08:00 預測時昨天收盤已經買不到，可交易的報酬一律從「今天開盤」算起
    o = tw["open"]
    feat["r_gap"] = o / c.shift(1) - 1           # 參考：跳空（無法交易）
    feat["r_oc"] = c / o - 1                      # 今天開盤買、收盤賣
    feat["r_d5"] = c.shift(-4) / o - 1            # 今天開盤買、第 5 個交易日收盤賣
    feat["y_gap"] = (feat["r_gap"] > 0).astype(int)
    feat["y_oc"] = (feat["r_oc"] > 0).astype(int)
    feat["y_d5"] = (feat["r_d5"] > 0).astype(int)
    feat.loc[feat.index[-4:], ["y_d5", "r_d5"]] = np.nan  # 未來還沒發生
    return feat[feat.index >= "2018-07-01"]


FEATURES = None  # build() 之後決定


# ---------------- 模型與驗證 ----------------

def walk_forward(df: pd.DataFrame, target: str, years=range(2020, 2027)) -> pd.DataFrame:
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    feats = [c for c in df.columns if not c.startswith(("y_", "r_"))]
    out = []
    for y in years:
        tr = df[(df.index.year < y)].dropna(subset=feats + [target])
        te = df[(df.index.year == y)].dropna(subset=feats + [target])
        if len(tr) < 200 or te.empty:
            continue
        lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))
        gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                            min_samples_leaf=40, random_state=0)
        lr.fit(tr[feats], tr[target])
        gb.fit(tr[feats], tr[target])
        o = pd.DataFrame(index=te.index)
        o["y"] = te[target]
        o["p_lr"] = lr.predict_proba(te[feats])[:, 1]
        o["p_gb"] = gb.predict_proba(te[feats])[:, 1]
        o["base"] = float(tr[target].mean())  # 訓練期上漲比例（永遠猜多數）
        out.append(o)
    return pd.concat(out)


def score(o: pd.DataFrame) -> dict:
    from sklearn.metrics import roc_auc_score
    res = {"樣本": len(o), "實際上漲比例": f"{o['y'].mean():.1%}",
           "永遠猜漲 準確率": f"{o['y'].mean():.1%}"}
    for k, name in [("p_lr", "邏輯迴歸"), ("p_gb", "梯度提升樹")]:
        acc = ((o[k] > 0.5).astype(int) == o["y"]).mean()
        res[f"{name} 準確率"] = f"{acc:.1%}"
        res[f"{name} AUC"] = f"{roc_auc_score(o['y'], o[k]):.3f}"
    return res


def by_year(o: pd.DataFrame, k: str) -> pd.DataFrame:
    from sklearn.metrics import roc_auc_score
    rows = []
    for y, g in o.groupby(o.index.year):
        rows.append({"年": y, "樣本": len(g), "上漲比例": f"{g['y'].mean():.0%}",
                     "準確率": f"{((g[k] > 0.5).astype(int) == g['y']).mean():.1%}",
                     "AUC": f"{roc_auc_score(g['y'], g[k]):.3f}" if g["y"].nunique() > 1 else "—"})
    return pd.DataFrame(rows)


def buckets(o: pd.DataFrame, ret: pd.Series, k: str) -> pd.DataFrame:
    """依預測機率分組，看實際平均報酬——有用的模型應該「機率越高、報酬越高」"""
    g = o.assign(ret=ret.reindex(o.index), b=pd.cut(o[k], [0, 0.4, 0.45, 0.5, 0.55, 0.6, 1.0]))
    t = g.groupby("b", observed=True).agg(天數=("ret", "size"), 實際上漲比例=("y", "mean"), 平均報酬=("ret", "mean"))
    t["實際上漲比例"] = t["實際上漲比例"].map(lambda x: f"{x:.0%}")
    t["平均報酬"] = t["平均報酬"].map(lambda x: f"{x:+.2%}")
    t.index = t.index.astype(str)
    return t


def timing_sim(o: pd.DataFrame, r1: pd.Series, k: str) -> pd.DataFrame:
    """每天開盤前：預測漲就持有加權指數（昨收→今收），否則空手；對照一直持有。未計成本。"""
    r = r1.reindex(o.index).fillna(0)
    hold = (o[k] > 0.5).astype(float)
    rows = []
    for name, daily in [("每天開盤買收盤賣", r), ("模型擇時", r * hold)]:
        eq = (1 + daily).cumprod()
        mdd = (eq / eq.cummax() - 1).min()
        yrs = len(daily) / 245
        rows.append({"方式": name, "總報酬": f"{eq.iloc[-1] - 1:+.0%}",
                     "年化": f"{eq.iloc[-1] ** (1 / yrs) - 1:+.1%}", "最大回撤": f"{mdd:.1%}",
                     "持有天數比例": f"{(daily != 0).mean():.0%}" if name == "模型擇時" else "100%"})
    return pd.DataFrame(rows)


def importance(df: pd.DataFrame, target: str) -> pd.DataFrame:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    feats = [c for c in df.columns if not c.startswith(("y_", "r_"))]
    d = df.dropna(subset=feats + [target])
    lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000)).fit(d[feats], d[target])
    coef = pd.Series(lr[-1].coef_[0], index=feats)
    t = coef.reindex(coef.abs().sort_values(ascending=False).index).head(10)
    return pd.DataFrame({"特徵": t.index, "係數（標準化）": t.round(3).values,
                         "方向": ["越大越容易漲" if v > 0 else "越大越容易跌" for v in t.values]})


def main():
    df = build()
    print(f"# 大盤方向預測（{datetime.now():%Y-%m-%d}）\n")
    print(f"資料 {df.index.min():%Y-%m-%d} ～ {df.index.max():%Y-%m-%d}，"
          f"{len(df)} 個交易日；測試期 2020～2026（逐年 walk-forward）\n")
    oos = {}
    for target, title in [("y_gap", "今天開盤跳空方向（參考，無法交易）"), ("y_oc", "今天開盤→收盤漲跌"),
                          ("y_d5", "今天開盤→5 日後收盤漲跌")]:
        o = walk_forward(df, target)
        oos[target] = o
        print(f"## {title}（{target}）\n")
        print(pd.DataFrame([score(o)]).T.rename(columns={0: "結果"}).to_markdown())
        print()
        print("逐年（梯度提升樹）\n")
        print(by_year(o, "p_gb").to_markdown(index=False))
        print()
        ret = df["r_" + target[2:]]
        print("依預測機率分組（梯度提升樹）\n")
        print(buckets(o, ret, "p_gb").to_markdown())
        print()
        print("影響最大的特徵（邏輯迴歸，全期間）\n")
        print(importance(df, target).to_markdown(index=False))
        print()
    print("## 擇時模擬：預測「開盤→收盤」會漲才在開盤買、收盤賣（未計成本）\n")
    print("對照組「每天開盤買收盤賣」＝只賺盤中，不含隔夜跳空\n")
    for k, name in [("p_lr", "邏輯迴歸"), ("p_gb", "梯度提升樹")]:
        print(f"### {name}\n")
        print(timing_sim(oos["y_oc"], df["r_oc"], k).to_markdown(index=False))
        print()
    pd.concat({k: v for k, v in oos.items()}, axis=1).to_parquet(DATA / "predict_oos.parquet")


if __name__ == "__main__":
    main()
