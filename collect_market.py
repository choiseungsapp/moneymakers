#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
머니메이커스 데이터 수집기 (v3 - 네이버 금융 기반)
- v2 기능(KOSPI+KOSDAQ 상승률 TOP 30) 유지.
- [추가] 업종별 등락률 → 오늘의 '주도 섹터' 히트맵.
- [추가] 시가총액 상위 종목 중 강세주 → '주도주 후보'.
  (등락률 TOP은 상한가 잡주 위주라 주도주가 안 잡힌다. 시총 큰데 오늘 강세인 게 주도주.)
- pykrx / pandas / numpy 미사용 (requests + beautifulsoup4 만 사용).

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
SECTOR_URL = "https://finance.naver.com/sise/sise_group.naver?type=upjong"      # 업종별 시세
MARKETSUM_URL = "https://finance.naver.com/sise/sise_market_sum.naver?sosok={}" # 0=KOSPI, 1=KOSDAQ
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://finance.naver.com/sise/",
}
TOP_N = 30
LEADER_N = 12             # 주도주 후보 출력 개수
SECTOR_N = 6             # 주도/소외 섹터 각각 출력 개수
LIMIT_PCT = 29.0          # 등락률이 이 값 이상이면 상한가 후보로 표시
PCT_RE = re.compile(r"([-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*%")


def _get_soup(url):
    """네이버 금융 페이지를 EUC-KR로 받아 BeautifulSoup 반환."""
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    res.encoding = "euc-kr"          # 네이버 금융은 EUC-KR
    return BeautifulSoup(res.text, "html.parser")


def _first_pct(tr):
    """행(tr)에서 '%'가 들어간 첫 셀의 숫자를 float로 반환 (없으면 None)."""
    for td in tr.find_all("td"):
        txt = td.get_text(strip=True)
        if "%" in txt:
            m = PCT_RE.search(txt)
            if m:
                return float(m.group(1).replace(",", ""))
    return None


def fetch_market(sosok, market_name):
    """네이버 상승 페이지에서 (종목명, 시장, 등락률) 리스트를 반환."""
    soup = _get_soup(RISE_URL.format(sosok))

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

        rate = _first_pct(tr)             # 상승 페이지라 모두 양수
        if rate is None:
            continue

        seen.add(name)
        rows.append((name, market_name, rate))
    return rows


def fetch_sectors():
    """업종별 등락률 (업종명, 등락률%) 리스트를 best-effort로 반환. 실패하면 []."""
    try:
        soup = _get_soup(SECTOR_URL)
    except Exception:
        return []

    rows = []
    seen = set()
    # 업종명 링크는 sise_group_detail.naver 로 연결된다 (클래스명에 의존하지 않음)
    for tr in soup.select("tr"):
        link = tr.select_one("a[href*='sise_group_detail']")
        if link is None:
            continue
        name = link.get_text(strip=True)
        if not name or name in seen:
            continue
        rate = _first_pct(tr)             # 업종 등락률은 음수일 수 있음 → PCT_RE가 부호 처리
        if rate is None:
            continue
        seen.add(name)
        rows.append((name, rate))
    return rows


def fetch_leaders(sosok, market_name):
    """시가총액 상위 페이지(1페이지=시총 상위 50)에서 강세주만 (종목명, 시장, 등락률)로 반환.
    페이지가 시총 내림차순으로 정렬돼 있으므로, 여기 잡히는 건 '대형주 중 오늘 오른 종목' = 주도주 후보."""
    try:
        soup = _get_soup(MARKETSUM_URL.format(sosok))
    except Exception:
        return []

    table = soup.select_one("table.type_2")
    if table is None:
        return []

    rows = []
    seen = set()
    for tr in table.select("tr"):
        link = tr.select_one("a.tltle")
        if link is None:
            continue
        name = link.get_text(strip=True)
        if not name or name in seen:
            continue
        rate = _first_pct(tr)
        if rate is None:
            continue
        seen.add(name)
        if rate > 0:                      # 시총 상위 중 강세만 = 주도주 후보
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

    sectors = fetch_sectors()
    leaders = fetch_leaders(0, "KOSPI") + fetch_leaders(1, "KOSDAQ")
    leaders.sort(key=lambda x: x[2], reverse=True)
    leaders = leaders[:LEADER_N]

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

    # ── 주도 섹터 ────────────────────────────────────────────
    lines.append("[주도 섹터]  (네이버 업종별 등락률 기준)")
    if sectors:
        up = sorted(sectors, key=lambda x: x[1], reverse=True)[:SECTOR_N]
        down = sorted(sectors, key=lambda x: x[1])[:SECTOR_N]
        up_str = " / ".join(f"{n} {r:+.2f}%" for n, r in up)
        down_str = " / ".join(f"{n} {r:+.2f}%" for n, r in down)
        lines.append(f"  강세: {up_str}")
        lines.append(f"  약세: {down_str}")
    else:
        lines.append("  (자동수집 실패 — 네이버 업종별시세에서 직접 확인)")
    lines.append("")

    # ── 주도주 후보 ──────────────────────────────────────────
    lines.append("[주도주 후보]  (시총 상위 50 중 강세, 등락률 내림차순)")
    if leaders:
        for i, (name, market, rate) in enumerate(leaders, 1):
            lines.append(f"{i:>2}. {name:<14} ({market:<6}) {rate:+6.2f}%")
    else:
        lines.append("  (자동수집 실패 또는 대형주 일제 약세 — 네이버 시총상위에서 확인)")
    lines.append("")

    # ── 상승률 TOP (테마/상한가 잡주 포함) ───────────────────
    lines.append("[상승률 TOP 30]  (KOSPI+KOSDAQ 통합, 등락률 내림차순)")
    for i, (name, market, rate) in enumerate(movers, 1):
        limit = "  ★상한가후보" if rate >= LIMIT_PCT else ""
        lines.append(f"{i:>2}. {name:<14} ({market:<6}) {rate:+6.2f}%{limit}")
    lines.append("")
    lines.append("-" * 58)
    lines.append("※ [주도 섹터] → 앱의 '오늘의 주도 섹터' 칸에 붙여넣기")
    lines.append("※ [주도주 후보] → 앱의 '주도주' 칸에 붙여넣기 (시총 큰데 강세 = 진짜 주도주)")
    lines.append("※ [상승률 TOP 30] → 앱의 '특징주 / 상승률 TOP' 칸 (테마·상한가 잡주)")
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
