"""설정 파일 - 숫자를 바꾸고 싶으면 이 파일만 고치면 됩니다.
모든 '일'은 4시간봉 1개(=캔들)로 바뀌었습니다. 예: 224일선 → 4시간봉 224개 이동평균(약 37일)."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
REPORT_DIR = os.path.join(BASE_DIR, "reports")

# ── 수집 ──────────────────────────────────────────
UNIT = 240                   # 4시간봉 (업비트 minutes/240)
TOP_N_COINS = 60             # 24시간 거래대금 상위 몇 개 코인을 볼지
HISTORY_CANDLES = 320        # 스캔용 캔들 수 (224선 계산에 최소 230개 필요)
BACKTEST_CANDLES = 1800      # 백테스트용 캔들 수 (4h × 1800 ≈ 300일)
SLEEP = 0.13                 # 요청 간격(초), 업비트 제한 초당 10회
TIMEOUT = 10
MIN_24H_VALUE = 5_000_000_000   # 24시간 거래대금 50억 미만 코인은 제외(유동성 부족)
STABLE = {"KRW-USDT", "KRW-USDC"}  # 스테이블코인은 제외

# ── 기준 거래대금(거) ─────────────────────────────
BASE_FIND_MULT = 3.0         # 기준봉 후보: 4시간 거래대금이 7일 중앙값의 3배 이상인 양봉 중 '가장 최근 것'을 기준봉으로 삼음
BASE_MULT = 10.0             # 4시간 거래대금이 최근 7일(42캔들) 중앙값의 이 배수 이상이면 '터졌다' (백테스트 최적: 10~20배)
BASE_MULT_MAX = 20.0         # 그 기준봉이 20배 이상이면 꼭대기 급등(추격 위험)이라 신호 제외 - 학습/검증 양쪽에서 10~20배가 가장 좋았음
CORE_ONLY = True             # 핵심 타점 4개만 사용 (바닥주 224선 돌파·갭상승 양봉·1일차 장대음봉 지지·거감음봉 지지)
BASE_MIN_VALUE = 500_000_000  # 그래도 4시간 거래대금 5억 미만이면 기준봉으로 보지 않음
BASE_LOOKBACK = 15           # 기준봉이 최근 몇 캔들 안에 있어야 하는지
PULLBACK_BASE_MAX = 6        # 눌림목 판정: 기준봉이 최근 이 캔들 안일 것

# ── 타점 기준(차) ─────────────────────────────────
BOTTOM_MAX_ABOVE_PCT = 8.0
BOTTOM_BELOW_RATIO = 0.7
BIG_BEAR_BODY_PCT = 2.0      # 4시간봉은 일봉보다 움직임이 작아 3%→2%
MA5_BREAK_MAX_PCT = 3.0
MA5_GAP_MAX_PCT = 5.0
GAP_MIN_PCT = 0.3            # 24시간 거래라 갭이 작음: 시가가 직전 종가보다 이만큼(%) 위
WICK_MIN = 0.05
DRY_VS_BASE = 0.4
VOL_DROP_RATIO = 0.25
MA_TOUCH_PCT = 1.0
NAKJU_SURGE_PCT = 15.0       # 4시간봉 기준 30캔들(5일) 내 고점이 45선 대비 이만큼 위
RSI_OVERSOLD = 30
RESIST_LOOKBACK = 42         # 1차 목표용 저항선: 직전 42캔들(7일) 고점

# ── 백테스트 ──────────────────────────────────────
FEE = 0.0005                 # 업비트 원화마켓 수수료 0.05% (매수·매도 각각)
SLIPPAGE = 0.0005            # 체결 미끄러짐 가정 0.05%
MAX_HOLD = 42                # 최대 보유 캔들(7일)
