"""종합 점수 모듈 - 타점 종목을 100점 만점으로 비교합니다.
※ 수익을 예측하는 점수가 아니라 '조건이 얼마나 잘 갖춰졌나'를 보는 규칙 기반 점수입니다.
   배점을 바꾸고 싶으면 아래 숫자만 고치면 됩니다."""

SETUP_POINTS = {"거감음봉": 12, "낙주": 12, "이평선 지지": 10, "RSI 추세 전환": 10}


def score_stock(s):
    """종목 dict → (총점, 항목별 점수 dict)"""
    plans = s["plans"].values()

    # 1) 타점 (30점): 겹치는 타점이 많을수록 신뢰도 상승
    setup = min(30, sum(SETUP_POINTS.get(k, 8) for k in s["setups"]))

    # 2) 손익비 (25점): 1차 목표까지 이익이 손절폭의 3배면 만점
    rr = max(p["rr"] for p in plans)
    reward = round(max(0.0, min(rr / 3, 1)) * 25, 1)

    # 3) 손절 폭 (15점): 손절이 짧을수록 유리 (3% 이하 만점, 10% 이상 0점)
    risk = min(p["risk_pct"] for p in plans)
    safety = round(max(0.0, min((10 - risk) / 7, 1)) * 15, 1)

    # 4) 주도성 (15점): 거래대금 상위 / 거래량 1천만주 / 시간외 4% 각 5점
    lead = min(15, 5 * len(s["sources"]))

    # 5) 재료 (10점): 뉴스 핵심 키워드 하나당 4점
    theme = min(10, 4 * len(s["keywords"]))

    # 6) 추세 위치 (5점): 45일선 위(3점) + 3>5>8일선 정배열(2점)
    trend = (3 if s["price"] >= s["ma45"] else 0) + (2 if s["ma3"] > s["ma5"] > s["ma8"] else 0)

    parts = {"타점": setup, "손익비": reward, "손절폭": safety, "주도성": lead, "재료": theme, "추세": trend}
    return round(sum(parts.values())), parts


def grade(total):
    return "A" if total >= 75 else "B" if total >= 60 else "C" if total >= 45 else "D"


def apply_scores(stocks):
    """모든 종목에 점수를 붙이고 높은 순으로 정렬해서 돌려준다."""
    for s in stocks:
        s["score"], s["score_parts"] = score_stock(s)
        s["grade"] = grade(s["score"])
    return sorted(stocks, key=lambda s: -s["score"])
