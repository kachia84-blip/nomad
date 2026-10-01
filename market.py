"""시황 모듈 - 오늘 시장에서 어떤 업종·테마로 돈이 몰렸는지를 네이버 업종/테마 시세로 확인합니다.
영상에서 유목민은 '재료·차트·거래량이 갖춰져도 그날 시장이 관심 갖는 섹터가 아니면 움직이지 않는다'고 했습니다.
여기서는 그것을 '종목이 속한 업종과 테마가 오늘 얼마나 올랐는가'로 객관화합니다."""
from collector import BASE, get_json

THEME_TOP_N = 40        # 오늘 상승률 상위 몇 개 테마까지 구성 종목을 확인할지


def fetch_industries():
    """업종별 등락률과 순위. {업종코드: {name, rate, rise, fall, total, rank, count}}"""
    groups = get_json(f"{BASE}/stocks/industry", {"page": 1, "pageSize": 100})["groups"]
    ranked = sorted(groups, key=lambda g: -float(g["changeRate"]))
    return {str(g["no"]): {"name": g["name"], "rate": float(g["changeRate"]), "rise": g["riseCount"],
                           "fall": g["fallCount"], "total": g["totalCount"], "rank": i, "count": len(ranked)}
            for i, g in enumerate(ranked, 1)}


def fetch_theme_map():
    """상승률 상위 테마의 구성 종목을 받아 {종목코드: 가장 많이 오른 소속 테마} 로 만든다."""
    groups = get_json(f"{BASE}/stocks/theme", {"page": 1, "pageSize": 100})["groups"]
    groups = [g for g in groups if g["totalCount"] >= 3][:THEME_TOP_N]       # 응답이 상승률 높은 순
    mapping = {}
    for g in groups:
        info = {"name": g["name"], "rate": float(g["changeRate"]), "rise": g["riseCount"], "total": g["totalCount"]}
        for st in get_json(f"{BASE}/stocks/theme/{g['no']}", {"page": 1, "pageSize": 100}).get("stocks", []):
            if st["itemCode"] not in mapping or info["rate"] > mapping[st["itemCode"]]["rate"]:
                mapping[st["itemCode"]] = info
    return mapping


def attach_market(stocks, log):
    """각 종목에 s["market"] = {industry, theme} 를 붙인다. 일부가 실패해도 분석은 계속한다."""
    try:
        industries = fetch_industries()
    except Exception as e:
        log(f"업종 시세 수집 실패: {e}")
        industries = {}
    try:
        themes = fetch_theme_map()
        log(f"상위 테마 {THEME_TOP_N}개의 구성 종목 {len(themes)}개 확인")
    except Exception as e:
        log(f"테마 시세 수집 실패: {e}")
        themes = {}
    for s in stocks:
        industry = None
        try:
            code = str(get_json(f"{BASE}/stock/{s['code']}/integration").get("industryCode") or "")
            industry = industries.get(code)
        except Exception as e:
            log(f"  {s['name']} 업종 조회 실패: {e}")
        s["market"] = {"industry": industry, "theme": themes.get(s["code"])}
