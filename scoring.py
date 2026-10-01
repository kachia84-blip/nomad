"""종합 점수 모듈 - 타점 종목을 100점 만점으로 비교하고, 항목마다 점수를 준 이유를 문장으로 남깁니다.
※ 수익을 예측하는 점수가 아니라 '조건이 얼마나 잘 갖춰졌나'를 보는 규칙 기반 점수입니다.
   배점을 바꾸고 싶으면 아래 숫자만 고치면 됩니다."""

CORE_SETUPS = ("갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지")   # 영상에서 소개된 유목민 핵심 매수 타점
NO_CORE_PENALTY = 15                         # 핵심 타점이 없으면 감점
SETUP_POINTS = {"갭상승 양봉": 14, "1일차 장대음봉 지지": 14, "거감음봉 지지": 14, "거감음봉": 12, "낙주": 12, "이평선 지지": 10, "RSI 추세 전환": 10}


def score_detail(s):
    """종목 dict → 항목별 [{name, score, max, reason}] 목록"""
    plans = s["plans"]
    out = []

    # 1) 타점 (30점)
    pts = {k: SETUP_POINTS.get(k, 8) for k in s["setups"]}
    setup = min(30, sum(pts.values()))
    listing = " + ".join(f"{k} {v}점" for k, v in pts.items())
    out.append({"name": "타점", "max": 30, "score": setup,
                "reason": f"{listing} = {sum(pts.values())}점 (최대 30점). 서로 다른 타점이 겹칠수록 신뢰도가 높다고 봅니다."})

    # 2) 손익비 (25점)
    best = max(plans.items(), key=lambda kv: kv[1]["rr"])
    rr = best[1]["rr"]
    reward = round(max(0.0, min(rr / 3, 1)) * 25, 1)
    out.append({"name": "손익비", "max": 25, "score": reward,
                "reason": f"[{best[0]}] 기준 손익비가 {rr}입니다. 3 이상이면 만점이라 {rr}÷3×25 = {reward}점입니다. "
                          f"(1차 목표까지 갈 때 이익이 손절폭의 몇 배인지)"})

    # 3) 손절폭 (15점)
    tight = min(plans.items(), key=lambda kv: kv[1]["risk_pct"])
    risk = tight[1]["risk_pct"]
    safety = round(max(0.0, min((10 - risk) / 7, 1)) * 15, 1)
    out.append({"name": "손절폭", "max": 15, "score": safety,
                "reason": f"[{tight[0]}] 기준 손절폭이 진입가 대비 {risk}%입니다. 3% 이하면 만점, 10% 이상이면 0점이라 {safety}점입니다. "
                          f"손절이 짧을수록 한 번 틀렸을 때 잃는 돈이 작습니다."})

    # 4) 주도성 (15점): 거래대금 상위 등 각 5점(최대 10점) + 기준 거래대금 규모 보너스(최대 5점)
    base = s.get("base")
    bonus = 0 if not base else (2 if base.get("kind") == "150억" else 5 if base["value_eok"] >= 1000 else 3)
    lead = min(10, 5 * len(s["sources"])) + bonus
    btxt = (f" 기준 거래대금({base.get('kind', '500억')} 봉) {base['value_eok']:,}억({base['date']}, {base['days_ago']}일 전)이라 +{bonus}점."
            if base else "")
    out.append({"name": "주도성", "max": 15, "score": lead,
                "reason": f"{', '.join(s['sources'])} → 항목당 5점(최대 10점).{btxt} 시장의 돈이 크게 몰린 종목일수록 주도주일 가능성이 큽니다."})

    # 5) 재료 (10점)
    theme = min(10, 4 * len(s["keywords"]))
    kw = ", ".join(f"#{k}" for k in s["keywords"]) or "없음"
    out.append({"name": "재료", "max": 10, "score": theme,
                "reason": f"뉴스에서 찾은 핵심 키워드: {kw}. 하나당 4점(최대 10점)이라 {theme}점입니다."})

    # 6) 추세 위치 (5점)
    above = s["price"] >= s["ma45"]
    aligned = s["ma3"] > s["ma5"] > s["ma8"]
    trend = (3 if above else 0) + (2 if aligned else 0)
    reason = f"현재가 {s['price']:,.0f}원이 45일선 {s['ma45']:,.0f}원 " + ("위라 +3점. " if above else "아래라 0점. ")
    reason += (f"3일선 {s['ma3']:,.0f} > 5일선 {s['ma5']:,.0f} > 8일선 {s['ma8']:,.0f} 정배열이라 +2점." if aligned
               else "3·5·8일선이 정배열이 아니라 0점.")
    out.append({"name": "추세", "max": 5, "score": trend, "reason": reason})
    return out


def grade(total):
    return "A" if total >= 75 else "B" if total >= 60 else "C" if total >= 45 else "D"


def apply_scores(stocks):
    """모든 종목에 점수를 붙이고 높은 순으로 정렬해서 돌려준다."""
    for s in stocks:
        detail = score_detail(s)
        s["score_detail"] = detail
        s["score_parts"] = {d["name"]: d["score"] for d in detail}
        raw = round(sum(d["score"] for d in detail))
        has_core = any(k in s["setups"] for k in CORE_SETUPS)
        s["score"] = raw if has_core else max(0, raw - NO_CORE_PENALTY)
        s["score_note"] = ("" if has_core else
                           f"항목 합계는 {raw}점이지만, 핵심 타점(갭상승 양봉·1일차 장대음봉 지지·거감음봉 지지)이 없어 {NO_CORE_PENALTY}점을 감점했습니다.")
        s["grade"] = grade(s["score"])
    return sorted(stocks, key=lambda s: -s["score"])
