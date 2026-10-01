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


def uptrend(t):
    """상승 추세: 현재가가 20일선 위이고 5일선이 20일선 위 (영상: 단기 매매는 20일선 위가 정석)."""
    return t["ma20"] == t["ma20"] and t["close"] >= t["ma20"] and t["ma5"] > t["ma20"]


def find_base(df):
    """[기준 거래대금] 최근 BASE_LOOKBACK일 안에 거래대금 500억 이상 양봉(또는 상승 추세 중 150억 이상 양봉)이 있었는지.
    영상 설명: 500억이 터졌다는 건 거래량과 차트가 완성돼 상승 준비가 끝났다는 뜻. 150억은 상승 추세에서만 의미.
    거래대금은 종가x거래량으로 어림잡는다. 오늘은 제외(기준일 다음 날부터가 매수 자리)."""
    n = len(df)
    value = df["close"] * df["volume"]
    best = None
    for i in range(max(0, n - 1 - config.BASE_LOOKBACK), n - 1):
        r = df.iloc[i]
        if r["close"] <= r["open"]:
            continue
        if value.iloc[i] >= config.BASE_TRADE_VALUE:
            best = (i, "500억")                       # 가장 최근 기준일을 쓴다
        elif value.iloc[i] >= config.BASE_MID_VALUE and uptrend(r):
            if best is None or best[1] == "150억":
                best = (i, "150억")
    if best is None:
        return None
    i, kind = best
    r = df.iloc[i]
    return {"date": str(r["date"]), "value_eok": int(round(value.iloc[i] / 1e8)), "days_ago": n - 1 - i, "kind": kind,
            "close": float(r["close"]), "volume": float(r["volume"])}


def gap_up_candle(df, base):
    """[갭상승 양봉] 기준일 이후, 시가가 갭으로 뜨고 양봉으로 마감하며 기준일 종가를 지키는 캔들.
    영상: 갭은 크든 작든 좋고, 윗꼬리가 길수록 좋다. 종가가 전일 종가 이상이면 더 좋다. 갭이 약하면 대응하지 않는다."""
    t, y = df.iloc[-1], df.iloc[-2]
    gap = (t["open"] / y["close"] - 1) * 100 if y["close"] else 0
    rng = t["high"] - t["low"]
    wick = (t["high"] - max(t["open"], t["close"])) / rng if rng > 0 else 0
    ok = (gap >= config.GAP_MIN_PCT and t["close"] > t["open"]
          and t["close"] > base["close"] and wick >= config.WICK_MIN)
    day = "기준일 다음 날(1일차) " if base["days_ago"] == 1 else ""
    return ok, f"{day}시가 갭 +{gap:.1f}%, 양봉 마감, 기준일 종가 {base['close']:,.0f}원 위 유지, 윗꼬리 {wick:.0%}"


def first_day_big_bear(df, base):
    """[1일차 장대 음봉] 기준 거래대금 바로 다음 날 장대 음봉이 나와도, 종가가 전일 종가·전일 고가·3일선 중
    하나를 지키면 강한 매수 자리. 이때는 거래량이 늘어도 감점 요인이 아니다."""
    if base["days_ago"] != 1:
        return False, ""
    t, y = df.iloc[-1], df.iloc[-2]
    body = (t["open"] - t["close"]) / t["open"] * 100 if t["open"] else 0
    held = []
    if t["close"] >= y["close"]:
        held.append("전일 종가")
    if t["close"] >= y["high"]:
        held.append("전일 고가")
    if t["ma3"] == t["ma3"] and t["close"] >= t["ma3"]:
        held.append("3일선")
    ok = bool(t["close"] < t["open"] and body >= config.BIG_BEAR_BODY_PCT and held)
    return ok, f"기준일 다음 날 장대 음봉(몸통 {body:.1f}%)이지만 종가가 {'·'.join(held) or '지지선'}을 지킴 (거래량 증가는 무방)"


def dry_bear_support(df, base):
    """[거감음봉 지지] 기준일 이후, 거래량이 마르는 음봉이 3일선(첫 조정) → 8일선 → 15·20일선에서 지지받는 자리.
    영상의 거래량 법칙: 전일 대비 25% 이하로 급감한 음봉이며, 5일선과 이격이 크지 않아야 한다."""
    t, y = df.iloc[-1], df.iloc[-2]
    ratio = t["volume"] / y["volume"] if y["volume"] > 0 else 1
    vs_base = t["volume"] / base["volume"] if base["volume"] > 0 else 1
    dry = ratio <= config.VOL_DROP_RATIO or vs_base <= config.DRY_VS_BASE
    gap5 = (t["close"] / t["ma5"] - 1) * 100 if t["ma5"] == t["ma5"] and t["ma5"] else 0
    sup = [n for n in (3, 8, 15, 20) if t[f"ma{n}"] == t[f"ma{n}"]
           and t["low"] <= t[f"ma{n}"] * 1.01 and t["close"] >= t[f"ma{n}"] * 0.98]
    ok = bool(t["close"] < t["open"] and dry and sup and abs(gap5) <= config.MA5_GAP_MAX_PCT)
    n = sup[0] if sup else 3
    return ok, f"음봉, 거래량 전일 대비 {ratio:.0%}·기준일 대비 {vs_base:.0%}, 5일선 이격 {gap5:+.1f}%, {n}일선 {t[f'ma{n}']:,.0f}원 지지"


SETUPS = {
    "거감음봉": gyeo_gam_eum,
    "이평선 지지": ma_support,
    "낙주": nakju,
    "RSI 추세 전환": rsi_reversal,
}


def classify(df, base):
    """타점을 검사해 {타점이름: 설명} 로 반환. 기준 거래대금이 터진 종목(base)만 대상입니다.
    20일선 아래(3% 넘게)에 있는 종목은 낙주(45일선 눌림)를 빼고 제외합니다."""
    if len(df) < 20 or base is None:
        return {}
    t = df.iloc[-1]
    above20 = t["ma20"] != t["ma20"] or t["close"] >= t["ma20"] * 0.97
    found = {}
    if above20:
        for name, func in (("갭상승 양봉", gap_up_candle), ("1일차 장대음봉 지지", first_day_big_bear), ("거감음봉 지지", dry_bear_support)):
            ok, note = func(df, base)
            if ok:
                found[name] = note
    for name, func in SETUPS.items():
        if name == "거감음봉" and "거감음봉 지지" in found:
            continue                                   # 같은 신호를 두 번 세지 않음
        if name != "낙주" and not above20:
            continue
        ok, note = func(df)
        if ok:
            found[name] = note
    return found
