"""백테스트 연구 - 신호를 한 번 뽑아 저장(stage1)한 뒤, 필터 조합(stage2)과 청산 규칙(stage3)을 탐색합니다.
기준은 앞 60% 기간(학습)에서만 고르고 뒤 40%(검증)에서 확인합니다. 사용법: python research.py [코인수=80]"""
import itertools
import math
import os
import pickle
import sys

import numpy as np
import pandas as pd

import config
import strategy
import upbit

PRIORITY = ("바닥주 224일선 돌파", "갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지", "거감음봉", "낙주", "이평선 지지", "RSI 추세 전환")
PKL = os.path.join(config.REPORT_DIR, "signals.pkl")


# ── stage 1: 신호 수집 ────────────────────────────
def collect(n):
    config.ALLOWED_SETUPS, config.BASE_MULT, config.BASE_MULT_MAX, config.BASE_MAX_AGE = None, 0.0, 1e9, 999      # 필터는 나중에 사후 적용
    markets = upbit.top_markets(n)
    data = {}
    for m, name, _ in markets:
        df = strategy.add_indicators(upbit.closed_only(upbit.candles(m, config.BACKTEST_CANDLES)))
        data[m] = df
        print(f"수집 {m} {name} {len(df)}", flush=True)
    if "KRW-BTC" not in data:
        data["KRW-BTC"] = strategy.add_indicators(upbit.closed_only(upbit.candles("KRW-BTC", config.BACKTEST_CANDLES)))
    b = data["KRW-BTC"]
    btc = {d: (bool(c > m45), bool(m5 > m20)) for d, c, m45, m5, m20 in zip(b["date"], b["close"], b["ma45"], b["ma5"], b["ma20"])}
    coins, sigs = {}, []
    for m, df in data.items():
        coins[m] = {k: df[k].values for k in ("open", "high", "low", "close", "ma5", "ma8", "ma20")} | {"date": df["date"].values}
        has_base = df["is_base"].rolling(config.BASE_LOOKBACK + 1).max().fillna(0).values > 0
        for i in range(60, len(df) - 1):
            if not has_base[i]:
                continue
            sub = df.iloc[: i + 1]
            setups, base = strategy.find_setups(sub)
            if not setups:
                continue
            ab, al = btc.get(df["date"].iat[i], (False, False))
            sigs.append({"coin": m, "i": i, "time": df["date"].iat[i], "setups": list(setups),
                         "plans": strategy.make_plans(setups, sub), "base_mult": base["mult"], "base_eok": base["value_eok"],
                         "base_days": base["days_ago"], "vol_ratio": float(sub["volume"].iat[-1] / sub["volume"].iat[-2]) if sub["volume"].iat[-2] > 0 else 1.0,
                         "hour": int(df["date"].iat[i].hour), "btc45": ab, "btcal": al,
                         "above20": bool(sub["close"].iat[-1] >= sub["ma20"].iat[-1])})
    print(f"신호 {len(sigs)}건, 코인 {len(coins)}개", flush=True)
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    pickle.dump({"coins": coins, "sigs": sigs}, open(PKL, "wb"))


# ── 청산 시뮬레이션 ───────────────────────────────
DEFAULT = dict(stop_scale=1.0, t1="plan", frac1=0.5, t2="plan", trail=5, hold=42)
FINAL = dict(stop_scale=1.0, t1=config.TARGET_R, frac1=1.0, t2=None, trail=5, hold=config.MAX_HOLD)   # 확정된 청산 규칙


def sim(c, i, plan, p):
    j = i + 1
    n = len(c["close"])
    if j >= n:
        return None
    entry = plan["entry"]
    risk0 = entry - plan["stop"]
    stop = entry - p["stop_scale"] * risk0
    risk = entry - stop
    if p["t1"] == "plan":
        t1 = plan["target1"]
    else:
        t1 = entry + p["t1"] * risk
    t2 = plan["target2"] if p["t2"] == "plan" else (entry + p["t2"] * risk if p["t2"] else None)
    o = c["open"][j]
    if plan["breakout"]:
        if c["high"][j] < entry:
            return None
        fill = max(o, entry)
    else:
        if not (stop < o <= entry * 1.03):
            return None
        fill = o
    cost = fill * (1 + config.SLIPPAGE) * (1 + config.FEE)
    k_ = 1 - config.SLIPPAGE
    k_ *= 1 - config.FEE
    got, left, half = 0.0, 1.0, False
    last = min(j + p["hold"], n - 1)
    ma = c[f"ma{p['trail']}"] if p["trail"] else None
    k = j
    while k <= last:
        o_, h, l, cl = c["open"][k], c["high"][k], c["low"][k], c["close"][k]
        if l <= stop:
            got += left * min(o_, stop) * k_; left = 0; break
        if not half and h >= t1:
            f = p["frac1"]
            got += f * max(o_, t1) * k_; left -= f; half = True
            if left <= 1e-9:
                left = 0; break
        if half and t2 is not None and h >= t2:
            got += left * max(o_, t2) * k_; left = 0; break
        if half and ma is not None and cl < ma[k]:
            got += left * cl * k_; left = 0; break
        k += 1
    if left > 0:
        k = min(k, last)
        got += left * c["close"][k] * k_
    return got / cost - 1, k - j + 1


# ── 평가 ──────────────────────────────────────────
def pf(r):
    r = np.asarray(r)
    w, l = r[r > 0].sum(), -r[r <= 0].sum()
    return float(w / l) if l > 0 else 9.99


def tstat(r):
    r = np.asarray(r)
    return float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))) if len(r) > 2 and r.std() > 0 else 0.0


def pick_trades(S, coins, filt, p, cache=None):
    """필터를 통과한 신호들을 시간순으로 돌며(코인별 보유 중에는 건너뜀) 거래 리스트 [(time, ret)]를 만든다."""
    out, free = [], {}
    for idx, s in S:
        if not filt(s):
            continue
        allowed = [x for x in PRIORITY if x in s["setups"] and filt.allowed(x)]
        if not allowed:
            continue
        if s["i"] <= free.get(s["coin"], -1):
            continue
        setup = allowed[0]
        key = (idx, setup, id(p))
        if cache is not None and key in cache:
            res = cache[key]
        else:
            res = sim(coins[s["coin"]], s["i"], s["plans"][setup], p)
            if cache is not None:
                cache[key] = res
        if res is None:
            continue
        free[s["coin"]] = s["i"] + res[1]
        out.append((s["time"], res[0], setup))
    return out


class Filt:
    def __init__(self, mmin, mmax, sets, btc, dry, maxdays):
        self.mmin, self.mmax, self.sets, self.btc, self.dry, self.maxdays = mmin, mmax, sets, btc, dry, maxdays

    def allowed(self, setup):
        return self.sets is None or setup in self.sets

    def __call__(self, s):
        if not (self.mmin <= s["base_mult"] < self.mmax) or s["base_days"] > self.maxdays:
            return False
        if self.btc == "45" and not s["btc45"]:
            return False
        if self.btc == "45al" and not (s["btc45"] and s["btcal"]):
            return False
        return True

    def label(self):
        return f"배수{self.mmin:g}~{'∞' if self.mmax > 1e8 else format(self.mmax, 'g')} 타점{'전부' if self.sets is None else '+'.join(x[:4] for x in self.sets)} BTC{self.btc or '-'} 기준봉≤{self.maxdays}캔들전"


def summarize(trades, cut):
    a = [r for t, r, _ in trades if t <= cut]
    b = [r for t, r, _ in trades if t > cut]
    return a, b


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 80
    if not os.path.exists(PKL) or "--recollect" in sys.argv:
        collect(n)
    d = pickle.load(open(PKL, "rb"))
    coins, sigs = d["coins"], d["sigs"]
    S = sorted(enumerate(sigs), key=lambda x: (x[1]["time"], x[0]))
    times = sorted(s["time"] for s in sigs)
    cut = times[int(len(times) * 0.60)]
    print(f"신호 {len(sigs)}건 / {len(coins)}코인 / 학습 ~{pd.Timestamp(cut):%Y-%m-%d} 검증 이후\n")
    cache = {}

    # stage 2: 필터 탐색 (기본 청산)
    SETS = {"전부": None, "핵심4": ("바닥주 224일선 돌파", "갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지"),
            "바닥주+눌림": ("바닥주 224일선 돌파", "거감음봉 지지"), "바닥주": ("바닥주 224일선 돌파",),
            "바닥주+눌림+1일차": ("바닥주 224일선 돌파", "거감음봉 지지", "1일차 장대음봉 지지"),
            "눌림만": ("거감음봉 지지",), "바닥주+이평선": ("바닥주 224일선 돌파", "이평선 지지")}
    RANGES = [(3, 1e9), (4, 1e9), (6, 1e9), (8, 1e9), (10, 1e9), (6, 20), (8, 20), (10, 20), (12, 20), (10, 30), (8, 15), (10, 15), (15, 30), (15, 1e9)]
    rows = []
    for (mmin, mmax), (sn, sets), btc, md in itertools.product(RANGES, SETS.items(), (None, "45", "45al"), (15, 6, 3)):
        f = Filt(mmin, mmax, sets, btc, None, md)
        tr = pick_trades(S, coins, f, DEFAULT, cache)
        a, b = summarize(tr, cut)
        if len(a) < 30 or len(b) < 15:
            continue
        ha, hb = a[: len(a) // 2], a[len(a) // 2:]
        rows.append({"label": f.label(), "f": f, "n_tr": len(a), "pf_tr": pf(a), "mean_tr": np.mean(a) * 100, "t_tr": tstat(a),
                     "half_ok": np.mean(ha) > 0 and np.mean(hb) > 0, "n_te": len(b), "pf_te": pf(b), "mean_te": np.mean(b) * 100, "win_te": np.mean(np.array(b) > 0) * 100})
    R = pd.DataFrame(rows)
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80); pd.set_option("display.max_columns", 30)
    cols = ["label", "n_tr", "pf_tr", "mean_tr", "t_tr", "half_ok", "n_te", "pf_te", "mean_te", "win_te"]
    print(f"[stage2] 필터 조합 {len(R)}개 평가. 학습 t값 상위 20 (검증 성과 병기)")
    good = R[R["half_ok"]].sort_values("t_tr", ascending=False)
    print(good[cols].head(20).round(2).to_string(index=False))
    print(f"\n학습 t값과 검증 평균수익의 상관: {R['t_tr'].corr(R['mean_te']):.2f} (양수일수록 학습 성과가 검증에서도 이어짐)")
    R.drop(columns="f").to_csv(os.path.join(config.REPORT_DIR, "research_filters.csv"), index=False, encoding="utf-8-sig")

    # stage 3: 청산 규칙 탐색 (학습 t값 상위 필터 5개)
    top = good.head(5)
    EX = [dict(stop_scale=ss, t1=t1, frac1=f1, t2=t2, trail=tr, hold=h)
          for ss, t1, f1, t2, tr, h in itertools.product((0.7, 1.0, 1.3), ("plan", 1.5, 2.5), (0.3, 0.5, 1.0), ("plan", None), (5, 8, 20), (24, 42, 84))]
    print(f"\n[stage3] 청산 규칙 {len(EX)}개 × 필터 {len(top)}개")
    ex_rows = []
    for _, r in top.iterrows():
        for p in EX:
            tr_ = pick_trades(S, coins, r["f"], p, None)
            a, b = summarize(tr_, cut)
            if len(a) < 30 or len(b) < 15:
                continue
            ex_rows.append({"label": r["label"], **{k: p[k] for k in ("stop_scale", "t1", "frac1", "t2", "trail", "hold")},
                            "n_tr": len(a), "pf_tr": pf(a), "mean_tr": np.mean(a) * 100, "t_tr": tstat(a),
                            "n_te": len(b), "pf_te": pf(b), "mean_te": np.mean(b) * 100, "win_te": np.mean(np.array(b) > 0) * 100})
    E = pd.DataFrame(ex_rows)
    E.to_csv(os.path.join(config.REPORT_DIR, "research_exits.csv"), index=False, encoding="utf-8-sig")
    print(E.sort_values("t_tr", ascending=False).head(15).round(2).to_string(index=False))
    print(f"\n학습 t값과 검증 평균수익의 상관(청산): {E['t_tr'].corr(E['mean_te']):.2f}")


if __name__ == "__main__":
    main()
