"""백테스트 - 4시간봉 유목민 타점을 과거 데이터에 적용해 성과를 봅니다.
사용법: python backtest.py [코인수=40]
체결 가정(보수적): 신호는 '마감된 캔들'에서 나오고, 매수는 다음 캔들에서만 체결합니다. 한 캔들 안에서 손절과 목표가 모두 닿으면 손절을 먼저 친 것으로 봅니다.
※ 현재 거래대금 상위 코인으로 과거를 돌리므로 '생존 편향'이 있어 실제보다 좋게 나옵니다(상장폐지·급락 코인이 빠져 있음)."""
import os
import sys

import pandas as pd

import config
import research
import strategy
import upbit

CORE = ("바닥주 224일선 돌파", "갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지")
PRIORITY = CORE + ("거감음봉", "낙주", "이평선 지지", "RSI 추세 전환")


_ARR = {}


def simulate(df, i, plan):
    """i번째 캔들에서 나온 신호를 다음 캔들부터 체결·관리(research.sim 과 같은 규칙). 거래 dict 또는 None."""
    key = id(df)
    if key not in _ARR:
        _ARR[key] = {k: df[k].values for k in ("open", "high", "low", "close", "ma5", "ma8", "ma20")}
    res = research.sim(_ARR[key], i, plan, research.FINAL)
    if res is None:
        return None
    ret, hold = res
    return {"entry_time": df["date"].iat[i + 1], "exit_time": df["date"].iat[min(i + hold, len(df) - 1)], "hold": hold, "ret": ret, "half": False}


def run_coin(market, df, btc_up):
    trades, free_at = [], -1
    has_base = df["is_base"].rolling(config.BASE_LOOKBACK + 1).max().fillna(0).values > 0
    for i in range(60, len(df) - 1):
        if i <= free_at or not has_base[i]:
            continue
        sub = df.iloc[: i + 1]
        setups, base = strategy.find_setups(sub)
        if not setups:
            continue
        ab, al = btc_up.get(df["date"].iat[i], (False, False))
        if config.REQUIRE_BTC and not (ab and al):
            continue
        primary = next(s for s in PRIORITY if s in setups)
        plan = strategy.make_plan(primary, sub)
        res = simulate(df, i, plan)
        if res is None:
            continue
        free_at = i + res["hold"]
        trades.append({"market": market, "signal_time": df["date"].iat[i], "setup": primary, "core": primary in CORE,
                       "all_setups": "+".join(setups),
                       "base_eok": base["value_eok"], "vol_ratio": round(float(sub["volume"].iat[-1] / sub["volume"].iat[-2]), 3) if sub["volume"].iat[-2] > 0 else 1.0, "base_mult": round(float(df["vmult"].iat[i - base["days_ago"]]), 1), "risk_pct": plan["risk_pct"], "rr": plan["rr"],
                       "btc_up": bool(ab and al), **res})
    return trades


def stats(g):
    r = g["ret"]
    win, loss = r[r > 0].sum(), -r[r <= 0].sum()
    return pd.Series({"거래수": len(g), "승률%": round((r > 0).mean() * 100, 1), "평균수익%": round(r.mean() * 100, 2),
                      "중앙값%": round(r.median() * 100, 2), "손익비PF": round(win / loss, 2) if loss > 0 else float("inf"),
                      "평균보유(캔들)": round(g["hold"].mean(), 1), "최악%": round(r.min() * 100, 1)})


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    markets = upbit.top_markets(n)
    data = {}
    for m, name, _ in markets:
        df = upbit.candles(m, config.BACKTEST_CANDLES)
        df = strategy.add_indicators(upbit.closed_only(df))
        data[m] = df
        print(f"수집 {m} {name}: {len(df)}캔들", flush=True)
    btc = data.get("KRW-BTC")
    if btc is None:
        btc = strategy.add_indicators(upbit.closed_only(upbit.candles("KRW-BTC", config.BACKTEST_CANDLES)))
    btc_up = {d: (bool(c > m45), bool(m5 > m20)) for d, c, m45, m5, m20 in zip(btc["date"], btc["close"], btc["ma45"], btc["ma5"], btc["ma20"])}

    trades = []
    for m, df in data.items():
        trades += run_coin(m, df, btc_up)
    if not trades:
        print("거래가 없습니다."); return
    t = pd.DataFrame(trades)
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    t.to_csv(os.path.join(config.REPORT_DIR, "backtest_trades.csv"), index=False, encoding="utf-8-sig")
    first, last = t["signal_time"].min(), t["signal_time"].max()
    print(f"\n기간 {first:%Y-%m-%d} ~ {last:%Y-%m-%d}, 코인 {len(data)}개, 수수료 {config.FEE:.2%}+슬리피지 {config.SLIPPAGE:.2%} (매수·매도 각각)\n")
    pd.set_option("display.width", 200)
    print("■ 전체"); print(stats(t).to_frame().T.to_string(index=False))
    print("\n■ 타점별"); print(t.groupby("setup").apply(stats, include_groups=False).to_string())
    print("\n■ 핵심 타점 여부"); print(t.groupby("core").apply(stats, include_groups=False).to_string())
    print("\n■ 신호 시점 BTC 상태(45선 위=상승)"); print(t.groupby("btc_up").apply(stats, include_groups=False).to_string())
    print("\n■ 핵심 타점 + BTC 상승일 때만"); print(stats(t[t["core"] & t["btc_up"]]).to_frame().T.to_string(index=False))
    print("\n■ 기준봉 거래대금 배수별 (최근 7일 중앙값 대비)")
    t["mult_bin"] = pd.cut(t["base_mult"], [0, 6, 10, 20, 1e9], labels=["4~6배", "6~10배", "10~20배", "20배+"])
    print(t.groupby("mult_bin", observed=True).apply(stats, include_groups=False).to_string())
    print("\n■ 기준봉 거래대금 금액별(억원)")
    t["eok_bin"] = pd.cut(t["base_eok"], [0, 5, 20, 50, 1e9], labels=["~5억", "5~20억", "20~50억", "50억+"])
    print(t.groupby("eok_bin", observed=True).apply(stats, include_groups=False).to_string())
    print("\n■ 핵심 타점만, 기준봉 배수별")
    c = t[t["core"]]
    print(c.groupby("mult_bin", observed=True).apply(stats, include_groups=False).to_string())
    t["month"] = t["signal_time"].dt.to_period("M")
    print("\n■ 월별 평균수익%/거래수"); print(t.groupby("month")["ret"].agg(["count", lambda s: round(s.mean() * 100, 2)]).to_string())


if __name__ == "__main__":
    main()
