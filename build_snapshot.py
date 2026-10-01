"""분석을 실행하고 모바일용 웹페이지(docs/index.html)를 새로 만든다.  실행: python build_snapshot.py
  --if-needed : 이번 회차(20:30 기준) 결과가 이미 있으면 건너뜀
  --no-run    : 새로 수집하지 않고 저장된 결과(reports/latest.json)로 화면만 다시 만듦"""
import json
import os
import sys
from datetime import datetime, timedelta

import pipeline

PLACEHOLDER = "/*__DATA__*/null"


def is_fresh():
    """가장 최근 20:30 이후에 성공한 분석 결과가 이미 있으면 True (그 회차는 끝난 것)."""
    try:
        made = datetime.strptime(json.load(open("reports/latest.json", encoding="utf-8"))["generated_at"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False
    now = datetime.now()
    boundary = now.replace(hour=20, minute=30, second=0, microsecond=0)
    if boundary > now:
        boundary -= timedelta(days=1)
    return made >= boundary


def build(run=True):
    if run:
        pipeline.run_pipeline(print, lambda a, b: None)  # 수집 → 분석 → reports/latest.json 저장

    html = open("templates/index.html", encoding="utf-8").read()
    data = open("reports/latest.json", encoding="utf-8").read().replace("</", "<\\/")
    if PLACEHOLDER not in html:
        raise RuntimeError("templates/index.html 에 데이터 자리표시자가 없습니다")
    os.makedirs("docs", exist_ok=True)
    open("docs/index.html", "w", encoding="utf-8").write(html.replace(PLACEHOLDER, data))
    print("docs/index.html 생성 완료")


if __name__ == "__main__":
    if "--if-needed" in sys.argv and is_fresh():
        print("SKIP: 이번 회차 결과가 이미 있습니다")
        sys.exit(0)
    build(run="--no-run" not in sys.argv)
