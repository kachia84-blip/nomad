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


SETUPS = {
    "거감음봉": gyeo_gam_eum,
    "이평선 지지": ma_support,
    "낙주": nakju,
    "RSI 추세 전환": rsi_reversal,
}


def classify(df):
    """4가지 타점을 모두 검사해 {타점이름: 설명} 형태로 반환."""
    if len(df) < 10:
        return {}
    found = {}
    for name, func in SETUPS.items():
        ok, note = func(df)
        if ok:
            found[name] = note
    return found
