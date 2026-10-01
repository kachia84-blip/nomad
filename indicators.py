"""지표 계산 모듈 - 이동평균선(3/5/8/45일)과 RSI(14)를 계산합니다."""


def add_indicators(df):
    """일봉 표에 이평선과 RSI 열을 붙여서 돌려준다."""
    df = df.copy()
    for n in (3, 5, 8, 15, 20, 45, 60, 224):
        df[f"ma{n}"] = df["close"].rolling(n).mean()

    # RSI(14): 와일더 방식 (상승폭/하락폭의 지수이동평균)
    diff = df["close"].diff()
    gain = diff.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-diff.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    df["rsi"] = 100 - 100 / (1 + rs)
    return df


def chart_data(df, n=60):
    """카드에 일봉 차트를 그리기 위한 최근 n일 데이터 (용량을 줄이려고 열별 배열로 저장)."""
    t = df.tail(n)

    def col(name):
        return [None if v != v else round(float(v), 1) for v in t[name]]

    return {"d": [str(x) for x in t["date"]], "o": col("open"), "h": col("high"), "l": col("low"), "c": col("close"),
            "v": [int(x) for x in t["volume"]], "m5": col("ma5"), "m20": col("ma20"), "m60": col("ma60")}
