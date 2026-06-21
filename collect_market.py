#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
머니메이커스 데이터 수집기 (v2 - Naver Finance Scraping)
- KOSPI + KOSDAQ 통합 '상승률 TOP 30'을 네이버 금융에서 스크래핑합니다.
- numpy, pandas, pykrx 등 무겁고 충돌이 잦은 라이브러리를 완전히 제거했습니다.
- 결과는 앱의 '특징주 / 상승률 TOP' 칸에 붙여넣을 수 있는 형식으로 출력됩니다.

설치:  pip install requests beautifulsoup4
실행:  python collect_market.py
"""

import datetime
import requests
from bs4 import BeautifulSoup

def get_index(code):
    url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
    res = requests.get(url)
    res.encoding = 'euc-kr'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    now_elem = soup.find('em', id='now_value')
    if not now_elem:
        return "0.00", "0.00"
    now = now_elem.text.strip()
    
    change_elem = soup.find('span', id='change_value_and_rate')
    if not change_elem:
        return now, "0.00"
        
    change = change_elem.text.strip()
    # "하락 11.20 -0.40%" 등에서 퍼센트 부분만 추출
    try:
        rate = change.split('%')[0].split()[-1]
        # 상승/하락 기호 보정
        if float(rate) > 0 and not rate.startswith('+'):
            rate = '+' + rate
    except Exception:
        rate = "0.00"
        
    return now, rate

def get_top_gainers(sosok, market_name):
    # sosok=0: KOSPI, sosok=1: KOSDAQ
    url = f"https://finance.naver.com/sise/sise_rise.naver?sosok={sosok}"
    res = requests.get(url)
    res.encoding = 'euc-kr'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    tbl = soup.find('table', class_='type_2')
    if not tbl:
        return []
        
    gainers = []
    for tr in tbl.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) >= 5:
            rank_str = tds[0].text.strip()
            if not rank_str.isdigit():
                continue
            name = tds[1].text.strip()
            rate_str = tds[4].text.strip()
            
            try:
                rate_val = float(rate_str.replace('%', '').replace('+', ''))
            except ValueError:
                continue
                
            gainers.append({
                "시장": market_name,
                "종목명": name,
                "등락률": rate_val,
                "등락률_str": rate_str
            })
    return gainers

def main():
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    print("[시스템] 네이버 금융에서 데이터를 수집 중입니다...\n")
    
    kospi_now, kospi_rate = get_index('KOSPI')
    kosdaq_now, kosdaq_rate = get_index('KOSDAQ')
    
    kospi_gainers = get_top_gainers(0, 'KOSPI')
    kosdaq_gainers = get_top_gainers(1, 'KOSDAQ')
    
    all_gainers = kospi_gainers + kosdaq_gainers
    # 일간 등락률 내림차순 정렬
    all_gainers.sort(key=lambda x: x["등락률"], reverse=True)
    top_30 = all_gainers[:30]
    
    lines = []
    lines.append("=" * 58)
    lines.append(f" 머니메이커스 시황 데이터   |   기준일: {date_str}")
    lines.append("=" * 58)
    lines.append("")
    lines.append("[지수]")
    lines.append(f"KOSPI  : {kospi_now:>10}  ({kospi_rate}%)")
    lines.append(f"KOSDAQ : {kosdaq_now:>10}  ({kosdaq_rate}%)")
    lines.append("")
    lines.append("[상승률 TOP 30]  (KOSPI+KOSDAQ 통합, 일간 등락률 내림차순)")
    
    for i, row in enumerate(top_30):
        limit = "  ★상한가후보" if row["등락률"] >= 29.0 else ""
        rate_str = row['등락률_str']
        if not rate_str.startswith('+') and not rate_str.startswith('-') and row["등락률"] > 0:
            rate_str = '+' + rate_str
        lines.append(f"{i+1:>2}. {row['종목명']:<14} ({row['시장']:<6}) {rate_str:>7}{limit}")
        
    lines.append("")
    lines.append("-" * 58)
    lines.append("※ [상승률 TOP 30] 블록 → 앱의 '특징주 / 상승률 TOP' 칸에 붙여넣기")
    lines.append("※ [지수] 등락률 → 앱의 KOSPI/KOSDAQ 등락률 칸에 입력")
    lines.append("※ 사유는 비워두면 AI가 뉴스와 엮어 채웁니다(없으면 '확인 불가'로 표기).")
    
    out = "\n".join(lines)
    print(out)
    
    # 텍스트 파일로도 저장
    fname = f"market_data.txt"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(f"\n[저장됨] {fname}")

if __name__ == "__main__":
    main()
