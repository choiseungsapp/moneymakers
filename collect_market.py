#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
머니메이커스 데이터 수집기 (v2 - 네이버 금융 기반)
- 네이버 금융 '상승' 페이지에서 KOSPI+KOSDAQ 통합 상승률 TOP 30을 수집한다.
- pykrx / pandas / numpy 를 전혀 사용하지 않는다 (requests + beautifulsoup4 만 사용).
- 결과를 앱의 '특징주 / 상승률 TOP' 칸에 붙여넣을 수 있는 형식으로 출력한다.

설치:  pip install requests beautifulsoup4
실행:  python collect_market.py

※ 장 마감(15:30) 이후 실행하면 당일 최종 등락률이 나옵니다. (장중 실행 시 실시간 값)
"""

import re
import sys
from datetime import datetime

import requests
from bs4 import BeautifulSoup

RISE_URL = "https://finance.naver.com/sise/sise_rise.naver?sosok={}"   # 0=KOSPI, 1=KOSDAQ
INDEX_URL = "https://polling.finance.naver.com/api/realtime/domestic/index/{}"  # KOSPI / KOSDAQ
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://finance.naver.com/sise/",
}
TOP_N = 30
LIMIT_PCT = 29.0          # 등락률이 이 값 이상이면 상한가 후보로 표시
PCT_RE = re.compile(r"([-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*%")


def fetch_market(sosok, market_name):
    """네이버 상승 페이지에서 (종목명, 시장, 등락률) 리스트를 반환."""
    url = RISE_URL.format(sosok)
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    res.encoding = "euc-kr"          # 네이버 금융은 EUC-KR
    soup = BeautifulSoup(res.text, "html.parser")

    table = soup.select_one("table.type_2")
    if table is None:
        return []

    rows = []
    seen = set()
    for tr in table.select("tr"):
        link = tr.select_one("a.tltle")   # 네이버 종목명 링크 (오타 클래스명 'tltle' 맞음)
        if link is None:
            continue
        name = link.get_text(strip=True)
        if not name or name in seen:
            continue

        # 등락률: 행의 td 중 '%'가 들어간 첫 셀에서 숫자 추출 (상승 페이지라 모두 양수)
        rate = None
        for td in tr.find_all("td"):
            txt = td.get_text(strip=True)
            if "%" in txt:
                m = PCT_RE.search(txt)
                if m:
                    rate = float(m.group(1).replace(",", ""))
                    break
        if rate is None:
            continue

        seen.add(name)
        rows.append((name, market_name, rate))
    return rows


def fetch_index(name):
    """지수의 (종가, 등락률%) 를 best-effort로 반환. 실패하면 None."""
    try:
        res = requests.get(INDEX_URL.format(name), headers=HEADERS, timeout=10)
        data = res.json()

        node = data
        if isinstance(node, dict) and "datas" in node and node["datas"]:
            node = node["datas"][0]

        def dig(d, *keys):
            for k in keys:
                if isinstance(d, dict) and k in d and d[k] not in (None, ""):
                    return d[k]
            return None

        close = dig(node, "closePrice", "now", "nv")
        ratio = dig(node, "fluctuationsRatio", "rate", "cr")
        if close is None or ratio is None:
            return None
        close = float(str(close).replace(",", ""))
        ratio = float(str(ratio).replace(",", "").replace("%", ""))
        return (close, ratio)
    except Exception:
        return None


def main():
    today = datetime.now().strftime("%Y-%m-%d")

    movers = fetch_market(0, "KOSPI") + fetch_market(1, "KOSDAQ")
    if not movers:
        print("상승 종목을 가져오지 못했습니다. 네이버 페이지 구조가 바뀌었거나 네트워크 문제일 수 있어요.")
        sys.exit(1)

    movers.sort(key=lambda x: x[2], reverse=True)
    movers = movers[:TOP_N]

    kospi = fetch_index("KOSPI")
    kosdaq = fetch_index("KOSDAQ")

    def idx_line(label, v):
        if v is None:
            return f"{label:<7}: (자동수집 실패 — 네이버에서 직접 확인해 입력)"
        return f"{label:<7}: {v[0]:>10,.2f}  ({v[1]:+.2f}%)"

    lines = []
    lines.append("=" * 58)
    lines.append(f" 머니메이커스 시황 데이터   |   기준일: {today}")
    lines.append("=" * 58)
    lines.append("")
    lines.append("[지수]")
    lines.append(idx_line("KOSPI", kospi))
    lines.append(idx_line("KOSDAQ", kosdaq))
    lines.append("")
    lines.append("[상승률 TOP 30]  (KOSPI+KOSDAQ 통합, 등락률 내림차순)")
    for i, (name, market, rate) in enumerate(movers, 1):
        limit = "  ★상한가후보" if rate >= LIMIT_PCT else ""
        lines.append(f"{i:>2}. {name:<14} ({market:<6}) {rate:+6.2f}%{limit}")
    lines.append("")
    lines.append("-" * 58)
    lines.append("※ [상승률 TOP 30] 블록 → 앱의 '특징주 / 상승률 TOP' 칸에 붙여넣기")
    lines.append("※ [지수] 등락률 → 앱의 KOSPI/KOSDAQ 등락률 칸에 입력")
    lines.append("※ 사유는 비워두면 AI가 뉴스와 엮어 채웁니다.")

    out = "\n".join(lines)
    print(out)

    fname = f"market_data_{today}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(f"\n[저장됨] {fname}")


if __name__ == "__main__":
    main()
