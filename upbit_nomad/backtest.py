"""백테스트 - 4시간봉 유목민 타점을 과거 데이터에 적용해 성과를 봅니다.
사용법: python backtest.py [코인수=40]
체결 가정(보수적): 신호는 '마감된 캔들'에서 나오고, 매수는 다음 캔들에서만 체결합니다. 한 캔들 안에서 손절과 목표가 모두 닿으면 손절을 먼저 친 것으로 봅니다.
※ 현재 거래대금 상위 코인으로 과거를 돌리므로 '생존 편향'이 있어 실제보다 좋게 나옵니다(상장폐지·급락 코인이 빠져 있음)."""
import os
import sys

import pandas as pd

import config
import strategy
import upbit

CORE = ("바닥주 224일선 돌파", "갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지")
PRIORITY = CORE + ("거감음봉", "낙주", "이평선 지지", "RSI 추세 전환")


def simulate(df, i, plan):
    """i번째 캔들에서 나온 신호를 다음 캔들부터 체결·관리. 거래 dict 또는 None."""
    j = i + 1
    if j >= len(df):
        return None
    entry, stop, t1, t2 = plan["entry"], plan["stop"], plan["target1"], plan["target2"]
    o = df["open"].iat[j]
    if plan["breakout"]:
        if df["high"].iat[j] < entry:
            return None
        fill = max(o, entry)
    else:
        if not (stop < o <= entry * 1.03):
            return None
        fill = o
    cost = fill * (1 + config.SLIPPAGE) * (1 + config.FEE)
    got, left, half = 0.0, 1.0, False

    def sell(frac, price):
        return frac * price * (1 - config.SLIPPAGE) * (1 - config.FEE)

    last = min(j + config.MAX_HOLD, len(df) - 1)
    k = j
    while k <= last:
        o_, h, l, c = (df[x].iat[k] for x in ("open", "high", "low", "close"))
        if l <= stop:
            got += sell(left, min(o_, stop)); left = 0; break
        if not half and h >= t1:
            got += sell(0.5, max(o_, t1)); left -= 0.5; half = True
        if half and h >= t2:
            got += sell(left, max(o_, t2)); left = 0; break
        if half and c < df["ma5"].iat[k]:
            got += sell(left, c); left = 0; break
        k += 1
    if left > 0:
        k = min(k, last)
        got += sell(left, df["close"].iat[k])
    return {"entry_time": df["date"].iat[j], "exit_time": df["date"].iat[k], "hold": k - j + 1,
            "ret": got / cost - 1, "half": half}


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
        primary = next(s for s in PRIORITY if s in setups)
        plan = strategy.make_plan(primary, sub)
        res = simulate(df, i, plan)
        if res is None:
            continue
        free_at = i + res["hold"]
        trades.append({"market": market, "signal_time": df["date"].iat[i], "setup": primary, "core": primary in CORE,
                       "all_setups": "+".join(setups), "risk_pct": plan["risk_pct"], "rr": plan["rr"],
                       "btc_up": bool(btc_up.get(df["date"].iat[i], False)), **res})
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
    btc_up = dict(zip(btc["date"], (btc["close"] > btc["ma45"]).values))

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
    t["month"] = t["signal_time"].dt.to_period("M")
    print("\n■ 월별 평균수익%/거래수"); print(t.groupby("month")["ret"].agg(["count", lambda s: round(s.mean() * 100, 2)]).to_string())


if __name__ == "__main__":
    main()
