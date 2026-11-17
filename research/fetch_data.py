"""抓回測用的歷史資料到 research/data/（不進 git）

uv run python research/fetch_data.py
- 股價、三大法人：2015-01-01 起；月營收：2014-01-01 起；加權指數 TAIEX
- 已抓過的檔案跳過（可中斷後重跑）
- 依 FinMind user_info 控制用量，每小時不超過 520 次，留額度給每天的排程
"""

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT.parent / ".env")
except ImportError:
    pass

from universe import load_universe  # noqa: E402

DATA = ROOT / "data"
URL = "https://api.finmindtrade.com/api/v4/data"
H = {"Authorization": f"Bearer {os.environ['FINMIND_TOKEN']}"}
SAFE_LIMIT = 520

DATASETS = [
    ("TaiwanStockPrice", "2015-01-01"),
    ("TaiwanStockInstitutionalInvestorsBuySell", "2015-01-01"),
    ("TaiwanStockMonthRevenue", "2014-01-01"),
]


def used() -> int:
    try:
        return int(requests.get("https://api.web.finmindtrade.com/v2/user_info", headers=H, timeout=20)
                   .json().get("user_count", 0))
    except Exception:
        return 0


def wait_quota():
    while (u := used()) >= SAFE_LIMIT:
        print(f"  用量 {u}/600，等 5 分鐘", flush=True)
        time.sleep(300)


def fetch(dataset: str, sid: str, start: str) -> bool:
    out = DATA / dataset / f"{sid}.parquet"
    if out.exists():
        return False
    wait_quota()
    for attempt in range(3):
        try:
            j = requests.get(URL, headers=H, timeout=60,
                             params={"dataset": dataset, "data_id": sid, "start_date": start}).json()
            if j.get("status") == 402:
                print("  FinMind 額度用完，等 10 分鐘", flush=True)
                time.sleep(600)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(j.get("data", [])).to_parquet(out)
            return True
        except Exception as e:
            print(f"  {dataset} {sid} 失敗：{e}", flush=True)
            time.sleep(10)
    return False


def main():
    from stock_strategies.sheet import read_watchlist
    ids = load_universe([w["stock_id"] for w in read_watchlist()])
    print(f"股票池 {len(ids)} 檔", flush=True)
    fetch("TaiwanStockPrice", "TAIEX", "2015-01-01")
    for dataset, start in DATASETS:
        n = 0
        for i, sid in enumerate(ids, 1):
            n += fetch(dataset, sid, start)
            if i % 25 == 0:
                print(f"{dataset} {i}/{len(ids)}（新抓 {n}）", flush=True)
            time.sleep(0.3)
        print(f"✅ {dataset} 完成（新抓 {n}）", flush=True)
    print("✅ 全部完成", flush=True)


if __name__ == "__main__":
    main()
