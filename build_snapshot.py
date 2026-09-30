"""분석을 실행하고 모바일용 스냅샷(snapshot.html)을 새로 만든다.  실행: python build_snapshot.py"""
import json
import re
import sys
from datetime import datetime, timedelta

import pipeline


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

    h = open("templates/index.html", encoding="utf-8").read()
    data = open("reports/latest.json", encoding="utf-8").read()
    style = re.search(r"<style>(.*?)</style>", h, re.S).group(1)
    body = re.search(r"<body>(.*?)<script>", h, re.S).group(1)
    script = re.search(r"<script>(.*?)</script>", h, re.S).group(1)

    # 정적 스냅샷: 입력창/실행 버튼/진행 표시 제거
    body = re.sub(r"<textarea.*?</textarea>\s*", "", body, flags=re.S)
    body = re.sub(r'<button id="run">.*?</button>\s*<a class="btn.*?</a>\s*', "", body, flags=re.S)
    body = body.replace('  <div class="progress" id="prog"><div id="progbar"></div></div>\n  <pre class="log" id="log"></pre>\n', "")
    body = re.sub(r'<div class="sub">.*?</div>', '<div class="sub">재·차·거·시 기반 스크리닝 · 아래는 분석 시점의 스냅샷입니다</div>', body, count=1)

    # 다크모드 토큰을 data-theme 선택에도 적용
    dark = re.search(r"@media \(prefers-color-scheme: dark\) \{\s*:root \{(.*?)\}\s*\}", style, re.S).group(1)
    style = style.replace("@media (prefers-color-scheme: dark) {\n    :root {", '@media (prefers-color-scheme: dark) {\n    :root:not([data-theme="light"]) {')
    style += f'\n  :root[data-theme="dark"] {{{dark}}}\n'

    script = re.sub(r"async function loadResult.*?\n", "async function loadResult() { data = DATA; render(); }\n", script)
    script = script[: script.index("async function poll")] + "loadResult();\n"

    out = f"<title>유목민 주도주 분석</title>\n<style>{style}</style>\n{body}\n<script>const DATA={data};\n{script}</script>"
    open("snapshot.html", "w", encoding="utf-8").write(out)

    # GitHub Pages용: 완전한 HTML 문서로 감싸서 docs/index.html 로도 저장
    import os
    os.makedirs("docs", exist_ok=True)
    page = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex"><meta name="color-scheme" content="light dark"></head>'
            f"<body>{out}</body></html>")
    open("docs/index.html", "w", encoding="utf-8").write(page)
    print("snapshot.html 생성 완료")


if __name__ == "__main__":
    if "--if-needed" in sys.argv and is_fresh():
        print("SKIP: 이번 회차 결과가 이미 있습니다")
        sys.exit(0)
    build(run="--no-run" not in sys.argv)  # --no-run: 새로 수집하지 않고 저장된 결과로만 화면 생성
