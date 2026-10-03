"""실시간 스캔 - 방금 마감된 4시간봉 기준으로 업비트 원화마켓 코인의 유목민 타점을 찾아 웹페이지(index.html)와 latest.json 으로 저장합니다.
사용법: python scan.py [--out 저장폴더]   (기본 reports)
※ 매매 신호가 아니라 '조건이 갖춰진 후보'입니다. 주문 기능은 없습니다."""
import argparse
import html
import json
import os
import sys
from datetime import datetime, timedelta

import config
import strategy
import upbit

SETUP_POINTS = {"바닥주 224일선 돌파": 16, "갭상승 양봉": 14, "1일차 장대음봉 지지": 14, "거감음봉 지지": 14,
                "거감음봉": 12, "낙주": 12, "이평선 지지": 10, "RSI 추세 전환": 10}
CORE = ("바닥주 224일선 돌파", "갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지")
VERIFIED = "바닥주 224일선 돌파"   # 백테스트 학습·검증 두 기간 모두 성과가 좋았던 타점
MAX_SCORE = 90   # 재료(뉴스) 항목은 아직 연동하지 않아 90점 만점


def score(s, btc, rank):
    """90점 만점. 거래량(30점)이 가장 큰 비중: 기준봉 거래대금 배수(15) + 24시간 거래대금 순위(8) + 눌림 때 거래량 마름(7).
    백테스트에서 기준봉이 평소의 6~20배일 때 성과가 가장 좋았고 20배 이상(꼭대기 급등)은 오히려 나빴습니다."""
    plans = s["plans"]
    rr = max(p["rr"] for p in plans.values())
    risk = min(p["risk_pct"] for p in plans.values())
    mult = s["base"]["mult"] if s["base"] else 0
    vm = 15 if 10 <= mult < 20 else 12 if 6 <= mult < 10 else 8 if mult >= 20 else 4
    vr = s["vol_ratio"]
    parts = {
        "거래량": vm + (8 if rank <= 5 else 6 if rank <= 15 else 4 if rank <= 30 else 2) + (7 if vr <= 0.3 else 4 if vr <= 0.6 else 0),
        "타점": min(25, sum(SETUP_POINTS.get(k, 8) for k in s["setups"])),
        "손익비": round(max(0.0, min(rr / 3, 1)) * 15, 1),
        "손절폭": round(max(0.0, min((10 - risk) / 7, 1)) * 10, 1),
        "시황": (5 if btc["above45"] else 0) + (5 if btc["aligned"] else 0),
    }
    raw = sum(parts.values())
    has_core = any(k in CORE for k in s["setups"])
    total = round(raw if has_core else max(0, raw - 15))
    grade = "A" if total >= 68 else "B" if total >= 54 else "C" if total >= 40 else "D"
    return parts, total, grade, has_core


def candle_label(ts):
    return f"{ts:%m/%d %H:%M}~{(ts + timedelta(hours=4)):%H:%M}"


def build(out_dir):
    now = datetime.utcnow() + timedelta(hours=9)
    markets = upbit.top_markets(config.TOP_N_COINS)
    data = {}
    for m, name, v24 in markets:
        try:
            df = strategy.add_indicators(upbit.closed_only(upbit.candles(m, config.HISTORY_CANDLES), now))
        except Exception as e:                      # 한 코인 오류가 전체를 막지 않게
            print(f"건너뜀 {m}: {e}", file=sys.stderr)
            continue
        if len(df) >= 60:
            data[m] = (name, v24, df)
    if "KRW-BTC" not in data:
        raise SystemExit("BTC 데이터를 받지 못했습니다.")
    b = data["KRW-BTC"][2].iloc[-1]
    btc = {"price": float(b["close"]), "above45": bool(b["close"] > b["ma45"]), "aligned": bool(b["ma5"] > b["ma20"]),
           "ma45": float(b["ma45"]), "candle": candle_label(b["date"])}
    ranks = {m: i + 1 for i, (m, _, _) in enumerate(sorted(((m, n, v) for m, (n, v, _) in data.items()), key=lambda x: -x[2]))}

    out = []
    for m, (name, v24, df) in data.items():
        setups, base = strategy.find_setups(df)
        if not setups:
            continue
        t = df.iloc[-1]
        s = {"market": m, "name": name, "price": float(t["close"]), "ma3": float(t["ma3"]), "ma5": float(t["ma5"]),
             "ma8": float(t["ma8"]), "ma45": float(t["ma45"]), "setups": setups, "base": base,
             "plans": strategy.make_plans(setups, df), "v24_eok": round(v24 / 1e8), "rank": ranks[m],
             "candle": candle_label(t["date"]), "vol_ratio": float(t["volume"] / df.iloc[-2]["volume"]) if df.iloc[-2]["volume"] > 0 else 1.0,
             "chart": [round(float(x), 6) for x in df["close"].tail(60)]}
        s["parts"], s["score"], s["grade"], s["core"] = score(s, btc, ranks[m])
        s["verified"] = VERIFIED in setups
        out.append(s)
    out.sort(key=lambda s: (not s["verified"], -s["score"]))

    os.makedirs(out_dir, exist_ok=True)
    result = {"updated": f"{now:%Y-%m-%d %H:%M}", "last_candle": btc["candle"], "btc": btc, "scanned": len(data),
              "max_score": MAX_SCORE, "signals": out}
    with open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(result))
    print(f"스캔 {len(data)}개 코인, 후보 {len(out)}개, 기준 캔들 {btc['candle']}")
    for s in out[:10]:
        print(f"  {s['grade']} {s['score']:>2}점 {s['name']}({s['market']}) {'+'.join(s['setups'])}")
    return result


def spark(vals, w=120, h=32):
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / span * h:.1f}" for i, v in enumerate(vals))
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true"><polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>'


def render(r):
    e = html.escape
    btc = r["btc"]
    state = ("상승 (45선 위" + (", 5선>20선" if btc["aligned"] else "") + ")") if btc["above45"] else "약세 (45선 아래) - 신규 매수 주의"
    cards = []
    for s in r["signals"]:
        best = max(s["plans"].items(), key=lambda kv: kv[1]["rr"])
        rows = "".join(
            f"<tr><td>{e(k)}</td><td>{strategy.fmt(p['entry'])}</td><td>{strategy.fmt(p['stop'])} <small>(-{p['risk_pct']}%)</small></td>"
            f"<td>{strategy.fmt(p['target1'])}</td><td>{strategy.fmt(p['target2'])}</td><td>{p['rr']}</td></tr>"
            for k, p in s["plans"].items())
        why = "".join(f"<li><b>{e(k)}</b> - {e(v)}</li>" for k, v in s["setups"].items())
        base = s["base"]
        btxt = (f"기준 거래대금 봉: {base['value_eok']}억원(평소의 {base['mult']}배), {base['days_ago']}캔들 전 · 직전 봉 대비 거래량 {s['vol_ratio']:.0%}" if base else "")
        parts = " · ".join(f"{k} {v}" for k, v in s["parts"].items())
        cards.append(f"""<article class="card g{s['grade']}"><header><div><h2>{e(s['name'])} <small>{e(s['market'])}</small> <span class="bd {'v' if s['verified'] else 'r'}">{'백테스트 검증' if s['verified'] else '참고'}</span></h2>
<p class="mut">현재가 {strategy.fmt(s['price'])} · 24h 거래대금 {s['v24_eok']:,}억 ({s['rank']}위)</p></div>
<div class="sc"><b>{s['score']}</b><span>/{r['max_score']} {s['grade']}</span></div></header>
<div class="sp">{spark(s['chart'])}</div>
<ul class="why">{why}</ul><p class="mut">{e(btxt)}</p>
<div class="tw"><table><thead><tr><th>타점</th><th>진입</th><th>손절</th><th>1차 목표</th><th>2차 목표</th><th>손익비</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="mut small">점수 구성: {e(parts)}</p></article>""")
    body = "\n".join(cards) or '<p class="empty">지금 조건을 갖춘 코인이 없습니다. 다음 4시간봉이 마감되면 다시 계산합니다.</p>'
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>업비트 유목민 4시간봉</title><style>
:root{{--bg:#f6f7f9;--fg:#15181d;--mut:#667085;--card:#fff;--line:#e4e7ec;--acc:#1b64f2;--A:#12805c;--B:#1b64f2;--C:#b7791f;--D:#98a2b3}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1115;--fg:#e8eaee;--mut:#98a2b3;--card:#181b21;--line:#2a2f38;--acc:#6ea0ff;--A:#3ccf9b;--B:#6ea0ff;--C:#e8b14f;--D:#7b8494}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Malgun Gothic",sans-serif}}
main{{max-width:880px;margin:0 auto;padding:20px 16px 60px}}h1{{font-size:20px;margin:0 0 4px}}.mut{{color:var(--mut);margin:2px 0}}.small{{font-size:12px}}
.top{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--D);border-radius:12px;padding:14px 16px;margin:12px 0}}
.gA{{border-left-color:var(--A)}}.gB{{border-left-color:var(--B)}}.gC{{border-left-color:var(--C)}}
header{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}h2{{font-size:17px;margin:0}}h2 small{{color:var(--mut);font-weight:400;font-size:12px}}
.sc{{text-align:right;white-space:nowrap}}.sc b{{font-size:26px}}.sc span{{color:var(--mut);font-size:12px;margin-left:2px}}.sp{{color:var(--acc);margin:6px 0}}
.why{{margin:6px 0;padding-left:18px;font-size:13px}}.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px;min-width:460px}}
th,td{{text-align:right;padding:5px 6px;border-bottom:1px solid var(--line);white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}th{{color:var(--mut);font-weight:500}}
.bd{{font-size:11px;font-weight:600;border-radius:99px;padding:1px 8px;margin-left:4px;vertical-align:middle}}.bd.v{{background:var(--A);color:#fff}}.bd.r{{background:var(--line);color:var(--mut)}}
.empty{{text-align:center;color:var(--mut);padding:40px 0}}footer{{color:var(--mut);font-size:12px;margin-top:24px}}</style></head><body><main>
<h1>업비트 유목민 · 4시간봉</h1>
<p class="mut">갱신 {r['updated']} (KST) · 기준 캔들 {e(btc['candle'])} · 스캔 {r['scanned']}개 코인 · 후보 {len(r['signals'])}개</p>
<div class="top"><b>BTC 시황</b> {strategy.fmt(btc['price'])} · {e(state)}<p class="mut small">4시간봉은 업비트 기준 01·05·09·13·17·21시에 시작하고 4시간 뒤 마감됩니다. 마감된 봉만 사용합니다.</p></div>
{body}
<footer>조건이 얼마나 갖춰졌는지 보는 규칙 기반 점수이며 수익을 예측하지 않습니다. 투자 판단과 주문은 직접 하세요. 재료(뉴스) 항목은 아직 반영하지 않아 90점 만점입니다.
기준봉 거래대금이 평소의 10~20배인 핵심 타점만 표시합니다(백테스트 최적 구간). 그중 '백테스트 검증' 표시는 바닥주 224선 돌파로, 40개 코인·약 10개월 중 48건에서 학습기(PF 2.4)와 검증기(PF 3.4) 모두 성과가 좋았던 타점입니다. 나머지 '참고' 타점은 장세에 따라 본전 수준이었습니다. 과거 성과가 앞으로를 보장하지 않습니다.</footer></main></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(config.BASE_DIR, "reports"))
    build(ap.parse_args().out)
