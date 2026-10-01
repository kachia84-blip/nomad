"""데이터 수집 모듈 - 네이버 증권(모바일 JSON API)에서 종목 목록과 일봉을 가져옵니다.
※ 네이버가 예전 finance.naver.com 표 페이지를 없애서, 지금은 m.stock.naver.com 의 JSON 주소를 씁니다."""
import random
import time

import pandas as pd
import requests

import config

BASE = "https://m.stock.naver.com/api"


def get_json(url, params=None):
    """User-Agent를 붙여 요청하고, 봇 차단을 피하려고 잠깐 쉰다."""
    time.sleep(random.uniform(config.SLEEP_MIN, config.SLEEP_MAX))
    res = requests.get(url, params=params, headers=config.HEADERS, timeout=config.TIMEOUT)
    res.raise_for_status()
    return res.json()


def to_number(text):
    """'1,234', '-3.2' 같은 글자를 숫자로 바꾼다."""
    try:
        return float(str(text).replace(",", "").replace("+", ""))
    except ValueError:
        return 0.0


def normalize(item):
    """API 응답 한 줄 → 우리가 쓰는 형태."""
    return {
        "code": item["itemCode"],
        "name": item["stockName"],
        "price": to_number(item["closePrice"]),
        "rate": to_number(item["fluctuationsRatio"]),
        "volume": to_number(item.get("accumulatedTradingVolumeRaw", item.get("accumulatedTradingVolume", 0))),
        "trade_value": to_number(item.get("accumulatedTradingValueRaw", 0)) / 1_000_000,  # 백만원 단위
        "type": item.get("stockEndType", "stock"),
    }


def fetch_list(kind, market, size=100):
    """kind: 'quantTop'(거래량 상위) / 'up'(상승률 상위). ETF·ETN은 제외하고 주식만 반환."""
    data = get_json(f"{BASE}/stocks/{kind}/{market}", {"page": 1, "pageSize": size})
    return [normalize(s) for s in data.get("stocks", []) if s.get("stockEndType") == "stock"]


def fetch_overtime(code):
    """시간외 단일가 등락률(%). 정보가 없으면 None."""
    try:
        info = get_json(f"{BASE}/stock/{code}/basic").get("overMarketPriceInfo")
        return to_number(info["fluctuationsRatio"]) if info else None
    except Exception:
        return None


def collect_candidates(log):
    """거래대금 상위 / 거래량 1천만주 이상 / 시간외 4%↑ 종목을 모아 중복 없이 반환."""
    quant, up = [], []
    for market in ("KOSPI", "KOSDAQ"):
        quant += fetch_list("quantTop", market)
        up += fetch_list("up", market, 30)
    log(f"거래량 상위 {len(quant)}개, 상승률 상위 {len(up)}개 수집")

    by_value = sorted(quant, key=lambda r: r["trade_value"], reverse=True)[: config.TOP_N_TRADING_VALUE]
    by_volume = [r for r in quant if r["volume"] >= config.VOLUME_MIN]

    merged = {}

    def add(source, items):
        for r in items:
            merged.setdefault(r["code"], {**r, "sources": []})["sources"].append(source)

    add("거래대금 상위", by_value)
    add("거래량 1천만주↑", by_volume)

    # 시간외 단일가: 후보 + 상승률 상위 종목의 시간외 등락률을 확인해 4% 이상만 표시
    pool = {r["code"]: r for r in by_value + by_volume + up}
    log(f"시간외 단일가 확인 중 ({len(pool)}개)...")
    for code, r in pool.items():
        rate = fetch_overtime(code)
        if rate is not None and rate >= config.AFTER_HOURS_MIN_RATE:
            r["overtime"] = rate
            add(f"시간외 {rate:+.1f}%", [r])

    result = list(merged.values())[: config.MAX_CANDIDATES]
    log(f"주도주 후보 {len(result)}개 확정")
    return result


def resolve_manual(entries, log):
    """사용자가 직접 넣은 종목(코드 또는 이름)을 후보 형태로 변환. 예: '삼성전자', '005930'"""
    out = []
    for e in entries:
        e = e.strip()
        if not e:
            continue
        try:
            found = get_json("https://ac.stock.naver.com/ac", {"q": e, "target": "stock"})["items"]
            found = [f for f in found if f.get("category") == "stock"]
            if not found:
                log(f"'{e}' 종목을 찾지 못했습니다")
                continue
            code = found[0]["code"]
            basic = get_json(f"{BASE}/stock/{code}/basic")
            item = normalize({**basic, "accumulatedTradingVolumeRaw": 0})
            # 거래량은 일봉에서 채워지므로 여기서는 0으로 두고 pipeline에서 갱신
            item["sources"] = ["직접 입력"]
            out.append(item)
        except Exception as ex:
            log(f"'{e}' 조회 실패: {ex}")
    return out


def fetch_daily(code, days=config.HISTORY_DAYS):
    """종목의 일봉(날짜/시가/고가/저가/종가/거래량)을 오래된 날짜부터 정렬해 반환.
    네이버는 한 번에 최대 60일치만 주므로 페이지를 나눠 받는다."""
    rows = []
    for page in range(1, (days + 59) // 60 + 1):
        got = get_json(f"{BASE}/stock/{code}/price", {"pageSize": 60, "page": page})
        rows += got
        if len(got) < 60:          # 상장한 지 얼마 안 된 종목은 여기서 끝
            break
    df = pd.DataFrame([{
        "date": r["localTradedAt"], "close": to_number(r["closePrice"]), "open": to_number(r["openPrice"]),
        "high": to_number(r["highPrice"]), "low": to_number(r["lowPrice"]),
        "volume": to_number(r["accumulatedTradingVolume"]),
    } for r in rows]).drop_duplicates("date")
    return df.sort_values("date").reset_index(drop=True).tail(days)
