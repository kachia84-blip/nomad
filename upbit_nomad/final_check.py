"""최종 후보 비교 - research.py 가 저장한 신호로 배수 구간·기준봉 최근성·타점 조합을 청산 규칙(1.5R 전량/84캔들)에서 비교한다."""
import itertools, pickle, os
import numpy as np, pandas as pd
import config, research as R
d = pickle.load(open(R.PKL, "rb")); coins, sigs = d["coins"], d["sigs"]
S = sorted(enumerate(sigs), key=lambda x: (x[1]["time"], x[0]))
times = sorted(s["time"] for s in sigs); cut = times[int(len(times) * .6)]
t1, t2 = times[int(len(times) / 3)], times[int(len(times) * 2 / 3)]
EX = dict(stop_scale=1.0, t1=1.5, frac1=1.0, t2=None, trail=5, hold=84)
SETS = {"바닥주+눌림+1일차": ("바닥주 224일선 돌파", "거감음봉 지지", "1일차 장대음봉 지지"), "바닥주+눌림": ("바닥주 224일선 돌파", "거감음봉 지지"), "바닥주": ("바닥주 224일선 돌파",), "전부": None}
rows = []
for (mn, mx), (sn, st), md, btc in itertools.product([(8,15),(8,20),(8,30),(10,15),(10,20),(10,30),(10,1e9),(12,30),(6,20),(6,1e9)], SETS.items(), (3, 6, 15), ("45al", "45")):
    f = R.Filt(mn, mx, st, btc, None, md)
    tr = R.pick_trades(S, coins, f, EX, None)
    if len(tr) < 60: continue
    a = [r for t, r, _ in tr if t <= cut]; b = [r for t, r, _ in tr if t > cut]
    thirds = [np.mean([r for t, r, _ in tr if lo < t <= hi]) * 100 if any(lo < t <= hi for t, _, _ in tr) else np.nan for lo, hi in ((times[0] - pd.Timedelta(days=1), t1), (t1, t2), (t2, times[-1]))]
    allr = [r for _, r, _ in tr]
    rows.append(dict(배수=f"{mn}~{'∞' if mx>1e8 else int(mx)}", 타점=sn, BTC=btc, 기준봉최근=md, n=len(tr), 전체PF=R.pf(allr), 전체평균=np.mean(allr)*100, 승률=np.mean(np.array(allr)>0)*100,
                     학습n=len(a), 학습PF=R.pf(a), 학습t=R.tstat(a), 검증n=len(b), 검증PF=R.pf(b), 검증평균=np.mean(b)*100,
                     구간1=thirds[0], 구간2=thirds[1], 구간3=thirds[2], 최악=min(allr)*100))
X = pd.DataFrame(rows)
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30)
X["세구간모두+"] = (X[["구간1", "구간2", "구간3"]] > 0).all(axis=1)
print("학습 t값 상위 15 (검증/3구간 병기)")
print(X.sort_values("학습t", ascending=False).head(15).round(2).to_string(index=False))
print("\n세 구간(시간 3등분) 모두 평균수익 +인 조합 중 전체 n≥100, 전체PF 상위 10")
print(X[X["세구간모두+"] & (X.n >= 100)].sort_values("전체PF", ascending=False).head(10).round(2).to_string(index=False))
X.to_csv(os.path.join(config.REPORT_DIR, "final_check.csv"), index=False, encoding="utf-8-sig")
