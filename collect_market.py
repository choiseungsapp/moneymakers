#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
머니메이커스 데이터 수집기 (v1)
- KOSPI + KOSDAQ 통합 '상승률 TOP 30'을 KRX 데이터로 정확히 수집한다.
- 숫자(등락률·지수)는 AI에 맡기지 않고 코드로만 가져온다.
- 결과를 앱의 '특징주 / 상승률 TOP' 칸에 붙여넣을 수 있는 형식으로 출력한다.

설치:  pip install pykrx pandas
실행:  python collect_market.py            # 가장 최근 거래일
       python collect_market.py 20260619   # 특정 날짜(YYYYMMDD)

※ 실행 시 'KRX 로그인 실패...' 경고가 떠도 무시하세요. 기본 시세 조회는 로그인 없이 됩니다.
"""

import sys
import pandas as pd
from pykrx import stock

TOP_N = 30
LIMIT_PCT = 29.0      # 등락률이 이 값 이상이면 상한가 후보로 표시(일일 ±30% 기준)
KOSPI_IDX = "1001"    # 코스피 지수
KOSDAQ_IDX = "2001"   # 코스닥 지수


def resolve_date(arg: str | None) -> str:
    """인자가 있으면 그 날짜, 없으면 가장 최근 거래일(YYYYMMDD)."""
    if arg:
        return arg.strip()
    return stock.get_nearest_business_day_in_a_week()


def fetch_movers(date: str) -> pd.DataFrame:
    """KOSPI+KOSDAQ 전 종목의 일간 등락률을 합쳐 등락률 내림차순으로 반환."""
    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        df = stock.get_market_ohlcv_by_ticker(date, market=market)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["시장"] = market
        df["티커"] = df.index
        frames.append(df)

    if not frames:
        raise RuntimeError(f"{date} 데이터가 비어 있습니다. 거래일이 아니거나 아직 장 데이터가 없을 수 있어요.")

    allm = pd.concat(frames)
    # 등락률 컬럼만 신뢰. 거래량 0(거래정지 등)은 제외.
    if "거래량" in allm.columns:
        allm = allm[allm["거래량"] > 0]
    allm = allm.dropna(subset=["등락률"])
    allm = allm.sort_values("등락률", ascending=False).head(TOP_N)

    # 상위 종목만 이름 조회 (30건이라 가볍다)
    names = []
    for t in allm["티커"]:
        try:
            names.append(stock.get_market_ticker_name(t))
        except Exception:
            names.append(t)
    allm["종목명"] = names
    return allm[["종목명", "티커", "시장", "등락률"]].reset_index(drop=True)


def fetch_index_change(date: str, idx_ticker: str) -> tuple[float, float]:
    """지수의 (종가, 등락률%)를 반환. 등락률 컬럼이 없으면 전일 대비로 계산."""
    # 최근 약 10일 창에서 해당 날짜까지의 마지막 행 사용
    start = (pd.Timestamp(date) - pd.Timedelta(days=10)).strftime("%Y%m%d")
    df = stock.get_index_ohlcv_by_date(start, date, idx_ticker)
    if df is None or df.empty:
        return (float("nan"), float("nan"))
    last = df.iloc[-1]
    close = float(last.get("종가", float("nan")))
    if "등락률" in df.columns and pd.notna(last.get("등락률")):
        return (close, float(last["등락률"]))
    # 등락률 컬럼이 없으면 전일 종가로 계산
    if len(df) >= 2:
        prev = float(df.iloc[-2]["종가"])
        if prev:
            return (close, (close - prev) / prev * 100)
    return (close, float("nan"))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    date = resolve_date(arg)
    ymd = f"{date[:4]}-{date[4:6]}-{date[6:]}"

    movers = fetch_movers(date)
    kospi_close, kospi_chg = fetch_index_change(date, KOSPI_IDX)
    kosdaq_close, kosdaq_chg = fetch_index_change(date, KOSDAQ_IDX)

    lines = []
    lines.append("=" * 58)
    lines.append(f" 머니메이커스 시황 데이터   |   기준일: {ymd}")
    lines.append("=" * 58)
    lines.append("")
    lines.append("[지수]")
    lines.append(f"KOSPI  : {kospi_close:>10,.2f}  ({kospi_chg:+.2f}%)")
    lines.append(f"KOSDAQ : {kosdaq_close:>10,.2f}  ({kosdaq_chg:+.2f}%)")
    lines.append("")
    lines.append("[상승률 TOP 30]  (KOSPI+KOSDAQ 통합, 일간 등락률 내림차순)")
    for i, row in movers.iterrows():
        limit = "  ★상한가후보" if row["등락률"] >= LIMIT_PCT else ""
        lines.append(
            f"{i+1:>2}. {row['종목명']:<14} ({row['시장']:<6}) {row['등락률']:+6.2f}%{limit}"
        )
    lines.append("")
    lines.append("-" * 58)
    lines.append("※ [상승률 TOP 30] 블록 → 앱의 '특징주 / 상승률 TOP' 칸에 붙여넣기")
    lines.append("※ [지수] 등락률 → 앱의 KOSPI/KOSDAQ 등락률 칸에 입력")
    lines.append("※ 사유는 비워두면 AI가 뉴스와 엮어 채웁니다(없으면 '확인 불가'로 표기).")

    out = "\n".join(lines)
    print(out)

    fname = f"market_data_{date}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(f"\n[저장됨] {fname}")


if __name__ == "__main__":
    main()
