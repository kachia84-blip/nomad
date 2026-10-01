"""전체 흐름: 수집 → 지표 계산 → 타점 분류 → 뉴스 → 보고서 저장."""
import json
import os
from datetime import datetime

import config
import market
import collector, indicators, screener, news, report, trade_plan, scoring

RESULT_FILE = os.path.join(report.REPORT_DIR, "latest.json")


def _plain(o):
    """numpy 숫자/참거짓 같은 값을 JSON에 쓸 수 있는 일반 값으로 바꾼다."""
    return o.item() if hasattr(o, "item") else str(o)


def run_pipeline(log, progress, manual=None):
    """log(글자), progress(현재, 전체) 콜백으로 진행 상황을 알린다."""
    candidates = collector.collect_candidates(log)
    if manual:  # 사용자가 직접 넣은 종목(SNS 등에서 본 것)을 맨 앞에 추가
        seen = {c["code"] for c in candidates}
        candidates = [m for m in collector.resolve_manual(manual, log) if m["code"] not in seen] + candidates
    if not candidates:  # 수집 실패 시 기존 결과를 덮어쓰지 않도록 중단
        raise RuntimeError("수집된 종목이 0개입니다 (네이버 주소/차단 확인)")
    total = len(candidates)
    picked = []

    # 1단계: 일봉 → 지표 → 타점
    for i, c in enumerate(candidates, 1):
        progress(i, total * 2)
        try:
            df = indicators.add_indicators(collector.fetch_daily(c["code"]))
            base = screener.find_base(df) or screener.find_base_today(df)   # 기준 거래대금이 터진 종목만 후보
            setups = screener.classify(df, base)
            c["volume"] = c["volume"] or float(df.iloc[-1]["volume"])
        except Exception as e:
            log(f"{c['name']} 분석 실패: {e}")
            continue
        if setups:
            last = df.iloc[-1]
            picked.append({**c, "base": base, "setups": setups, "pullback": screener.is_pullback(df, base, setups), "pq": screener.pullback_quality(df, base) if base else None, "chart": indicators.chart_data(df), "plans": trade_plan.make_plans(setups, df), "rsi": float(last["rsi"]),
                           **{f"ma{n}": float(last[f"ma{n}"]) for n in (3, 5, 8, 45)}})
            log(f"✔ {c['name']} → {', '.join(setups)}")

    # 2단계: 타점 종목만 뉴스 검색
    for j, s in enumerate(picked, 1):
        progress(total + int(total * j / max(len(picked), 1)), total * 2)
        r = news.analyze_news(s["name"], log)
        s["news"], s["keywords"] = r["articles"], r["keywords"]
        s["leader_news"] = r["leader"][:3]
        s["leader_hits"] = len(r["leader"])

    market.attach_market(picked, log)       # 업종·테마 시황
    picked = scoring.apply_scores(picked)  # 100점 만점 점수 → 높은 순 정렬
    screened = len(picked)
    picked = picked[: config.STORE_TOP_N]    # 상위 N개만 저장 (화면에는 눌림목/전체 각각 상위 10개를 보여줌)
    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": total,
        "screened_count": screened,
        "prices": {c["name"]: c["price"] for c in candidates},  # 후보 전체의 현재가 (보유 종목 평가용)
        "stocks": picked,
    }
    payload = json.dumps(result, ensure_ascii=False, default=_plain)   # 먼저 문자열로 만들어, 실패해도 기존 파일이 깨지지 않게 한다
    report.save_report(result)
    tmp = RESULT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
    os.replace(tmp, RESULT_FILE)                                          # 한 번에 교체
    progress(1, 1)
    log(f"완료: 타점 종목 {len(picked)}개, 보고서 저장됨")
    return result
