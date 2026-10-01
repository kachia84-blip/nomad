"""보고서 모듈 - 분석 결과를 마크다운(.md) 파일로 저장합니다."""
import os
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")


def report_path(date=None):
    date = date or datetime.now().strftime("%Y%m%d")
    return os.path.join(REPORT_DIR, f"유목민_당일_주도주_분석_보고서_{date}.md")


def build_markdown(result):
    """결과 dict → 마크다운 문자열."""
    lines = [f"# 유목민 당일 주도주 분석 보고서 ({result['date']})", "",
             f"- 생성 시각: {result['generated_at']}",
             f"- 후보 종목 {result['candidate_count']}개 중 타점 {result.get('screened_count', len(result['stocks']))}개, 점수 상위 {len(result['stocks'])}개 표시", "",
             "| 순위 | 점수 | 종목명 | 현재가 | 거래량 | 타점 유형 | 연관 뉴스 헤드라인 | 재료 키워드 |",
             "|---:|---:|---|---:|---:|---|---|---|"]
    for rank, s in enumerate(result["stocks"], 1):
        heads = "<br>".join(a["title"].replace("|", "/") for a in s["news"][:3]) or "-"
        lines.append(
            f"| {rank} | {s['score']}점({s['grade']}) | {s['name']} | {s['price']:,.0f} | {s['volume']:,.0f} | {' / '.join(s['setups'])} "
            f"| {heads} | {', '.join(s['keywords']) or '-'} |")
    lines += ["", "## 타점 상세", ""]
    for s in result["stocks"]:
        lines.append(f"### {s['name']} ({s['code']}) {s['rate']:+.2f}%")
        for k, v in s["setups"].items():
            lines.append(f"- **{k}**: {v}")
        for k, p in s["plans"].items():
            lines.append(f"- **[{k}] 매매 계획**: {p['how']}")
            for key, label in (("entry", "매수"), ("stop", "손절"), ("target1", "1차 목표"), ("target2", "2차 목표")):
                lines.append(f"  - {label} 산정 이유: {p['reasons'][key]}")
            lines.append(f"  - 매수 {p['entry']:,.0f} / 손절 {p['stop']:,.0f} (-{p['risk_pct']}%) / 1차 목표 {p['target1']:,.0f} / 2차 목표 {p['target2']:,.0f} / 손익비 {p['rr']}")
        lines.append("- **점수 상세**")
        for d in s["score_detail"]:
            lines.append(f"  - {d['name']} {d['score']}/{d['max']}: {d['reason']}")
        lines.append(f"- 이평선: 3일 {s['ma3']:,.0f} / 5일 {s['ma5']:,.0f} / 8일 {s['ma8']:,.0f} / 45일 {s['ma45']:,.0f} · RSI(14) {s['rsi']:.1f}")
        lines.append("")
    lines.append("> 본 보고서는 참고용 자동 분석이며 투자 판단과 책임은 본인에게 있습니다.")
    return "\n".join(lines)


def save_report(result):
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = report_path(result["date"].replace("-", ""))
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_markdown(result))
    return path
