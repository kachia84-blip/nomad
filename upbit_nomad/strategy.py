"""유목민 전략 4시간봉 버전 - 지표, 타점 판별, 매수·손절·목표 계획.
df는 오래된 → 최신 순서이고 마지막 줄이 '방금 마감된 4시간봉'입니다. (일·일선은 모두 캔들·선으로 바뀜: 5일선 = 4시간봉 5개 평균)"""
import numpy as np

import config


# ── 지표 ──────────────────────────────────────────
def add_indicators(df):
    df = df.copy()
    for n in (3, 5, 8, 15, 20, 45, 60, 224):
        df[f"ma{n}"] = df["close"].rolling(n).mean()
    diff = df["close"].diff()
    gain = diff.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-diff.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    # 거래대금이 터진 봉: 양봉 + 최근 7일 중앙값의 BASE_MULT배 이상 + 절대 최소금액 이상
    vmed = df["value"].rolling(42).median().shift(1)
    df["vmult"] = df["value"] / vmed
    df["is_base"] = ((df["close"] > df["open"]) & (df["value"] >= config.BASE_MIN_VALUE)
                     & (df["value"] >= config.BASE_FIND_MULT * vmed)).fillna(False)
    return df


def tick(price):
    """업비트 원화마켓 호가단위로 가격을 맞춘다."""
    for limit, unit in ((0.1, 0.00001), (1, 0.0001), (10, 0.001), (100, 0.01), (1000, 0.1), (10000, 1), (100000, 10),
                        (500000, 100), (1000000, 500), (2000000, 1000)):
        if price < limit:
            return round(round(price / unit) * unit, 8)
    return float(round(price / 1000) * 1000)


def fmt(price):
    p = tick(price)
    return f"{p:,.0f}원" if p >= 100 else f"{p:,.4g}원"


# ── 기준 거래대금(거) ─────────────────────────────
def _base_info(df, i):
    r = df.iloc[i]
    n = len(df)
    return {"date": str(r["date"]), "value_eok": round(float(r["value"]) / 1e8, 1), "days_ago": n - 1 - i, "mult": round(float(r["vmult"]), 1),
            "open": float(r["open"]), "close": float(r["close"]), "volume": float(r["volume"])}


def find_base(df):
    """최근 BASE_LOOKBACK 캔들 안에서 가장 최근에 터진 기준봉(오늘 제외). 기준봉 다음 캔들부터가 매수 자리."""
    n = len(df)
    isb = df["is_base"].values
    for i in range(n - 2, max(-1, n - 2 - config.BASE_LOOKBACK), -1):
        if isb[i]:
            return _base_info(df, i)
    return None


def find_base_today(df):
    return _base_info(df, len(df) - 1) if df["is_base"].values[-1] else None


# ── 타점(차) ──────────────────────────────────────
def gyeo_gam_eum(df):
    t, y = df.iloc[-1], df.iloc[-2]
    if y["volume"] <= 0:
        return False, ""
    ratio = t["volume"] / y["volume"]
    return bool(t["close"] < t["open"] and ratio <= config.VOL_DROP_RATIO), f"음봉, 거래량 직전봉 대비 {ratio:.0%}"


def ma_support(df):
    t, y = df.iloc[-1], df.iloc[-2]
    notes = []
    for n in (3, 5, 8):
        ma = t[f"ma{n}"]
        if ma == ma and abs(t["close"] - ma) / ma * 100 <= config.MA_TOUCH_PCT:
            notes.append(f"{n}선 접촉")
    if y["ma5"] == y["ma5"] and t["close"] > t["ma5"] and y["close"] < y["ma5"]:
        notes.append("5선 상향 돌파")
    return bool(notes), ", ".join(notes)


def nakju(df):
    if len(df) < 55 or df.iloc[-1]["ma45"] != df.iloc[-1]["ma45"]:
        return False, ""
    t = df.iloc[-1]
    touched_now = t["low"] <= t["ma45"] * 1.01 and t["close"] >= t["ma45"] * 0.97
    touched_before = (df.iloc[-11:-1]["low"] <= df.iloc[-11:-1]["ma45"] * 1.01).any()
    surge = (df.iloc[-30:]["high"].max() / t["ma45"] - 1) * 100
    return bool(touched_now and not touched_before and surge >= config.NAKJU_SURGE_PCT), f"최근 고점이 45선 대비 +{surge:.0f}% → 첫 터치"


def rsi_reversal(df):
    if len(df) < 20:
        return False, ""
    r = df["rsi"]
    was_low = r.iloc[-6:-1].min() <= config.RSI_OVERSOLD or r.iloc[-1] <= config.RSI_OVERSOLD
    return bool(was_low and r.iloc[-1] > r.iloc[-2]), f"RSI {r.iloc[-2]:.1f} → {r.iloc[-1]:.1f}"


def bottom_breakout(df, base):
    """[바닥주 224선 돌파] 224선(약 37일) 아래에서 오래 눌려 있다가 거래대금과 함께 돌파."""
    t = df.iloc[-1]
    ma = t["ma224"]
    if len(df) < 230 or ma != ma:
        return False, ""
    prior = df.iloc[-36:-6]
    below = float((prior["close"] < prior["ma224"]).mean())
    above = (t["close"] / ma - 1) * 100
    y = df.iloc[-2]
    gap = y["ma224"] == y["ma224"] and y["close"] < y["ma224"] and t["open"] >= ma
    ok = below >= config.BOTTOM_BELOW_RATIO and 0 < above <= config.BOTTOM_MAX_ABOVE_PCT
    return bool(ok), f"224선 {fmt(ma)} 아래에서 눌려 있다가(직전 30캔들 중 {below:.0%}) {'시가부터 갭으로' if gap else '종가로'} 돌파, 224선보다 {above:.1f}% 위"


def gap_up_candle(df, base):
    t, y = df.iloc[-1], df.iloc[-2]
    gap = (t["open"] / y["close"] - 1) * 100 if y["close"] else 0
    rng = t["high"] - t["low"]
    wick = (t["high"] - max(t["open"], t["close"])) / rng if rng > 0 else 0
    ok = gap >= config.GAP_MIN_PCT and t["close"] > t["open"] and t["close"] > base["close"] and wick >= config.WICK_MIN
    return bool(ok), f"시가 갭 +{gap:.2f}%, 양봉 마감, 기준봉 종가 {fmt(base['close'])} 위 유지, 윗꼬리 {wick:.0%}"


def first_day_big_bear(df, base):
    if base["days_ago"] != 1:
        return False, ""
    t, y = df.iloc[-1], df.iloc[-2]
    body = (t["open"] - t["close"]) / t["open"] * 100 if t["open"] else 0
    held = []
    if t["close"] >= y["close"]:
        held.append("직전 종가")
    if t["close"] >= y["high"]:
        held.append("직전 고가")
    if t["ma3"] == t["ma3"] and t["close"] >= t["ma3"]:
        held.append("3선")
    ok = t["close"] < t["open"] and body >= config.BIG_BEAR_BODY_PCT and held
    return bool(ok), f"기준봉 다음 캔들 장대 음봉(몸통 {body:.1f}%)이지만 종가가 {'·'.join(held) or '지지선'}을 지킴"


def dry_bear_support(df, base, mas=(3, 5, 8, 15, 20, 45)):
    t, y = df.iloc[-1], df.iloc[-2]
    ratio = t["volume"] / y["volume"] if y["volume"] > 0 else 1
    vs_base = t["volume"] / base["volume"] if base["volume"] > 0 else 1
    ups = df.iloc[-6:-1]
    ups = ups[ups["close"] > ups["open"]]
    peak = float(ups["volume"].max()) if len(ups) else 0.0
    vs_peak = t["volume"] / peak if peak > 0 else 1
    dry = ratio <= config.VOL_DROP_RATIO or vs_peak <= 0.30 or vs_base <= config.DRY_VS_BASE
    gap5 = (t["close"] / t["ma5"] - 1) * 100 if t["ma5"] == t["ma5"] and t["ma5"] else 0
    sup = [n for n in mas if t[f"ma{n}"] == t[f"ma{n}"] and t["low"] <= t[f"ma{n}"] * 1.01 and t["close"] >= t[f"ma{n}"] * 0.98]
    n = sup[0] if sup else 3
    near_ok = n >= 45 or (-config.MA5_BREAK_MAX_PCT <= gap5 <= config.MA5_GAP_MAX_PCT)
    ok = t["close"] < t["open"] and dry and sup and near_ok
    return bool(ok), f"음봉, 거래량 직전봉 대비 {ratio:.0%}·기준봉 대비 {vs_base:.0%}, 5선 이격 {gap5:+.1f}%, {n}선 {fmt(t[f'ma{n}'])} 지지"


def _uptrend(t):
    return t["ma20"] == t["ma20"] and t["close"] >= t["ma20"] and t["ma5"] > t["ma20"]


SIMPLE = {"거감음봉": gyeo_gam_eum, "이평선 지지": ma_support, "낙주": nakju, "RSI 추세 전환": rsi_reversal}
PULLBACK = "거감음봉 지지"
CORE = ("바닥주 224일선 돌파", "갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지")


def classify(df, base):
    """base(기준봉)가 있는 종목만 검사. base가 방금 마감된 봉(days_ago 0)이면 바닥주 224선 돌파만 본다."""
    if len(df) < 20 or base is None:
        return {}
    found = {}
    ok, note = bottom_breakout(df, base)
    if ok:
        found["바닥주 224일선 돌파"] = note
    if base["days_ago"] < 1:
        return found
    t = df.iloc[-1]
    above20 = t["ma20"] != t["ma20"] or t["close"] >= t["ma20"] * 0.97
    if above20:
        for name, func in (("갭상승 양봉", gap_up_candle), ("1일차 장대음봉 지지", first_day_big_bear)):
            ok, note = func(df, base)
            if ok:
                found[name] = note
        ok, note = dry_bear_support(df, base)
    else:
        ok, note = dry_bear_support(df, base, mas=(45,))
    if ok:
        found[PULLBACK] = note
    for name, func in SIMPLE.items():
        if name == "거감음봉" and PULLBACK in found:
            continue
        if name != "낙주" and not above20:
            continue
        ok, note = func(df)
        if ok:
            found[name] = note
    return found


def find_setups(df, strict=True):
    """(타점dict, 기준봉) - 방금 마감된 봉이 기준봉인 경우와 이전 기준봉이 있는 경우를 모두 본다.
    strict=False 이면 배수·기준봉 나이·타점 종류 제한을 풀어서 '조건에 얼마나 가까운지' 볼 때 쓴다(관찰용)."""
    def ok(b):
        return not strict or (config.BASE_MULT <= b["mult"] < config.BASE_MULT_MAX and b["days_ago"] <= config.BASE_MAX_AGE)
    found, base = {}, None
    bt = find_base_today(df)
    if bt and not ok(bt):
        bt = None
    if bt:
        found.update(classify(df, bt))
        base = bt
    bp = find_base(df)
    if bp and not ok(bp):
        bp = None                                   # 가장 최근 기준봉이 기준(10배 이상·24시간 이내)을 못 채우면 신호 없음
    if bp:
        for k, v in classify(df, bp).items():
            found.setdefault(k, v)
        base = bp
    if strict and config.ALLOWED_SETUPS is not None:
        found = {k: v for k, v in found.items() if k in config.ALLOWED_SETUPS}
    return found, base


# ── 매수·손절·목표 계획 ───────────────────────────
def make_plan(setup, df):
    t = df.iloc[-1]
    y = df.iloc[-2]
    high_res = df.iloc[-1 - config.RESIST_LOOKBACK:-1]["high"].max()
    low5 = df.iloc[-6:]["low"].min()
    if setup == "갭상승 양봉":
        entry, stop = t["close"], y["close"]
    elif setup == "바닥주 224일선 돌파":
        entry, stop = t["close"], t["ma224"] * 0.97
    elif setup == "1일차 장대음봉 지지":
        entry = t["close"]
        stop = min(y["close"], t["ma3"] if t["ma3"] == t["ma3"] else y["close"]) * 0.98
    elif setup == "거감음봉 지지":
        near = min((3, 8, 15, 20), key=lambda n: abs(t["low"] - t[f"ma{n}"]))
        entry, stop = t["close"], t[f"ma{near}"] * 0.97
    elif setup == "거감음봉":
        entry, stop = t["high"], t["low"]
    elif setup == "이평선 지지":
        near = min((3, 5, 8), key=lambda n: abs(t["close"] - t[f"ma{n}"]))
        entry, stop = t["close"], t[f"ma{near}"] * 0.97
    elif setup == "낙주":
        entry, stop = t["ma45"] * 1.01, t["ma45"] * 0.96
    else:  # RSI 추세 전환
        entry, stop = t["high"], low5
    risk = entry - stop if entry - stop > 0 else entry * 0.01
    t1 = entry + config.TARGET_R * risk
    return {"entry": tick(entry), "stop": tick(stop), "target1": tick(t1), "target2": tick(t1),
            "risk_pct": round(float(risk / entry * 100), 2), "rr": config.TARGET_R,
            "breakout": setup in ("거감음봉", "RSI 추세 전환"),
            "exit_rule": f"목표가(손절폭의 {config.TARGET_R}배) 도달 시 전량 매도, 손절가 이탈 시 전량 매도, 최대 {config.MAX_HOLD}캔들({config.MAX_HOLD // 6}일) 보유 후 정리."}


def make_plans(setups, df):
    return {name: make_plan(name, df) for name in setups}
