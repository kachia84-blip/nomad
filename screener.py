"""유목민 전략 필터 모듈 - 4가지 타점을 판별합니다.
각 함수는 (해당 여부, 설명) 을 돌려줍니다. df는 오래된 날짜 → 최신 순서, 마지막 줄이 '오늘'입니다."""
import config


def gyeo_gam_eum(df):
    """[거감음봉] 오늘 음봉 + 거래량이 전일의 25% 이하."""
    t, y = df.iloc[-1], df.iloc[-2]
    if y["volume"] <= 0:
        return False, ""
    ratio = t["volume"] / y["volume"]
    ok = t["close"] < t["open"] and ratio <= config.VOL_DROP_RATIO
    return ok, f"음봉, 거래량 전일 대비 {ratio:.0%}"


def ma_support(df):
    """[이평선 지지] 3/5/8일선 ±1% 이내 접촉, 또는 5일선 아래→위 첫 돌파."""
    t, y = df.iloc[-1], df.iloc[-2]
    notes = []
    for n in (3, 5, 8):
        ma = t[f"ma{n}"]
        if ma == ma and abs(t["close"] - ma) / ma * 100 <= config.MA_TOUCH_PCT:  # ma==ma: NaN 방지
            notes.append(f"{n}일선 접촉")
    # 5일선 첫 돌파: 오늘 종가가 5일선 위, 어제는 아래, 그 전 며칠도 계속 아래였을 것
    if y["ma5"] == y["ma5"] and t["close"] > t["ma5"] and y["close"] < y["ma5"]:
        notes.append("5일선 상향 돌파")
    return bool(notes), ", ".join(notes)


def nakju(df):
    """[낙주] 급등 후 조정 중 처음으로 45일선 터치."""
    if len(df) < 55 or df.iloc[-1]["ma45"] != df.iloc[-1]["ma45"]:
        return False, ""
    t = df.iloc[-1]
    touched_now = t["low"] <= t["ma45"] * 1.01 and t["close"] >= t["ma45"] * 0.97
    recent = df.iloc[-11:-1]  # 직전 10일
    touched_before = ((recent["low"] <= recent["ma45"] * 1.01)).any()
    surge = (df.iloc[-30:]["high"].max() / t["ma45"] - 1) * 100
    ok = touched_now and not touched_before and surge >= config.NAKJU_SURGE_PCT
    return ok, f"최근 고점이 45일선 대비 +{surge:.0f}% → 첫 터치"


def rsi_reversal(df):
    """[RSI 추세 전환] 최근 5일 내 RSI 30 이하 기록 후 오늘 반등."""
    if len(df) < 20:
        return False, ""
    r = df["rsi"]
    was_low = r.iloc[-6:-1].min() <= config.RSI_OVERSOLD or r.iloc[-1] <= config.RSI_OVERSOLD
    ok = bool(was_low and r.iloc[-1] > r.iloc[-2])
    return ok, f"RSI {r.iloc[-2]:.1f} → {r.iloc[-1]:.1f}"


def find_base(df):
    """[기준 거래대금] 최근 BASE_LOOKBACK일 안에 일봉 거래대금 500억 이상 양봉이 있었는지 찾는다.
    (영상에서 소개된 유목민 기준: 큰 거래대금이 터진 날 = 거래량과 차트가 완성돼 상승 준비가 끝난 날)
    거래대금은 종가×거래량으로 어림잡는다. 오늘은 제외(기준일 다음 날부터가 매수 자리)."""
    n = len(df)
    value = df["close"] * df["volume"]
    best = None
    for i in range(max(0, n - 1 - config.BASE_LOOKBACK), n - 1):
        r = df.iloc[i]
        if r["close"] > r["open"] and value.iloc[i] >= config.BASE_TRADE_VALUE:
            best = i                                   # 가장 최근 기준일을 쓴다
    if best is None:
        return None
    r = df.iloc[best]
    return {"date": str(r["date"]), "value_eok": int(round(value.iloc[best] / 1e8)), "days_ago": n - 1 - best,
            "close": float(r["close"]), "volume": float(r["volume"])}


def gap_up_candle(df, base):
    """[갭상승 양봉] 기준일 이후, 시가가 전일 종가보다 갭으로 높고 양봉으로 마감하며
    기준일 종가를 지켜주는 캔들. 윗꼬리가 길수록 좋다고 봅니다."""
    t, y = df.iloc[-1], df.iloc[-2]
    gap = (t["open"] / y["close"] - 1) * 100 if y["close"] else 0
    rng = t["high"] - t["low"]
    wick = (t["high"] - max(t["open"], t["close"])) / rng if rng > 0 else 0
    ok = (gap >= config.GAP_MIN_PCT and t["close"] > t["open"]
          and t["close"] > base["close"] and wick >= config.WICK_MIN)
    return ok, f"시가 갭 +{gap:.1f}%, 양봉 마감, 기준일 종가 {base['close']:,.0f}원 위 유지, 윗꼬리 {wick:.0%}"


def dry_bear_support(df, base):
    """[거감음봉 지지] 기준일 이후, 거래량이 마르는 음봉이 3일선 또는 8일선에서 지지받는 자리."""
    t, y = df.iloc[-1], df.iloc[-2]
    ratio = t["volume"] / y["volume"] if y["volume"] > 0 else 1
    vs_base = t["volume"] / base["volume"] if base["volume"] > 0 else 1
    dry = ratio <= config.VOL_DROP_RATIO or vs_base <= config.DRY_VS_BASE
    sup = [n for n in (3, 8) if t[f"ma{n}"] == t[f"ma{n}"]
           and t["low"] <= t[f"ma{n}"] * 1.01 and t["close"] >= t[f"ma{n}"] * 0.98]
    ok = bool(t["close"] < t["open"] and dry and sup)
    n = sup[0] if sup else 3
    return ok, f"음봉, 거래량 전일 대비 {ratio:.0%}·기준일 대비 {vs_base:.0%}, {n}일선 {t[f'ma{n}']:,.0f}원 지지"


SETUPS = {
    "거감음봉": gyeo_gam_eum,
    "이평선 지지": ma_support,
    "낙주": nakju,
    "RSI 추세 전환": rsi_reversal,
}


def classify(df, base):
    """타점을 검사해 {타점이름: 설명} 로 반환. 기준 거래대금이 터진 종목(base)만 대상입니다."""
    if len(df) < 10 or base is None:
        return {}
    found = {}
    ok, note = gap_up_candle(df, base)
    if ok:
        found["갭상승 양봉"] = note
    ok, note = dry_bear_support(df, base)
    if ok:
        found["거감음봉 지지"] = note
    for name, func in SETUPS.items():
        if name == "거감음봉" and "거감음봉 지지" in found:
            continue                                   # 같은 신호를 두 번 세지 않음
        ok, note = func(df)
        if ok:
            found[name] = note
    return found
