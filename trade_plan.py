"""매수·매도 지점 계산 모듈.
타점(setup)마다 '어디서 사고 / 어디서 손절하고 / 어디서 나눠 팔지'를 가격으로 계산합니다.
※ 책의 문장을 그대로 옮긴 것이 아니라, 유목민식 원칙(눌림에서 진입, 손절은 근거선 이탈, 분할 매도)을
   규칙으로 만든 것입니다. 기준을 바꾸고 싶으면 이 파일의 숫자만 고치면 됩니다."""


def tick(price):
    """한국 주식 호가단위로 가격을 맞춘다."""
    for limit, unit in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if price < limit:
            return round(price / unit) * unit
    return round(price / 1000) * 1000


def make_plan(setup, df):
    """한 타점에 대한 매수/손절/목표 계획(dict)을 만든다."""
    t = df.iloc[-1]
    high20 = df.iloc[-21:-1]["high"].max()      # 직전 20일 고점 = 저항선 겸 1차 목표
    low5 = df.iloc[-6:]["low"].min()

    if setup == "거감음봉":
        entry = t["high"]                       # 음봉의 고가를 넘어서면 매수(거래 없이 눌린 뒤 재상승 신호)
        stop = t["low"]                         # 그 음봉 저가를 깨면 시나리오 실패
        how = "다음 날 오늘 음봉의 고가를 돌파할 때 매수 (돌파 못 하면 관망)"
    elif setup == "이평선 지지":
        near = min((n for n in (3, 5, 8)), key=lambda n: abs(t["close"] - t[f"ma{n}"]))
        entry = t["close"]
        stop = t[f"ma{near}"] * 0.97
        how = f"{near}일선 지지 확인 구간(현재가 부근)에서 분할 매수"
    elif setup == "낙주":
        entry = t["ma45"] * 1.01
        stop = t["ma45"] * 0.96
        how = "45일선 터치 구간에서 소액 진입, 반등 확인 시 추가"
    else:  # RSI 추세 전환
        entry = t["high"]
        stop = low5
        how = "다음 날 오늘 고가 돌파 시 매수 (과매도 반등 확인)"

    risk = max(entry - stop, entry * 0.01)
    t1 = high20 if high20 > entry * 1.03 else entry + 1.5 * risk
    t2 = max(entry + 3 * risk, t1 * 1.05)
    return {
        "how": how,
        "entry": tick(entry), "stop": tick(stop),
        "target1": tick(t1), "target2": tick(t2),
        "risk_pct": round(risk / entry * 100, 1),
        "rr": round((t1 - entry) / risk, 2),
        "exit_rule": "1차 목표에서 절반 매도, 나머지는 5일선 종가 이탈 시 정리. 손절가 종가 이탈 시 전량 매도.",
    }


def make_plans(setups, df):
    return {name: make_plan(name, df) for name in setups}
