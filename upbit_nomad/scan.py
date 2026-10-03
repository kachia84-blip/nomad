"""실시간 스캔 - 방금 마감된 4시간봉 기준으로 업비트 원화마켓 코인의 유목민 타점을 찾아 웹페이지(index.html)와 latest.json 으로 저장합니다.
신호(백테스트로 확정한 기준을 모두 채운 코인)는 강조하고, 신호가 없어도 점수 상위 코인을 합쳐 10개까지 '관찰'로 보여줍니다.
사용법: python scan.py [--out 저장폴더] [--if-needed]   (--if-needed: 이미 최신 4시간봉으로 계산돼 있으면 건너뜀)
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
MAX_SCORE = 90   # 재료(뉴스) 항목은 아직 연동하지 않아 90점 만점
SHOW_TOTAL = 10  # 신호 + 관찰을 합쳐 최소 이 개수까지 표시


def expected_last_start(now):
    """지금 시각(KST) 기준으로 마지막으로 마감된 4시간봉의 시작 시각. 업비트 4시간봉은 01·05·09·13·17·21시에 시작한다."""
    t = now.replace(minute=0, second=0, microsecond=0)
    while t.hour % 4 != 1:
        t -= timedelta(hours=1)
    if t + timedelta(hours=4) > now:
        t -= timedelta(hours=4)
    return t


def score(s, btc, rank):
    """90점 만점. 거래량(30점)이 가장 큰 비중: 기준봉 거래대금 배수(15) + 24시간 거래대금 순위(8) + 눌림 때 거래량 마름(7)."""
    plans = s["plans"]
    rr = max((p["rr"] for p in plans.values()), default=0)
    risk = min((p["risk_pct"] for p in plans.values()), default=10)
    mult = s["mult"]
    vm = 15 if 10 <= mult < 20 else 12 if 6 <= mult < 10 else 8 if mult >= 20 else 4 if mult >= 3 else 1
    vr = s["vol_ratio"]
    parts = {
        "거래량": vm + (8 if rank <= 5 else 6 if rank <= 15 else 4 if rank <= 30 else 2) + (7 if vr <= 0.3 else 4 if vr <= 0.6 else 0),
        "타점": min(25, sum(SETUP_POINTS.get(k, 8) for k in s["setups"])),
        "손익비": round(max(0.0, min(rr / 3, 1)) * 15, 1) if plans else 0,
        "손절폭": round(max(0.0, min((10 - risk) / 7, 1)) * 10, 1) if plans else 0,
        "시황": (5 if btc["above45"] else 0) + (5 if btc["aligned"] else 0),
    }
    total = round(sum(parts.values()))
    grade = "A" if total >= 68 else "B" if total >= 54 else "C" if total >= 40 else "D"
    return parts, total, grade


def candle_label(ts):
    return f"{ts:%m/%d %H:%M}~{(ts + timedelta(hours=4)):%H:%M}"


def missing(btc_ok, raw_setups, raw_base):
    """신호가 아닌 이유(부족한 조건) 목록."""
    why = []
    if config.REQUIRE_BTC and not btc_ok:
        why.append("BTC 조건 미충족")
    if raw_base is None:
        why.append(f"최근 {config.BASE_LOOKBACK}캔들 안에 거래대금 폭발 봉 없음")
    else:
        if raw_base["mult"] < config.BASE_MULT:
            why.append(f"기준봉 거래대금 {raw_base['mult']}배(10배 필요)")
        if raw_base["days_ago"] > config.BASE_MAX_AGE:
            why.append(f"기준봉이 {raw_base['days_ago']}캔들 전(6캔들 이내 필요)")
    if not raw_setups:
        why.append("매수 타점 없음")
    elif config.ALLOWED_SETUPS is not None and not any(k in config.ALLOWED_SETUPS for k in raw_setups):
        why.append(f"{'·'.join(raw_setups)}은 백테스트 성과 부진으로 제외된 타점")
    return why


def build(out_dir, if_needed=False):
    now = datetime.utcnow() + timedelta(hours=9)
    json_path = os.path.join(out_dir, "latest.json")
    want = expected_last_start(now)
    if if_needed and os.path.exists(json_path):
        try:
            if json.load(open(json_path, encoding="utf-8")).get("last_candle_start") == f"{want:%Y-%m-%d %H:%M}":
                print(f"이미 최신입니다 (기준 캔들 시작 {want:%m/%d %H:%M}). 건너뜀")
                return None
        except (ValueError, OSError):
            pass
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
    btc["ok"] = btc["above45"] and btc["aligned"]
    ranks = {m: i + 1 for i, (m, _, _) in enumerate(sorted(((m, n, v) for m, (n, v, _) in data.items()), key=lambda x: -x[2]))}

    rows = []
    for m, (name, v24, df) in data.items():
        strict, base_s = strategy.find_setups(df, strict=True)
        signal = bool(strict) and (btc["ok"] or not config.REQUIRE_BTC)
        raw, base_r = strategy.find_setups(df, strict=False)
        setups, base = (strict, base_s) if signal else (raw, base_r)
        t = df.iloc[-1]
        s = {"market": m, "name": name, "price": float(t["close"]), "setups": setups, "base": base, "signal": signal,
             "mult": base["mult"] if base else round(float(t["vmult"]), 1) if t["vmult"] == t["vmult"] else 0.0,
             "plans": strategy.make_plans(setups, df) if setups else {}, "v24_eok": round(v24 / 1e8), "rank": ranks[m],
             "candle": candle_label(t["date"]),
             "vol_ratio": float(t["volume"] / df.iloc[-2]["volume"]) if df.iloc[-2]["volume"] > 0 else 1.0,
             "chart": [round(float(x), 6) for x in df["close"].tail(60)],
             "miss": [] if signal else missing(btc["ok"], raw, base_r)}
        s["parts"], s["score"], s["grade"] = score(s, btc, ranks[m])
        rows.append(s)
    signals = sorted((s for s in rows if s["signal"]), key=lambda s: -s["score"])
    watch = sorted((s for s in rows if not s["signal"]), key=lambda s: -s["score"])
    watch = watch[:max(0, SHOW_TOTAL - len(signals))]

    os.makedirs(out_dir, exist_ok=True)
    result = {"updated": f"{now:%Y-%m-%d %H:%M}", "last_candle": btc["candle"], "last_candle_start": f"{want:%Y-%m-%d %H:%M}",
              "btc": btc, "scanned": len(data), "max_score": MAX_SCORE, "signals": signals, "watch": watch}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(result))
    print(f"스캔 {len(data)}개 코인, 신호 {len(signals)}개, 관찰 {len(watch)}개, 기준 캔들 {btc['candle']}")
    for s in signals + watch:
        print(f"  {'★신호' if s['signal'] else '관찰'} {s['grade']} {s['score']:>2}점 {s['name']}({s['market']}) {'+'.join(s['setups']) or '-'}")
    return result


def spark(vals, w=120, h=32):
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / span * h:.1f}" for i, v in enumerate(vals))
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true"><polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>'


def card(s, r):
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(k)}</td><td>{strategy.fmt(p['entry'])}</td><td>{strategy.fmt(p['stop'])} <small>(-{p['risk_pct']}%)</small></td>"
        f"<td>{strategy.fmt(p['target1'])}</td></tr>" for k, p in s["plans"].items())
    table = (f'<div class="tw"><table><thead><tr><th>타점</th><th>진입</th><th>손절</th><th>목표(전량)</th></tr></thead><tbody>{rows}</tbody></table></div>'
             if rows else "")
    why = "".join(f"<li><b>{e(k)}</b> - {e(v)}</li>" for k, v in s["setups"].items())
    base = s["base"]
    btxt = (f"기준 거래대금 봉: {base['value_eok']}억원(평소의 {base['mult']}배), {base['days_ago']}캔들 전" if base
            else f"기준 거래대금 봉 없음 (현재 봉 거래대금은 평소의 {s['mult']}배)") + f" · 직전 봉 대비 거래량 {s['vol_ratio']:.0%}"
    parts = " · ".join(f"{k} {v}" for k, v in s["parts"].items())
    if s["signal"]:
        badge = '<span class="bd v">★ 신호</span>'
        miss = ""
    else:
        badge = '<span class="bd r">관찰</span>'
        miss = f'<p class="miss">신호가 아닌 이유: {e(" · ".join(s["miss"]))}</p>'
    cls = "card sig" if s["signal"] else "card watch"
    return f"""<article class="{cls} g{s['grade']}"><header><div><h2>{e(s['name'])} <small>{e(s['market'])}</small> {badge}</h2>
<p class="mut">현재가 {strategy.fmt(s['price'])} · 24h 거래대금 {s['v24_eok']:,}억 ({s['rank']}위)</p></div>
<div class="sc"><b>{s['score']}</b><span>/{r['max_score']} {s['grade']}</span></div></header>
<div class="sp">{spark(s['chart'])}</div>{miss}
<ul class="why">{why}</ul><p class="mut">{e(btxt)}</p>{table}
<p class="mut small">점수 구성: {e(parts)}</p></article>"""


def render(r):
    e = html.escape
    btc = r["btc"]
    state = ("상승 (45선 위, 5선>20선) - 매수 조건 충족" if btc["ok"] else
             "45선 위지만 5선<20선 - 매수 조건 미충족" if btc["above45"] else "45선 아래(약세) - 매수 조건 미충족")
    sig_html = "\n".join(card(s, r) for s in r["signals"])
    if r["signals"]:
        sig_block = f'<h3 class="sec sg">★ 신호 {len(r["signals"])}개 <small>백테스트 기준을 모두 채운 코인</small></h3>\n{sig_html}'
    else:
        why = ("BTC가 45선 위이면서 5선>20선일 때만 신호를 냅니다. 지금은 BTC 조건 미충족입니다." if not btc["ok"]
               else "BTC 조건은 충족이지만 기준봉(10배 이상·24시간 이내)과 타점을 모두 채운 코인이 없습니다.")
        sig_block = f'<div class="nosig"><b>지금은 신호가 없습니다.</b><br>{why}<br>다음 4시간봉이 마감되면 다시 계산합니다.</div>'
    watch_block = ""
    if r["watch"]:
        watch_block = (f'<h3 class="sec">관찰 · 점수 상위 <small>신호는 아니지만 점수가 높은 코인 (부족한 조건을 함께 표시)</small></h3>\n'
                       + "\n".join(card(s, r) for s in r["watch"]))
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>업비트 유목민 4시간봉</title><style>
:root{{--bg:#f6f7f9;--fg:#15181d;--mut:#667085;--card:#fff;--line:#e4e7ec;--acc:#1b64f2;--A:#12805c;--B:#1b64f2;--C:#b7791f;--D:#98a2b3;--sigbg:#e8f6ef;--sigline:#12805c}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1115;--fg:#e8eaee;--mut:#98a2b3;--card:#181b21;--line:#2a2f38;--acc:#6ea0ff;--A:#3ccf9b;--B:#6ea0ff;--C:#e8b14f;--D:#7b8494;--sigbg:#12281f;--sigline:#3ccf9b}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Malgun Gothic",sans-serif}}
main{{max-width:880px;margin:0 auto;padding:20px 16px 60px}}h1{{font-size:20px;margin:0 0 4px}}.mut{{color:var(--mut);margin:2px 0}}.small{{font-size:12px}}
.top{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:14px 0}}
.sec{{font-size:16px;margin:22px 0 6px}}.sec small{{color:var(--mut);font-weight:400;font-size:12px;margin-left:6px}}.sec.sg{{color:var(--sigline)}}
.nosig{{background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:18px 16px;text-align:center;color:var(--mut)}}.nosig b{{color:var(--fg)}}
.card{{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--D);border-radius:12px;padding:14px 16px;margin:12px 0}}
.card.sig{{background:var(--sigbg);border:2px solid var(--sigline);border-left-width:8px}}.card.watch{{opacity:.92}}
.gA{{border-left-color:var(--A)}}.gB{{border-left-color:var(--B)}}.gC{{border-left-color:var(--C)}}
header{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}h2{{font-size:17px;margin:0}}h2 small{{color:var(--mut);font-weight:400;font-size:12px}}
.sc{{text-align:right;white-space:nowrap}}.sc b{{font-size:26px}}.sc span{{color:var(--mut);font-size:12px;margin-left:2px}}.sp{{color:var(--acc);margin:6px 0}}
.miss{{margin:4px 0;font-size:13px;color:var(--C)}}
.why{{margin:6px 0;padding-left:18px;font-size:13px}}.tw{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px;min-width:380px}}
th,td{{text-align:right;padding:5px 6px;border-bottom:1px solid var(--line);white-space:nowrap}}th:first-child,td:first-child{{text-align:left}}th{{color:var(--mut);font-weight:500}}
.bd{{font-size:11px;font-weight:600;border-radius:99px;padding:1px 8px;margin-left:4px;vertical-align:middle}}.bd.v{{background:var(--A);color:#fff}}.bd.r{{background:var(--line);color:var(--mut)}}
footer{{color:var(--mut);font-size:12px;margin-top:24px}}</style></head><body><main>
<h1>업비트 유목민 · 4시간봉</h1>
<p class="mut">기준 캔들 <b>{e(r['last_candle'])}</b> · 계산 {r['updated']} (KST) · 스캔 {r['scanned']}개 코인 · 신호 {len(r['signals'])}개</p>
<div class="top"><b>BTC 시황</b> {strategy.fmt(btc['price'])} · {e(state)}<p class="mut small">4시간봉은 업비트 기준 01·05·09·13·17·21시에 시작하고 4시간 뒤 마감됩니다. 마감된 봉만 사용하고, 하루 6번 갱신됩니다.</p></div>
{sig_block}
{watch_block}
<footer><b>적용 기준(백테스트 최적)</b>: 기준봉 거래대금이 평소(7일 중앙값)의 10배 이상이고 최근 24시간 안에 터졌을 것 · 타점 3개(바닥주 224선 돌파, 거감음봉 지지, 1일차 장대음봉 지지) · BTC가 45선 위이고 5선>20선 · 목표가(손절폭의 1.5배) 도달 시 전량 매도, 손절 이탈 시 전량 매도, 최대 14일 보유.
백테스트(48개 코인, 2025-12~2026-10, 수수료·슬리피지 반영): 227건, 승률 53%, 평균 +1.6%/건, 손익비(PF) 1.76. 앞쪽 60% 기간에서 고른 기준이 뒤쪽 40%에서도 유지됐고 시간 3등분 구간이 모두 플러스였습니다. 다만 현재 상장된 코인으로만 검증해 실제보다 좋게 나왔을 수 있고(생존 편향), 과거 성과가 앞으로를 보장하지 않습니다.
'관찰' 코인은 신호 기준을 채우지 못한 코인이며 백테스트로 검증된 매수 대상이 아닙니다. 조건이 얼마나 갖춰졌는지 보는 규칙 기반 점수이며 투자 판단과 주문은 직접 하세요. 재료(뉴스) 항목은 반영하지 않아 90점 만점입니다.</footer></main></body></html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(config.BASE_DIR, "reports"))
    ap.add_argument("--if-needed", action="store_true")
    a = ap.parse_args()
    build(a.out, a.if_needed)
