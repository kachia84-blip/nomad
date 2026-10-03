"""조건 스윕 - 거래량 등 필터 조합을 앞 65% 기간(학습)에서 고르고 뒤 35% 기간(검증)에서 확인합니다. backtest.py 가 만든 거래 목록을 씁니다."""
import itertools
import os

import pandas as pd

import config

t = pd.read_csv(os.path.join(config.REPORT_DIR, "backtest_trades.csv"), parse_dates=["signal_time"])
cut = t["signal_time"].quantile(0.65)
print(f"전체 {len(t)}건 | 학습 ~{cut:%Y-%m-%d} / 검증 {cut:%Y-%m-%d}~")
CORE = ("바닥주 224일선 돌파", "갭상승 양봉", "1일차 장대음봉 지지", "거감음봉 지지")
SETS = {"전부": None, "핵심4": CORE, "핵심-갭·1일차": ("바닥주 224일선 돌파", "거감음봉 지지"),
        "바닥주만": ("바닥주 224일선 돌파",), "눌림만(거감음봉지지)": ("거감음봉 지지",)}


def pf(r):
    w, l = r[r > 0].sum(), -r[r <= 0].sum()
    return w / l if l > 0 else float("inf")


def ev(d):
    return len(d), (d["ret"] > 0).mean() * 100, d["ret"].mean() * 100, pf(d["ret"])


rows = []
for mmin, mmax, sname, btc, vr in itertools.product((3, 4, 6, 8, 10), (15, 20, 30, 1e9), SETS, (False, True), (9, 0.6, 0.3)):
    if mmax <= mmin:
        continue
    d = t[(t["base_mult"] >= mmin) & (t["base_mult"] < mmax)]
    if SETS[sname]:
        d = d[d["setup"].isin(SETS[sname])]
    if btc:
        d = d[d["btc_up"]]
    if vr < 9:
        d = d[(d["vol_ratio"] <= vr) | (d["setup"] == "바닥주 224일선 돌파")]
    a, b = d[d["signal_time"] <= cut], d[d["signal_time"] > cut]
    if len(a) < 40 or len(b) < 25:
        continue
    na, wa, ra, pa = ev(a); nb, wb, rb, pb = ev(b)
    rows.append(dict(배수=f"{mmin}~{mmax if mmax < 1e8 else '∞'}", 타점=sname, BTC필터=btc, 마른거래량=vr if vr < 9 else "-",
                     학습n=na, 학습승률=round(wa, 1), 학습평균=round(ra, 2), 학습PF=round(pa, 2),
                     검증n=nb, 검증승률=round(wb, 1), 검증평균=round(rb, 2), 검증PF=round(pb, 2)))
r = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(f"\n조합 {len(r)}개. 학습 PF 상위 15 (검증 성과를 함께 봄)")
print(r.sort_values("학습PF", ascending=False).head(15).to_string(index=False))
ok = r[(r["학습PF"] > 1.15) & (r["검증PF"] > 1.15)]
print(f"\n학습·검증 둘 다 PF>1.15: {len(ok)}개 (조합 {len(r)}개 중)")
print(ok.sort_values("학습PF", ascending=False).head(12).to_string(index=False))
r.to_csv(os.path.join(config.REPORT_DIR, "sweep.csv"), index=False, encoding="utf-8-sig")
