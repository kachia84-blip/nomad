"""업비트 수집 모듈 - 공개 API만 씁니다(키 불필요, 주문 기능 없음). 캔들은 cache 폴더에 저장해 두고 새 것만 받아 이어붙입니다."""
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

import config

API = "https://api.upbit.com/v1"


def _get(path, params=None):
    for attempt in range(5):
        r = requests.get(f"{API}{path}", params=params, timeout=config.TIMEOUT)
        if r.status_code == 429:
            time.sleep(1 + attempt)
            continue
        r.raise_for_status()
        time.sleep(config.SLEEP)
        return r.json()
    raise RuntimeError(f"업비트 요청 제한(429) 반복: {path}")


def top_markets(n=None):
    """원화마켓 중 24시간 거래대금 상위 코인 [(market, korean_name, value24h)]. 유의종목·스테이블코인 제외."""
    n = n or config.TOP_N_COINS
    info = _get("/market/all", {"isDetails": "true"})
    krw = {m["market"]: m["korean_name"] for m in info
           if m["market"].startswith("KRW-") and m.get("market_event", {}).get("warning") is not True
           and m["market"] not in config.STABLE}
    codes = list(krw)
    rows = []
    for i in range(0, len(codes), 100):
        for t in _get("/ticker", {"markets": ",".join(codes[i:i + 100])}):
            rows.append((t["market"], krw[t["market"]], float(t["acc_trade_price_24h"])))
    rows = [r for r in rows if r[2] >= config.MIN_24H_VALUE]
    rows.sort(key=lambda r: -r[2])
    return rows[:n]


def _page(market, count, to=None):
    p = {"market": market, "count": count}
    if to:
        p["to"] = to
    return _get(f"/candles/minutes/{config.UNIT}", p)


def _to_df(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = pd.DataFrame({
        "date": pd.to_datetime(df["candle_date_time_kst"]),
        "open": df["opening_price"].astype(float), "high": df["high_price"].astype(float),
        "low": df["low_price"].astype(float), "close": df["trade_price"].astype(float),
        "volume": df["candle_acc_trade_volume"].astype(float), "value": df["candle_acc_trade_price"].astype(float),
    })
    return df


def candles(market, count):
    """4시간봉 최근 count개 (오래된 → 최신). 캐시가 있으면 새로 생긴 캔들만 받는다. 마지막 줄은 진행 중인 캔들일 수 있다."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, f"{market}.csv")
    old = pd.read_csv(path, parse_dates=["date"]) if os.path.exists(path) else None
    # 진행 중이던 마지막 캔들은 값이 바뀌므로 캐시에서 버린다
    if old is not None and len(old):
        old = old.iloc[:-1]
    # 캐시가 요청한 개수보다 짧으면(상장 직후 코인 제외) 처음부터 다시 받는다
    if old is not None and len(old) < count - 5:
        old = None
    stop_at = old["date"].max() if old is not None and len(old) else None
    got, to = [], None
    while True:
        need = count - sum(len(g) for g in got)
        rows = _page(market, min(200, need) if stop_at is None else 200, to)
        if not rows:
            break
        df = _to_df(rows).sort_values("date")
        got.insert(0, df)
        oldest = rows[-1]["candle_date_time_utc"]
        to = oldest.replace("T", " ")
        if len(rows) < 200:
            break
        if stop_at is not None and df["date"].min() <= stop_at:
            break
        if stop_at is None and sum(len(g) for g in got) >= count:
            break
    new = pd.concat(got) if got else pd.DataFrame()
    df = pd.concat([old, new]) if old is not None else new
    df = df.drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    df.to_csv(path, index=False)
    return df.tail(count).reset_index(drop=True)


def closed_only(df, now=None):
    """진행 중인 캔들을 버리고 마감된 캔들만 남긴다 (KST 기준 시작시각 + 4시간이 지났을 때만 마감)."""
    now = now or (datetime.utcnow() + timedelta(hours=9))
    end = df["date"] + pd.Timedelta(hours=4)
    return df[end <= pd.Timestamp(now)].reset_index(drop=True)
