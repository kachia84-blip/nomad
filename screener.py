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
            "open": float(r["open"]), "close": float(r["close"]), "volume": float(r["volume"])}


def find_base_today(df):
    """오늘 자체가 기준 거래대금 봉인 경우(500억 이상 양봉). 바닥주 224일선 돌파(종가 배팅)에만 쓴다."""
    r = df.iloc[-1]
    v = r["close"] * r["volume"]
    if r["close"] > r["open"] and v >= config.BASE_TRADE_VALUE:
        return {"date": str(r["date"]), "value_eok": int(round(v / 1e8)), "days_ago": 0, "kind": "500억",
                "open": float(r["open"]), "close": float(r["close"]), "volume": float(r["volume"])}
    return None


def bottom_breakout(df, base):
    """[바닥주 224일선 돌파] 224일선 아래에서 오래 눌려 있던 종목이 거래대금을 터뜨리며 224일선을 돌파한 자리.
    영상: 유목민이 특히 좋아하는 자리. 돌파한 종가에서 종가 배팅, 갭으로 돌파하면 높은 확률로 급등, 수익 줄 때 매도."""
    t = df.iloc[-1]
    ma = t["ma224"]
    if len(df) < 230 or ma != ma:
        return False, ""
    prior = df.iloc[-36:-6]                                  # 오늘 기준 6~36일 전
    below = float((prior["close"] < prior["ma224"]).mean())
    above_pct = (t["close"] / ma - 1) * 100
    y = df.iloc[-2]
    gap_through = y["ma224"] == y["ma224"] and y["close"] < y["ma224"] and t["open"] >= ma
    ok = (below >= config.BOTTOM_BELOW_RATIO and 0 < above_pct <= config.BOTTOM_MAX_ABOVE_PCT)
    how = "시가부터 갭으로 돌파" if gap_through else "종가로 돌파"
    return ok, f"224일선 {ma:,.0f}원 아래에서 눌려 있다가(직전 30일 중 {below:.0%}) {how}, 종가는 224일선보다 {above_pct:.1f}% 위"


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


def dry_bear_support(df, base, mas=(3, 5, 8, 15, 20, 45)):
    """[거감음봉 지지] 기준일 이후, 거래량이 마르는 음봉이 3·5·8일선(15·20·45일선)에서 지지받는 자리 = 눌림목.
    거래량이 마른다는 기준(아래 중 하나): 전일 대비 25% 이하 / 최근 5일 상승일 최대 거래량 대비 30% 이하 / 기준일 대비 40% 이하.
    거래량이 터지면서 떨어지는 음봉은 탈출 신호라 제외한다. 15일선 이내에서는 5일선과의 이격이 크지 않아야 한다."""
    t, y = df.iloc[-1], df.iloc[-2]
    ratio = t["volume"] / y["volume"] if y["volume"] > 0 else 1
    vs_base = t["volume"] / base["volume"] if base["volume"] > 0 else 1
    ups = df.iloc[-6:-1]
    ups = ups[ups["close"] > ups["open"]]
    peak = float(ups["volume"].max()) if len(ups) else 0.0
    vs_peak = t["volume"] / peak if peak > 0 else 1
    dry = ratio <= config.VOL_DROP_RATIO or vs_peak <= 0.30 or vs_base <= config.DRY_VS_BASE
    gap5 = (t["close"] / t["ma5"] - 1) * 100 if t["ma5"] == t["ma5"] and t["ma5"] else 0
    sup = [n for n in mas if t[f"ma{n}"] == t[f"ma{n}"]
           and t["low"] <= t[f"ma{n}"] * 1.01 and t["close"] >= t[f"ma{n}"] * 0.98]
    n = sup[0] if sup else 3
    near_ok = n >= 45 or (-config.MA5_BREAK_MAX_PCT <= gap5 <= config.MA5_GAP_MAX_PCT)   # 5일선과 이격이 작고, 크게 깨지 않을 것
    ok = bool(t["close"] < t["open"] and dry and sup and near_ok)
    return ok, (f"음봉, 거래량 전일 대비 {ratio:.0%}·최근 상승일 최대 대비 {vs_peak:.0%}·기준일 대비 {vs_base:.0%}, "
                f"5일선 이격 {gap5:+.1f}%, {n}일선 {t[f'ma{n}']:,.0f}원 지지")


SETUPS = {
    "거감음봉": gyeo_gam_eum,
    "이평선 지지": ma_support,
    "낙주": nakju,
    "RSI 추세 전환": rsi_reversal,
}

PULLBACK = "거감음봉 지지"                       # 눌림목 타점 이름
CHASE = ("갭상승 양봉", "바닥주 224일선 돌파", "1일차 장대음봉 지지")   # 거래량 폭발·돌파 직후 매수하는 추격형


def classify(df, base):
    """타점을 검사해 {타점이름: 설명} 로 반환. 기준 거래대금이 터진 종목(base)만 대상입니다.
    20일선 아래(3% 넘게)에 있는 종목은 45일선 눌림(낙주·거감음봉 지지의 45일선)만 남깁니다.
    base 가 '오늘'(days_ago 0)이면 바닥주 224일선 돌파만 검사합니다(기준일 다음 날부터가 다른 타점의 자리)."""
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
    for name, func in SETUPS.items():
        if name == "거감음봉" and PULLBACK in found:
            continue                                   # 같은 신호를 두 번 세지 않음
        if name != "낙주" and not above20:
            continue
        ok, note = func(df)
        if ok:
            found[name] = note
    return found


def pullback_quality(df, base):
    """눌림목의 완성도 지표. 거래량 감소폭이 클수록, 음봉이 클수록, 5일선 이격이 작을수록, 기준일 1~2일차일수록 좋다."""
    t, y = df.iloc[-1], df.iloc[-2]
    ratio = t["volume"] / y["volume"] if y["volume"] > 0 else 1
    ups = df.iloc[-6:-1]
    ups = ups[ups["close"] > ups["open"]]
    peak = float(ups["volume"].max()) if len(ups) else 0.0
    vs_peak = t["volume"] / peak if peak > 0 else 1
    body = (t["open"] - t["close"]) / t["open"] * 100 if t["open"] else 0
    gap5 = (t["close"] / t["ma5"] - 1) * 100 if t["ma5"] == t["ma5"] and t["ma5"] else 0
    return {"vol_ratio": round(float(min(ratio, vs_peak)), 3), "body_pct": round(float(body), 2),
            "gap5": round(float(gap5), 2), "days_ago": int(base["days_ago"])}


def is_pullback(df, base, setups):
    """눌림목: 기준 거래대금이 최근 PULLBACK_BASE_MAX_DAYS일 안에 터져 상승한 뒤,
    거래량이 마르는 음봉이 지지선에서 받치고, 종가가 기준봉 시가 위에서 눌린 자리."""
    if base is None or PULLBACK not in setups:
        return False
    return bool(1 <= base["days_ago"] <= config.PULLBACK_BASE_MAX_DAYS and df.iloc[-1]["close"] >= base.get("open", 0))
