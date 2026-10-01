"""매수·매도 지점 계산 모듈.
타점(setup)마다 '어디서 사고 / 어디서 손절하고 / 어디서 나눠 팔지'를 가격으로 계산하고,
그 가격을 왜 그렇게 잡았는지 이유 문장도 함께 만듭니다.
※ 책의 문장을 그대로 옮긴 것이 아니라, 유목민식 원칙(눌림에서 진입, 손절은 근거선 이탈, 분할 매도)을
   규칙으로 만든 것입니다. 기준을 바꾸고 싶으면 이 파일의 숫자만 고치면 됩니다."""


def tick(price):
    """한국 주식 호가단위로 가격을 맞춘다."""
    for limit, unit in ((2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500)):
        if price < limit:
            return float(round(price / unit) * unit)
    return float(round(price / 1000) * 1000)


def won(price):
    return f"{tick(price):,.0f}원"


def make_plan(setup, df):
    """한 타점에 대한 매수/손절/목표 계획(dict)과 각 가격의 산정 이유를 만든다."""
    t = df.iloc[-1]
    high20 = df.iloc[-21:-1]["high"].max()      # 직전 20일 고점 = 저항선 겸 1차 목표
    low5 = df.iloc[-6:]["low"].min()

    y = df.iloc[-2]
    if setup == "갭상승 양봉":
        entry, stop = t["close"], y["close"]
        how = "기준 거래대금 이후 나온 갭상승 양봉의 종가 부근에서 분할 매수 (다음 날 갭이 유지되면 추가)"
        why_entry = (f"기준 거래대금이 터진 뒤 오늘 갭상승 양봉이 종가 {won(entry)}를 지켰습니다. "
                     f"영상에서 소개된 유목민의 매수 자리(종가를 지켜주는 갭상승 양봉)라 종가 부근을 진입가로 잡았습니다.")
        why_stop = f"전일 종가 {won(stop)}입니다. 이 가격까지 내려오면 갭이 메워진 것이라 갭상승 시나리오가 틀린 것으로 봅니다."
    elif setup == "바닥주 224일선 돌파":
        ma = t["ma224"]
        entry, stop = t["close"], ma * 0.97
        how = "224일선을 거래대금과 함께 돌파한 종가 부근 매수(종가 배팅), 다음 날 갭상승 등 수익이 날 때 정리"
        why_entry = (f"224일선 {won(ma)} 아래에서 오래 눌려 있던 종목이 거래대금을 터뜨리며 돌파했습니다. "
                     f"영상에서 소개된 유목민의 선호 자리(상승 추세의 시작점)라 돌파한 종가 {won(entry)} 부근을 진입가로 잡았습니다.")
        why_stop = f"224일선 {won(ma)}의 3% 아래입니다. 돌파 후 다시 224일선 밑으로 밀리면 돌파 실패로 봅니다."
    elif setup == "1일차 장대음봉 지지":
        entry = t["close"]
        stop = min(y["close"], t["ma3"] if t["ma3"] == t["ma3"] else y["close"]) * 0.98
        how = "기준 거래대금 다음 날 장대 음봉이 지지선을 지킨 자리, 종가 부근 매수 (재료와 시황이 살아 있을 때)"
        why_entry = (f"기준 거래대금 다음 날 장대 음봉이 나왔지만 종가 {won(entry)}가 전일 종가·전일 고가·3일선 중 하나를 지켰습니다. "
                     f"영상에서 소개된 강한 매수 기회(거래량이 늘어도 무방)라 종가 부근을 진입가로 잡았습니다.")
        why_stop = f"전일 종가와 3일선 중 낮은 값의 2% 아래인 {won(stop)}입니다. 지지선을 종가로 이탈하면 이 매수 근거가 사라집니다."
    elif setup == "거감음봉 지지":
        near = min((3, 8, 15, 20), key=lambda n: abs(t["low"] - t[f"ma{n}"]))
        ma = t[f"ma{near}"]
        entry, stop = t["close"], ma * 0.97
        how = f"기준 거래대금 이후 거래량이 마른 음봉이 {near}일선에서 지지받는 자리, 현재가 부근에서 분할 매수"
        why_entry = (f"기준 거래대금이 터진 종목이 거래량이 마르며 {near}일선({won(ma)})에서 지지받고 있습니다. "
                     f"영상에서 소개된 두 번째 매수 자리라 현재가 {won(entry)} 부근을 진입가로 잡았습니다.")
        why_stop = f"{near}일선 {won(ma)}의 3% 아래입니다. 이 선을 종가로 이탈하면 지지 실패로 봅니다."
    elif setup == "거감음봉":
        entry, stop = t["high"], t["low"]
        how = "다음 날 오늘 음봉의 고가를 돌파할 때 매수 (돌파 못 하면 관망)"
        why_entry = (f"오늘 음봉의 고가 {won(entry)}를 다시 넘어서면, 거래량이 줄어든 채 눌린 뒤 "
                     f"매수세가 돌아왔다는 신호로 보고 그 가격을 진입가로 잡았습니다.")
        why_stop = f"오늘 음봉의 저가 {won(stop)}를 깨면 '거래 없이 눌렸다'는 시나리오가 틀린 것이라 손절가로 잡았습니다."
    elif setup == "이평선 지지":
        near = min((3, 5, 8), key=lambda n: abs(t["close"] - t[f"ma{n}"]))
        ma = t[f"ma{near}"]
        entry, stop = t["close"], ma * 0.97
        how = f"{near}일선 지지 확인 구간(현재가 부근)에서 분할 매수"
        why_entry = (f"현재가 {won(entry)}가 {near}일선({won(ma)}) 부근이라, 이평선 위에서 지지받는 "
                     f"자리로 보고 현재가 부근을 진입가로 잡았습니다.")
        why_stop = f"{near}일선 {won(ma)}의 3% 아래입니다. 이 선 밑으로 내려가면 지지에 실패한 것으로 봅니다."
    elif setup == "낙주":
        ma45 = t["ma45"]
        entry, stop = ma45 * 1.01, ma45 * 0.96
        how = "45일선 터치 구간에서 소액 진입, 반등 확인 시 추가"
        why_entry = (f"45일선 {won(ma45)}의 1% 위입니다. 급등 후 처음 45일선까지 눌린 자리에서 "
                     f"지지를 확인하는 구간으로 잡았습니다.")
        why_stop = f"45일선 {won(ma45)}의 4% 아래입니다. 잠깐 이탈은 허용하되 그 이상 밀리면 추세가 꺾인 것으로 봅니다."
    else:  # RSI 추세 전환
        entry, stop = t["high"], low5
        how = "다음 날 오늘 고가 돌파 시 매수 (과매도 반등 확인)"
        why_entry = (f"RSI가 과매도(30 이하)를 찍고 올라선 상태에서, 오늘 고가 {won(entry)}를 넘어서면 "
                     f"반등이 이어진다고 보고 진입가로 잡았습니다.")
        why_stop = f"최근 5일 최저가 {won(stop)}입니다. 반등이 시작된 저점이라 깨지면 반등 실패로 봅니다."

    risk = max(entry - stop, entry * 0.01)
    if high20 > entry * 1.03:
        t1 = high20
        why_t1 = f"직전 20일 고점 {won(t1)}이 매물이 몰린 저항선이라 1차 목표로 잡았습니다. 여기서 절반을 정리합니다."
    else:
        t1 = entry + 1.5 * risk
        why_t1 = (f"직전 20일 고점이 진입가보다 3%도 높지 않아 저항선 구실을 못 합니다. 대신 위험폭 "
                  f"{won(risk)}의 1.5배를 더한 {won(t1)}를 1차 목표로 잡았습니다.")
    t2 = max(entry + 3 * risk, t1 * 1.05)
    why_t2 = f"위험폭의 3배({won(entry + 3 * risk)})와 1차 목표+5%({won(t1 * 1.05)}) 중 큰 값입니다. 남은 물량은 추세를 따라갑니다."

    return {
        "how": how,
        "entry": tick(entry), "stop": tick(stop),
        "target1": tick(t1), "target2": tick(t2),
        "risk_pct": round(float(risk / entry * 100), 1),
        "rr": round(float((t1 - entry) / risk), 2),
        "exit_rule": "수익이 날 때 1차 목표에서 절반 먼저 챙기고(길게 끄는 기법이 아님), 나머지는 5일선 종가 이탈 시 정리. 손절가 종가 이탈 시 전량 매도.",
        "reasons": {"entry": why_entry, "stop": why_stop, "target1": why_t1, "target2": why_t2,
                    "rr": f"손익비 = (1차 목표 − 진입가) ÷ (진입가 − 손절가) = {won(t1 - entry)} ÷ {won(risk)}"},
    }


def make_plans(setups, df):
    return {name: make_plan(name, df) for name in setups}
