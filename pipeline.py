"""전체 흐름: 수집 → 지표 계산 → 타점 분류 → 뉴스 → 보고서 저장."""
import json
import os
from datetime import datetime

import config
import collector, indicators, screener, news, report, trade_plan, scoring

RESULT_FILE = os.path.join(report.REPORT_DIR, "latest.json")


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
            setups = screener.classify(df)
            c["volume"] = c["volume"] or float(df.iloc[-1]["volume"])
        except Exception as e:
            log(f"{c['name']} 분석 실패: {e}")
            continue
        if setups:
            last = df.iloc[-1]
            picked.append({**c, "setups": setups, "plans": trade_plan.make_plans(setups, df), "rsi": float(last["rsi"]),
                           **{f"ma{n}": float(last[f"ma{n}"]) for n in (3, 5, 8, 45)}})
            log(f"✔ {c['name']} → {', '.join(setups)}")

    # 2단계: 타점 종목만 뉴스 검색
    for j, s in enumerate(picked, 1):
        progress(total + int(total * j / max(len(picked), 1)), total * 2)
        r = news.analyze_news(s["name"], log)
        s["news"], s["keywords"] = r["articles"], r["keywords"]

    picked = scoring.apply_scores(picked)  # 100점 만점 점수 → 높은 순 정렬
    screened = len(picked)
    picked = picked[: config.SHOW_TOP_N]    # 상위 N개만 남김
    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": total,
        "screened_count": screened,
        "stocks": picked,
    }
    report.save_report(result)
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    progress(1, 1)
    log(f"완료: 타점 종목 {len(picked)}개, 보고서 저장됨")
    return result
