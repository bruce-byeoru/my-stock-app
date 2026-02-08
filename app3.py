import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
import re
import time
import base64
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager as fm
import numpy as np

try:
    from pykrx import stock
except:
    stock = None

try:
    import feedparser
except:
    feedparser = None

# .env 파일에서 환경 변수 로드
load_dotenv()

# 뉴스 기반 분석 함수
def analyze_news_sentiment(news_list, company_name):
    """뉴스 제목 기반으로 긍정/부정/중립 분류 후 DataFrame 반환"""
    positive_keywords = [
        '상승', '증가', '호황', '호전', '강세', '반등', '부양', '수급', '신규', '신사업',
        '신제품', '개선', '확대', '성장', '기대', '이익', '수익', '영업익', '실적', '강화',
        '긍정', '추천', '신고가', '호재', '수주', '매출', '증가'
    ]

    negative_keywords = [
        '하락', '감소', '악화', '부진', '약세', '침체', '불황', '적자', '손실', '급락', '폭락',
        '위기', '문제', '분쟁', '파업', '구조조정', '감원', '소송', '규제', '리콜', '부실', '매도', '우려', '악재'
    ]

    neutral_info_keywords = ['출시', '발표', '공개', '보도자료', '리뷰']

    news_data = []
    if not news_list:
        return pd.DataFrame()

    for news in news_list:
        if isinstance(news, dict):
            title = news.get('title', '')
            url = news.get('url', '')
            date = news.get('date', datetime.now().strftime('%Y-%m-%d'))
        else:
            title = str(news)
            url = ''
            date = datetime.now().strftime('%Y-%m-%d')

        t_lower = title.lower()
        sentiment = '중립'

        for neg in negative_keywords:
            if neg in t_lower:
                sentiment = '부정'
                break
        if sentiment == '중립':
            for pos in positive_keywords:
                if pos in t_lower:
                    sentiment = '긍정'
                    break

        news_data.append({
            '분류': sentiment,
            '뉴스': title,
            '링크': url,
            '날짜': date
        })

    df_news = pd.DataFrame(news_data)
    return df_news

# 투자 매력도 점수 계산 함수
def calculate_investment_score(fundamental, technical_data, stock_data):
    """
    재무, 수급, 기술적 지표를 종합하여 0~100점 사이의 투자 매력도를 산출
    Args:
        fundamental: dict with PER, PBR, ROE, EPS, foreign_ratio 등
        technical_data: dict with RSI, MA정배열 여부, MACD 등
        stock_data: DataFrame with 거래량 등
    Returns:
        dict: {total_score, grade, breakdown, message}
    """
    scores = {}
    
    # 1. 재무지표 (25점): ROE + EPS
    roe = fundamental.get('roe', 0)
    eps = fundamental.get('eps', 0)
    
    # ROE 점수 (0~15점): 10% 이상이면 만점
    roe_score = min(15, max(0, (roe / 10.0) * 15))
    
    # EPS 점수 (0~10점): 양수이면 기본점수, 1000 이상이면 만점
    if eps > 0:
        eps_score = min(10, max(5, (eps / 1000) * 10))
    else:
        eps_score = 0
    
    scores['재무지표'] = round(roe_score + eps_score, 1)
    
    # 2. 가치평가 (15점): PBR
    pbr = fundamental.get('pbr', 0)
    # PBR이 낮을수록 높은 점수 (1.0 미만이면 만점, 3.0 이상이면 0점)
    if pbr > 0:
        pbr_score = max(0, 15 * (1 - (pbr - 0.5) / 2.5))
    else:
        pbr_score = 7.5  # 데이터 없으면 중간점수
    
    scores['가치평가'] = round(pbr_score, 1)
    
    # 3. 수급분석 (30점): 외국인 보유 비율
    foreign_ratio = fundamental.get('foreign_ratio', 0)
    # 외국인 비율이 높을수록 높은 점수 (30% 이상이면 만점)
    foreign_score = min(30, (foreign_ratio / 30.0) * 30)
    
    scores['수급분석'] = round(foreign_score, 1)
    
    # 4. 기술적분석 (20점): MA 정배열 + RSI
    rsi = technical_data.get('rsi', 50)
    ma_align = technical_data.get('ma_align', False)  # MA 정배열 여부
    
    # MA 정배열 여부 (0~10점)
    ma_score = 10 if ma_align else 0
    
    # RSI 점수 (0~10점): 30~70 범위가 안전, 50 근처가 이상적
    if 40 <= rsi <= 60:
        rsi_score = 10
    elif 30 <= rsi <= 70:
        rsi_score = 7
    elif rsi < 30:  # 과매도
        rsi_score = 5
    else:  # 과매수
        rsi_score = 3
    
    scores['기술적분석'] = round(ma_score + rsi_score, 1)
    
    # 5. 모멘텀 (10점): 거래량 증가율
    vol_ratio = technical_data.get('volume_ratio', 1.0)  # 평균 대비 비율
    # 거래량이 평균보다 많으면 높은 점수 (2배 이상이면 만점)
    momentum_score = min(10, max(0, (vol_ratio - 0.5) * 20 / 1.5))
    
    scores['모멘텀'] = round(momentum_score, 1)
    
    # 총점 계산
    total_score = sum(scores.values())
    
    # 등급 부여 (A~F)
    if total_score >= 90:
        grade = 'A'
    elif total_score >= 80:
        grade = 'B'
    elif total_score >= 70:
        grade = 'C'
    elif total_score >= 60:
        grade = 'D'
    elif total_score >= 50:
        grade = 'E'
    else:
        grade = 'F'
    
    # 분석 메시지 생성
    weakest = min(scores.items(), key=lambda x: x[1])
    strongest = max(scores.items(), key=lambda x: x[1])
    
    message = f"본 종목은 {strongest[0]} 점수가 가장 높고({strongest[1]}점), "
    message += f"{weakest[0]} 점수가 낮습니다({weakest[1]}점). "
    
    if scores['수급분석'] >= 20 and scores['가치평가'] < 10:
        message += "수급은 양호하나 밸류에이션이 높아 단기 트레이딩에 적합합니다."
    elif scores['가치평가'] >= 10 and scores['기술적분석'] < 10:
        message += "가치는 저평가되었으나 기술적 신호가 약해 중장기 관점이 필요합니다."
    elif scores['기술적분석'] >= 15:
        message += "기술적 지표가 우수하여 단기 진입 타이밍으로 적합합니다."
    else:
        message += "종합적으로 균형잡힌 투자 기회를 제공합니다."
    
    return {
        'total_score': round(total_score, 1),
        'grade': grade,
        'breakdown': scores,
        'message': message
    }

# .env 파일에서 환경 변수 로드
load_dotenv()

# 뉴스 크롤링 함수
def get_company_news(company_name, max_news=30, allowed_sites=None):
    """Naver 뉴스 검색에서 회사 관련 뉴스의 제목과 링크만 가져옴.
    allowed_sites: list of domain substrings to include (예: ['mk.co.kr', 'hankyung.com'])
    """
    all_news = []
    if allowed_sites is None:
        allowed_sites = [
            'mk.co.kr', 'hankyung.com', 'sedaily.com', 'mt.co.kr', 'money.mt.co.kr',
            'edaily.co.kr', 'fnnews.com', 'asiae.co.kr', 'heraldcorp.com', 'heraldbiz.com',
            'ajunews.com', 'dt.co.kr', 'etnews.com', 'n.news.naver.com', 'news.naver.com'
        ]
    
    # 경조사, 광고, 무관한 키워드 (주가와 관련 없는 내용)
    exclude_keywords = [
        '빙부상', '부음', '부고', '조의', '애도', '서거', '별세', '영결식', '발인', '장례', '조문',
        '구독', '이벤트', '프로모션', '할인', '세일', '쿠폰',
        '채용', '인턴', '경력직', '신입', '구인', '입사',
        '야구', '축구', '농구', '배구', '골프', '테니스',
        '드라마', '영화', '예능', '배우', '가수',
        '광고 접수', '보도자료', 'PR)', '(광고)'
    ]
    
    # 일반 경제/정치 뉴스 (종목과 무관)
    generic_keywords = [
        '커지는 추경', '예산 시즌', '기획처', '정부', '정책',
        '아침의 주요기사', '주요기사', '오늘의', '이번주',
    ]

    try:
        import urllib.parse
        query = urllib.parse.quote(company_name)
        url = f"https://search.naver.com/search.naver?where=news&query={query}&sm=tab_opt&sort=0&pd=30"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        }

        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 회사명 변형 리스트 (유연한 매칭)
        company_variations = [company_name]
        if '전자' in company_name and len(company_name) > 4:
            company_variations.append(company_name.replace('전자', ''))
        if '자동차' in company_name:
            company_variations.append(company_name.replace('자동차', '차'))
        
        # 모든 링크를 순회하면서 뉴스 기사로 보이는 것만 수집
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            if len(all_news) >= max_news:
                break

            try:
                title = link.get_text(strip=True)
                href = link.get('href', '')
                
                # 1. 기본 필터: 최소 길이, http 시작
                if len(title) < 15 or len(title) > 100:
                    continue
                    
                if not (href.startswith('http://') or href.startswith('https://')):
                    continue
                
                # 2. 네이버 쇼핑/스토어/광고 제외
                if any(x in href for x in ['shopping.naver', 'smartstore.naver', 'ad.naver', 
                                           'help.naver', 'news.naver.com/main', 'promotion']):
                    continue
                
                # 3. 허용된 뉴스 사이트 필터 (사용자 요구에 따라 특정 언론사만 허용)
                # 네이버 뉴스 링크의 경우 office 파라미터로 언론사 확인
                is_news_site = any(site in href for site in allowed_sites)
                
                # 네이버 뉴스 링크인 경우 추가 체크 (언론사 상관없이 허용 - 나중에 뉴스 제목으로 필터)
                if 'n.news.naver.com' in href or 'news.naver.com' in href:
                    is_news_site = True
                
                if not is_news_site:
                    continue
                
                # 4. 경조사/광고 키워드 제외 (이것만 엄격하게)
                if any(kw in title for kw in exclude_keywords):
                    continue
                
                # 5. 일반 경제 뉴스 제외는 완화 (너무 많이 걸러지므로)
                # 단, 명확히 무관한 것만 제외
                if '아침의 주요기사' in title or '오늘의 주요' in title:
                    continue
                
                # 6. 회사명 체크는 선택적으로 (우선순위 부여, 필수 아님)
                # 회사명이 있으면 우선 수집, 없어도 일단 수집
                
                # 7. 중복 체크
                if any(n['title'] == title for n in all_news):
                    continue
                
                # 8. 회사명 포함 여부로 우선순위 매기기
                has_company_name = any(var in title for var in company_variations)
                
                # 회사명이 있는 뉴스를 먼저 추가
                all_news.append({
                    'title': title, 
                    'url': href,
                    'priority': 1 if has_company_name else 2
                })

            except Exception:
                continue

    except Exception as e:
        print(f"뉴스 크롤링 오류: {e}")
        return []

    # 우선순위로 정렬 (회사명 포함된 것 먼저)
    all_news.sort(key=lambda x: x.get('priority', 2))
    
    # priority 키 제거 후 반환
    result = [{'title': n['title'], 'url': n['url']} for n in all_news[:max_news]]
    return result

    negative_keywords = [
        '하락', '감소', '악화', '부진', '약세', '침체', '불황', '적자',
        '손실', '하한가', '급락', '폭락', '위기', '위험', '문제', '분쟁',
        '파업', '구조조정', '감원', '폐업', '철수', '소송', '적발',
        '제재', '규제', '제한', '금지', '제조', '결함', '리콜', '부실',
        '매도', '약세', '우려', '악재', '손절', '공매', '조정', '하향'
    ]
    
    # 중립(일반 정보/제품 출시 등)으로 판단할 키워드
    neutral_info_keywords = ['출시', '출시한다', '출시 예정', '공개', '발표', '업데이트', '업그레이드', '런칭', '리뷰']
    
    news_data = []
    
    if not news_list:
        return pd.DataFrame()
    
    for news in news_list:
        title = news['title'].lower()
        sentiment = "중립"

        # 우선 부정/긍정 키워드 체크
        for neg_kw in negative_keywords:
            if neg_kw in title:
                sentiment = "부정"
                break

        if sentiment == "중립":
            for pos_kw in positive_keywords:
                if pos_kw in title:
                    sentiment = "긍정"
                    break

        # 제품 출시/일반 공지 등은 기본적으로 중립 처리하되,
        # 동시에 긍정/부정 키워드가 포함되면 그 감정을 우선 적용
        if sentiment == "중립":
            for info_kw in neutral_info_keywords:
                if info_kw in title:
                    sentiment = "중립"
                    break
        
        news_data.append({
            '분류': sentiment,
            '뉴스': news.get('title', '') if isinstance(news, dict) else news['title'],
            '링크': news.get('url', '') if isinstance(news, dict) else news['url'],
            '날짜': news.get('date', datetime.now().strftime('%Y-%m-%d')) if isinstance(news, dict) else datetime.now().strftime('%Y-%m-%d')
        })
    
    df_news = pd.DataFrame(news_data)
    return df_news

# 뉴스 DataFrame 기반 분석 텍스트 생성 함수
def generate_news_analysis_text(df_news):
    """뉴스 DataFrame을 받아서 분석 텍스트 생성"""
    if df_news.empty:
        return "최근 주목할 만한 뉴스가 없는 상태입니다. 기술적 신호에 집중하세요."
    
    positive = df_news[df_news['분류'] == '긍정']
    negative = df_news[df_news['분류'] == '부정']
    neutral = df_news[df_news['분류'] == '중립']
    
    pos_count = len(positive)
    neg_count = len(negative)
    neu_count = len(neutral)
    
    if pos_count > 0 and neg_count == 0:
        news_eval = f"✅ 긍정적 뉴스만 {pos_count}건 있습니다.\n\n주요 긍정 뉴스:\n"
        for i, (idx, row) in enumerate(positive.head(3).iterrows(), 1):
            news_eval += f"  {i}. {row['뉴스']}\n"
        news_eval += f"\n분석: 시장에서 긍정적 신호가 많이 포착되고 있어 조정 후 재상승 가능성이 높습니다."
    elif neg_count > 0 and pos_count == 0:
        news_eval = f"⚠️ 부정적 뉴스만 {neg_count}건 있습니다.\n\n주요 부정 뉴스:\n"
        for i, (idx, row) in enumerate(negative.head(3).iterrows(), 1):
            news_eval += f"  {i}. {row['뉴스']}\n"
        news_eval += f"\n분석: 악재가 계속되고 있어 추가 하락 위험이 높습니다. 추세 전환 신호를 주시하세요."
    elif pos_count > 0 and neg_count > 0:
        news_eval = f"🔀 긍정({pos_count}건) vs 부정({neg_count}건) 뉴스가 혼재되어 있습니다.\n\n"
        
        if pos_count > neg_count:
            news_eval += f"주요 긍정 뉴스:\n"
            for i, (idx, row) in enumerate(positive.head(2).iterrows(), 1):
                news_eval += f"  {i}. {row['뉴스']}\n"
            news_eval += f"\n분석: 긍정 뉴스가 부정 뉴스보다 많아 기술적 반등 신호와 결합하면 상승 가능성이 높습니다."
        else:
            news_eval += f"주요 부정 뉴스:\n"
            for i, (idx, row) in enumerate(negative.head(2).iterrows(), 1):
                news_eval += f"  {i}. {row['뉴스']}\n"
            news_eval += f"\n분석: 부정 뉴스가 많아서 기술적 반등도 제한적일 가능성이 높습니다."
    else:
        news_eval = f"중립적 뉴스만 {neu_count}건 있습니다. 기술적 신호를 중심으로 판단하세요."
    
    return news_eval

# 재무지표 가져오기 함수
def get_fundamental_data(code, market="KOSPI"):
    """네이버 증권 100위 리스트에서 재무지표 가져오기 (PER, PBR, ROE, 외국인비율 등)"""
    try:
        # get_market_data를 사용해 기본 정보 가져오기
        sosok = "0" if market == "KOSPI" else "1"
        
        for page in range(1, 6):
            try:
                df = get_market_data(sosok, page)
                if '상세페이지' not in df.columns:
                    continue
                
                for idx, row in df.iterrows():
                    if str(code) in str(row.get('상세페이지', '')):
                        # 기본 데이터 추출
                        per = pd.to_numeric(str(row.get('PER', 0)).replace(',', ''), errors='coerce') or 0
                        roe = pd.to_numeric(str(row.get('ROE', 0)).replace(',', '').replace('%', ''), errors='coerce') or 0
                        foreign_ratio = pd.to_numeric(str(row.get('외국인비율', 0)).replace(',', '').replace('%', ''), errors='coerce') or 0
                        current_price = pd.to_numeric(str(row.get('현재가', 0)).replace(',', ''), errors='coerce') or 0
                        
                        # 네이버 개별 페이지에서 PBR, EPS, BPS 크롤링 (캐시 사용, 디스크 캐시 추가)
                        url = f"https://finance.naver.com/item/main.naver?code={code}"
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }

                        pbr = 0
                        eps = 0
                        bps = 0

                        # 간단한 런타임 캐시 (코드 -> soup)
                        if not hasattr(get_fundamental_data, '_item_page_cache'):
                            get_fundamental_data._item_page_cache = {}

                        soup = None
                        cache_entry = get_fundamental_data._item_page_cache.get(code)
                        # 1) 런타임 캐시 우선
                        if cache_entry and (time.time() - cache_entry[0]) < 300:
                            soup = cache_entry[1]
                        else:
                            # 2) 디스크 캐시: .cache/item_pages/{code}.html (유효기간 600초)
                            cache_dir = os.path.join('.cache', 'item_pages')
                            os.makedirs(cache_dir, exist_ok=True)
                            cache_file = os.path.join(cache_dir, f"{code}.html")
                            use_disk = False
                            try:
                                if os.path.exists(cache_file):
                                    mtime = os.path.getmtime(cache_file)
                                    if time.time() - mtime < 600:
                                        with open(cache_file, 'rb') as f:
                                            content = f.read()
                                        soup = BeautifulSoup(content, 'html.parser')
                                        use_disk = True
                            except:
                                pass

                            if not use_disk:
                                try:
                                    time.sleep(0.15)
                                    response = requests.get(url, headers=headers, timeout=6)
                                    response.encoding = 'euc-kr'
                                    content = response.content
                                    soup = BeautifulSoup(content, 'html.parser')
                                    # write disk cache (best-effort)
                                    try:
                                        with open(cache_file, 'wb') as f:
                                            f.write(content)
                                    except:
                                        pass
                                    get_fundamental_data._item_page_cache[code] = (time.time(), soup)
                                except:
                                    soup = None

                        if soup:
                            # 정확한 테이블 기반 추출: 주요재무정보 테이블에서 최신 분기 실적 값 추출
                            try:
                                tables = soup.find_all('table')
                                for table in tables:
                                    text = table.get_text()
                                    # 주요재무정보 테이블 식별 (PER, PBR, EPS, BPS 모두 포함)
                                    if 'PER' in text and 'PBR' in text and 'EPS' in text and 'BPS' in text and '주요재무정보' in text:
                                        # 헤더 row에서 (E) 추정치 컬럼 인덱스 파악
                                        header_rows = table.find_all('tr')[:2]  # 처음 2개 row가 헤더
                                        estimated_cols = set()  # (E) 포함된 컬럼 인덱스
                                        for hr in header_rows:
                                            ths = hr.find_all('th')
                                            for idx, th in enumerate(ths):
                                                if '(E)' in th.get_text():
                                                    estimated_cols.add(idx)
                                        
                                        rows = table.find_all('tr')
                                        for row in rows:
                                            ths = row.find_all('th')
                                            tds = row.find_all('td')
                                            if ths and tds:
                                                th_text = ths[0].get_text(strip=True) if ths else ''
                                                
                                                # 최신 분기 값 찾기 함수 (추정치 제외)
                                                def get_latest_value(tds_list, skip_indices):
                                                    # 역순으로 탐색하여 추정치가 아닌 첫 유효값 반환
                                                    for i in range(len(tds_list)-1, -1, -1):
                                                        if i in skip_indices:
                                                            continue
                                                        val_text = tds_list[i].get_text(strip=True)
                                                        # 빈 값 건너뛰기
                                                        if val_text and val_text != '-':
                                                            try:
                                                                val = float(val_text.replace(',', ''))
                                                                if val != 0:  # 0 아닌 유효값
                                                                    return val
                                                            except:
                                                                pass
                                                    return 0
                                                
                                                # EPS(원) 행
                                                if 'EPS' in th_text and '(' in th_text and eps == 0:
                                                    eps = get_latest_value(tds, estimated_cols)
                                                # BPS(원) 행
                                                if 'BPS' in th_text and '(' in th_text and bps == 0:
                                                    bps = get_latest_value(tds, estimated_cols)
                                                # PBR은 테이블에서 추출하지 않음 (항상 현재가/BPS로 계산)
                                        break
                            except:
                                pass
                        
                        # BPS/PBR/EPS 추정 및 교차검증
                        # 우선순위: (1) 개별 페이지 값, (2) TOP-100 기반 계산(per->eps), (3) 추정식

                        # 1) EPS: 개별 페이지가 유효하면 사용
                        if (eps == 0 or eps is None) and per > 0 and current_price > 0:
                            try:
                                eps = float(current_price) / float(per)
                            except:
                                eps = 0

                        # 2) BPS: 개별 페이지 우선, 없으면 EPS/ROE로 추정
                        if (bps == 0 or bps is None) and eps > 0 and roe > 0:
                            try:
                                bps = float(eps) / (float(roe) / 100.0)
                            except:
                                bps = 0

                        # 3) PBR: 항상 현재가 / BPS로 계산 (테이블의 PBR은 과거 종가 기준이므로 사용 안 함)
                        if current_price > 0 and bps > 0:
                            try:
                                pbr = float(current_price) / float(bps)
                            except:
                                pbr = 0

                        # 추가 보정: 너무 극단적인 값 제거
                        try:
                            if eps and eps < 0:
                                eps = abs(eps)
                            if bps and bps < 0:
                                bps = abs(bps)
                            if pbr and pbr < 0:
                                pbr = abs(pbr)
                        except:
                            pass
                        
                        # DPS는 배당수익률이 있으면 현재가 기반으로 추정
                        dps = 0
                        try:
                            dps = float(current_price) * float(2.0) / 100.0
                        except:
                            dps = 0

                        # --- 외국인/기관 순매수량(또는 금액) 추출 시도 ---
                        def parse_korean_number(s):
                            try:
                                if s is None:
                                    return 0
                                s = str(s).strip()
                                s = s.replace(',', '').replace('\xa0', '')
                                # 단위 처리: 억, 만
                                if '억' in s:
                                    s = s.replace('억원', '').replace('억', '')
                                    return float(s) * 1e8
                                if '만' in s:
                                    s = s.replace('만', '')
                                    return float(s) * 1e4
                                # 괄호나 기타 문자 제거
                                s = re.sub(r"[^0-9\-.]", '', s)
                                if s == '' or s == '-' or s == '+':
                                    return 0
                                return float(s)
                            except:
                                return 0

                        foreign_net_buy = 0
                        inst_net_buy = 0
                        investor_data_from_page = False  # 개별 페이지에서 추출했는지 플래그

                        # 1) 먼저 TOP-리스트 row에서 후보 컬럼으로 추출 시도
                        possible_keys = ['외국인매매', '외국인순매수량', '외국인순매수', 'frgn_buy_vol', 'frgn_buy', '외국인매수']
                        for k in possible_keys:
                            try:
                                if k in row:
                                    val = row.get(k, 0)
                                    num = parse_korean_number(val)
                                    if num:
                                        foreign_net_buy = num
                                        break
                            except:
                                pass

                        possible_inst_keys = ['기관매매', '기관순매수량', '기관순매수', 'inst_buy_vol', 'inst_buy', '기관매수']
                        for k in possible_inst_keys:
                            try:
                                if k in row:
                                    val = row.get(k, 0)
                                    num = parse_korean_number(val)
                                    if num:
                                        inst_net_buy = num
                                        break
                            except:
                                pass

                        # 2) 투자자별 매매동향 테이블에서 최신 거래일의 외국인/기관 순매수 추출
                        try:
                            if soup is not None:
                                tables = soup.find_all('table')
                                # 헤더에 '날짜', '외국인', '기관'이 있는 테이블 찾기
                                for table in tables:
                                    header_row = table.find('tr')
                                    if header_row:
                                        ths = [th.get_text(strip=True) for th in header_row.find_all('th')]
                                        # 투자자별 매매동향 테이블 식별
                                        if '외국인' in ths and '기관' in ths and '날짜' in ths:
                                            # 헤더 인덱스 파악
                                            try:
                                                foreign_idx = ths.index('외국인')
                                                inst_idx = ths.index('기관')
                                            except:
                                                continue
                                            
                                            # 첫 번째 데이터 row(최신 거래일) 찾기
                                            rows = table.find_all('tr')
                                            for row in rows[1:]:  # 헤더 스킵
                                                # th와 td를 모두 합쳐서 cell 배열 생성
                                                ths_in_row = row.find_all('th')
                                                tds = row.find_all('td')
                                                cells = ths_in_row + tds
                                                
                                                if len(cells) > max(foreign_idx, inst_idx):
                                                    # 외국인 순매수
                                                    if foreign_net_buy == 0:
                                                        try:
                                                            f_text = cells[foreign_idx].get_text(strip=True)
                                                            foreign_net_buy = parse_korean_number(f_text)
                                                            investor_data_from_page = True
                                                        except:
                                                            pass
                                                    # 기관 순매수
                                                    if inst_net_buy == 0:
                                                        try:
                                                            i_text = cells[inst_idx].get_text(strip=True)
                                                            inst_net_buy = parse_korean_number(i_text)
                                                            investor_data_from_page = True
                                                        except:
                                                            pass
                                                    # 최신일 하나만 추출하면 종료
                                                    if foreign_net_buy != 0 or inst_net_buy != 0:
                                                        break
                                            break
                        except:
                            pass

                        # 3) 개별 페이지에서 추출한 데이터가 아니고, 값의 단위가 '주수'로 보이는 소규모 숫자면 현재가로 환산 시도
                        # (개별 페이지 투자자 매매동향 테이블은 이미 주 단위이므로 환산 불필요)
                        try:
                            if not investor_data_from_page and foreign_net_buy and abs(foreign_net_buy) < 1e6 and current_price > 0:
                                foreign_net_buy = foreign_net_buy * float(current_price)
                        except:
                            pass
                        try:
                            if not investor_data_from_page and inst_net_buy and abs(inst_net_buy) < 1e6 and current_price > 0:
                                inst_net_buy = inst_net_buy * float(current_price)
                        except:
                            pass

                        fundamental_data = {
                            'PER': per,
                            'PBR': pbr,
                            'ROE': roe,
                            'EPS': eps,
                            'BPS': bps,
                            'DIV': 2.0,  # 기본값
                            'DPS': dps,
                            'current_price': current_price,
                            'foreign_ratio': foreign_ratio,
                            'foreign_net_buy': int(foreign_net_buy) if foreign_net_buy else 0,
                            'inst_net_buy': int(inst_net_buy) if inst_net_buy else 0,
                            'date': datetime.now().strftime('%Y%m%d')
                        }
                        
                        return fundamental_data
            except:
                continue
        
        return None
        
    except Exception as e:
        return None

# 투자가치 분석 및 점수 계산 함수
def analyze_investment_value(fundamental, technical_signals, current_price):
    """재무지표, 기술적 신호, 외국인/기관 매매를 종합해서 투자가치 분석 및 점수 계산 (0~100점)"""
    
    scores = {
        'fundamental': 0,    # 재무지표 (25점): ROE, EPS
        'valuation': 0,      # 가치평가 (15점): PBR
        'supply_demand': 0,  # 수급분석 (30점): 외국인/기관
        'technical': 0,      # 기술적 분석 (20점): MA, RSI
        'momentum': 0        # 모멘텀 (10점): 거래량
    }
    
    analysis_text = "## 📊 투자 매력도 점수 분석\n\n"
    
    # 1. 재무지표 점수 (25점): ROE + EPS
    fund_score = 0
    if fundamental:
        # ROE 점수 (15점) - 높을수록 좋음
        roe = fundamental.get('ROE', 0)
        if roe >= 20:
            fund_score += 15
        elif roe >= 15:
            fund_score += 12
        elif roe >= 10:
            fund_score += 9
        elif roe >= 5:
            fund_score += 5
        else:
            fund_score += 2
        
        # EPS 점수 (10점) - 양수이고 높을수록 좋음
        eps = fundamental.get('EPS', 0)
        if eps >= 10000:
            fund_score += 10
        elif eps >= 5000:
            fund_score += 8
        elif eps >= 2000:
            fund_score += 6
        elif eps >= 500:
            fund_score += 4
        elif eps > 0:
            fund_score += 2
        else:
            fund_score += 0
    
    scores['fundamental'] = fund_score
    
    # 2. 가치평가 점수 (15점): PBR
    val_score = 0
    if fundamental:
        pbr = fundamental.get('PBR', 999)
        if pbr > 0:
            # PBR이 낮을수록 높은 점수 (1.0 미만이면 만점, 3.0 이상이면 0점)
            if pbr < 0.8:
                val_score = 15  # 매우 저평가
            elif pbr < 1.0:
                val_score = 13  # 저평가
            elif pbr < 1.5:
                val_score = 10  # 적정
            elif pbr < 2.0:
                val_score = 7   # 약간 고평가
            elif pbr < 3.0:
                val_score = 4   # 고평가
            else:
                val_score = 1   # 매우 고평가
    
    scores['valuation'] = val_score
    
    # 3. 수급분석 점수 (30점): 외국인 + 기관
    supply_score = 0
    if fundamental:
        # 외국인 보유비율 (15점) - 높을수록 좋음
        foreign_ratio = fundamental.get('foreign_ratio', 0)
        if foreign_ratio >= 30:
            supply_score += 15
        elif foreign_ratio >= 20:
            supply_score += 12
        elif foreign_ratio >= 10:
            supply_score += 8
        elif foreign_ratio >= 5:
            supply_score += 5
        else:
            supply_score += 2
        
        # 외국인 + 기관 순매수 (15점)
        foreign_net_buy = fundamental.get('foreign_net_buy', 0)
        inst_net_buy = fundamental.get('inst_net_buy', 0)
        total_net_buy = foreign_net_buy + inst_net_buy
        
        if total_net_buy > 2000000000:  # 20억 이상 순매수
            supply_score += 15
        elif total_net_buy > 500000000:  # 5억 이상
            supply_score += 12
        elif total_net_buy > 100000000:  # 1억 이상
            supply_score += 9
        elif total_net_buy > 0:
            supply_score += 6
        elif total_net_buy > -100000000:
            supply_score += 3
        else:
            supply_score += 0
    
    scores['supply_demand'] = supply_score
    
    # 4. 기술적분석 점수 (20점): MA 정배열 + RSI
    tech_score = 0
    if technical_signals:
        # MA 정배열 점수 (10점)
        ma_alignment = technical_signals.get('ma_alignment', 'mixed')
        if ma_alignment == 'bullish':
            tech_score += 10
        elif ma_alignment == 'neutral':
            tech_score += 5
        else:
            tech_score += 0
        
        # RSI 점수 (10점): 30~70 범위가 안전, 40~60이 이상적
        rsi = technical_signals.get('rsi', 50)
        if 40 <= rsi <= 60:
            tech_score += 10  # 최적 구간
        elif 30 <= rsi < 40 or 60 < rsi <= 70:
            tech_score += 7   # 양호 구간
        elif rsi < 30:  # 과매도
            tech_score += 5   # 반등 기회
        else:  # 과매수
            tech_score += 3   # 조정 위험
    
    scores['technical'] = tech_score
    
    # 5. 모멘텀 점수 (10점): 거래량 증가율
    momentum_score = 0
    if technical_signals:
        vol_ratio = technical_signals.get('volume_ratio', 1.0)  # 평균 대비 비율
        # 거래량이 평균보다 많으면 높은 점수
        if vol_ratio >= 2.0:
            momentum_score = 10  # 2배 이상
        elif vol_ratio >= 1.5:
            momentum_score = 8
        elif vol_ratio >= 1.2:
            momentum_score = 6
        elif vol_ratio >= 1.0:
            momentum_score = 4
        elif vol_ratio >= 0.8:
            momentum_score = 2
        else:
            momentum_score = 0
    
    scores['momentum'] = momentum_score
    
    # 총점 계산
    total_score = sum(scores.values())
    
    # 등급 부여 (A/B/C/D/E/F) - 90점 이상 A, 80점 이상 B, 70점 이상 C, 60점 이상 D, 50점 이상 E, 50점 미만 F
    if total_score >= 90:
        grade = 'A'
        recommendation = "🟢 **A등급** - 매수 적극 권장"
        invest_opinion = "모든 지표가 우수하며 투자 매력도가 매우 높습니다."
    elif total_score >= 80:
        grade = 'B'
        recommendation = "🟢 **B등급** - 매수 권장"
        invest_opinion = "대부분의 지표가 양호하며 투자 가치가 높습니다."
    elif total_score >= 70:
        grade = 'C'
        recommendation = "🟡 **C등급** - 보유 또는 매수 검토"
        invest_opinion = "전반적으로 양호한 수준이나 일부 보완이 필요합니다."
    elif total_score >= 60:
        grade = 'D'
        recommendation = "🟡 **D등급** - 중립, 신중한 접근"
        invest_opinion = "긍정/부정 신호가 혼재되어 신중한 판단이 필요합니다."
    elif total_score >= 50:
        grade = 'E'
        recommendation = "🟠 **E등급** - 관망 권장"
        invest_opinion = "부정적 신호가 우세하여 추가 하락 가능성이 있습니다."
    else:
        grade = 'F'
        recommendation = "🔴 **F등급** - 투자 부적합"
        invest_opinion = "다수의 부정적 신호로 투자를 권장하지 않습니다."
    
    # 강점/약점 분석
    weakest = min(scores.items(), key=lambda x: x[1])
    strongest = max(scores.items(), key=lambda x: x[1])
    
    category_names = {
        'fundamental': '재무지표',
        'valuation': '가치평가',
        'supply_demand': '수급분석',
        'technical': '기술적분석',
        'momentum': '모멘텀'
    }
    
    # 상세 분석 텍스트
    analysis_text += f"### 종합 평가: {recommendation}\n"
    analysis_text += f"**총점: {total_score}/100점 (등급: {grade})**\n\n"
    analysis_text += f"{invest_opinion}\n\n"
    
    analysis_text += f"**강점**: {category_names[strongest[0]]} ({strongest[1]}점) | "
    analysis_text += f"**약점**: {category_names[weakest[0]]} ({weakest[1]}점)\n\n"
    
    # 투자 전략 제안
    if scores['supply_demand'] >= 20 and scores['valuation'] < 10:
        analysis_text += "💡 **전략**: 수급은 양호하나 밸류에이션이 높아 **단기 트레이딩**에 적합합니다.\n\n"
    elif scores['valuation'] >= 10 and scores['technical'] < 10:
        analysis_text += "💡 **전략**: 가치는 저평가되었으나 기술적 신호가 약해 **중장기 관점**이 필요합니다.\n\n"
    elif scores['technical'] >= 15:
        analysis_text += "💡 **전략**: 기술적 지표가 우수하여 **단기 진입 타이밍**으로 적합합니다.\n\n"
    else:
        analysis_text += "💡 **전략**: 종합적으로 균형잡힌 접근이 필요합니다.\n\n"
    
    analysis_text += "---\n\n"
    analysis_text += "### 📈 카테고리별 상세 점수\n\n"
    analysis_text += f"1. **재무지표 (ROE, EPS)**: {scores['fundamental']}/25점\n"
    analysis_text += f"2. **가치평가 (PBR)**: {scores['valuation']}/15점\n"
    analysis_text += f"3. **수급분석 (외국인/기관)**: {scores['supply_demand']}/30점\n"
    analysis_text += f"4. **기술적분석 (MA, RSI)**: {scores['technical']}/20점\n"
    analysis_text += f"5. **모멘텀 (거래량)**: {scores['momentum']}/10점\n\n"
    
    # 재무지표 상세
    if fundamental:
        analysis_text += "---\n\n"
        analysis_text += "### 💰 재무지표 상세\n\n"
        analysis_text += f"- **PER** (주가수익비율): {fundamental['PER']:.2f}배\n"
        analysis_text += f"  → {'낮음 (저평가)' if fundamental['PER'] < 15 else '높음 (고평가)' if fundamental['PER'] > 25 else '적정'}\n\n"
        
        analysis_text += f"- **PBR** (주가순자산비율): {fundamental['PBR']:.2f}배\n"
        analysis_text += f"  → {'낮음 (저평가)' if fundamental['PBR'] < 1.0 else '높음 (고평가)' if fundamental['PBR'] > 2.0 else '적정'}\n\n"
        
        analysis_text += f"- **ROE** (자기자본이익률): {fundamental['ROE']:.2f}%\n"
        analysis_text += f"  → {'우수' if fundamental['ROE'] >= 15 else '양호' if fundamental['ROE'] >= 10 else '보통' if fundamental['ROE'] >= 5 else '낮음'}\n\n"
        
        analysis_text += f"- **배당수익률**: {fundamental['DIV']:.2f}%\n"
        analysis_text += f"  → {'높음' if fundamental['DIV'] >= 3 else '보통' if fundamental['DIV'] >= 1.5 else '낮음'}\n\n"
        
        analysis_text += f"- **EPS** (주당순이익): {fundamental['EPS']:,.0f}원\n"
        analysis_text += f"- **BPS** (주당순자산): {fundamental['BPS']:,.0f}원\n"
        analysis_text += f"- **DPS** (주당배당금): {fundamental['DPS']:,.0f}원\n\n"
        
        # 외국인/기관 매매 정보
        analysis_text += f"- **외국인 보유비율**: {fundamental.get('foreign_ratio', 0):.2f}%\n"
        analysis_text += f"  → {'매우 높음 (신뢰도 ↑)' if fundamental.get('foreign_ratio', 0) >= 30 else '높음' if fundamental.get('foreign_ratio', 0) >= 20 else '보통' if fundamental.get('foreign_ratio', 0) >= 10 else '낮음'}\n\n"
        
        foreign_net = fundamental.get('foreign_net_buy', 0)
        analysis_text += f"- **외국인 순매수**: {foreign_net:,.0f}원\n"
        analysis_text += f"  → {'강한 매수세' if foreign_net > 1000000000 else '순매수' if foreign_net > 0 else '순매도' if foreign_net > -1000000000 else '강한 매도세'}\n\n"
        
        inst_net = fundamental.get('inst_net_buy', 0)
        analysis_text += f"- **기관 순매수**: {inst_net:,.0f}원\n"
        analysis_text += f"  → {'강한 매수세' if inst_net > 1000000000 else '순매수' if inst_net > 0 else '순매도' if inst_net > -1000000000 else '강한 매도세'}\n\n"
        
        # 투자가치 판단
        analysis_text += "---\n\n"
        analysis_text += "### 🎯 투자가치 종합 판단\n\n"
        
        if fundamental['PBR'] < 1.0 and fundamental['ROE'] > 10:
            analysis_text += "✅ **저평가 + 높은 수익성**: 현재 주가가 순자산 대비 저평가되어 있고, 자기자본이익률도 우수하여 **가치투자 관점에서 매력적**입니다.\n\n"
        elif fundamental['PER'] < 15 and fundamental['DIV'] >= 2:
            analysis_text += "✅ **저 PER + 높은 배당**: 수익 대비 주가가 낮고 배당수익률도 높아 **안정적 투자처**로 적합합니다.\n\n"
        elif fundamental['PBR'] > 2.0 and fundamental['PER'] > 25:
            analysis_text += "⚠️ **고평가 위험**: 주가가 순자산과 수익 대비 높게 형성되어 있어 **추가 상승보다는 조정 위험**이 있습니다.\n\n"
        else:
            analysis_text += "📊 **적정 수준**: 재무지표가 전반적으로 적정 수준이며, 기술적 신호와 뉴스를 함께 고려한 투자 판단이 필요합니다.\n\n"
    
    return {
        'total_score': total_score,
        'scores': scores,
        'recommendation': recommendation,
        'analysis_text': analysis_text
    }

# 일봉 차트 및 기술분석 함수
def get_ohlcv_and_analysis(code, company_name, current_price, market="KOSPI"):
    """pykrx로 일봉 데이터 가져오고 분석"""
    try:
        if stock is None:
            return None, "pykrx 라이브러리를 설치하지 못했습니다. pip install pykrx를 실행하세요.", pd.DataFrame()
        
        # 최근 180일 데이터 가져오기
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=180)).strftime('%Y%m%d')
        
        df = stock.get_market_ohlcv(start_date, end_date, code)
        
        if df is None or len(df) == 0:
            return None, "차트 데이터를 가져올 수 없습니다.", pd.DataFrame()
        
        df = df.sort_index()
        
        # 이동평균선 계산
        df['MA5'] = df['종가'].rolling(window=5).mean()
        df['MA20'] = df['종가'].rolling(window=20).mean()
        df['MA60'] = df['종가'].rolling(window=60).mean()
        
        # 볼린저밴드 계산 (20일 이동평균, 표준편차 2배)
        df['BB_MA20'] = df['종가'].rolling(window=20).mean()
        df['BB_STD'] = df['종가'].rolling(window=20).std()
        df['BB_UPPER'] = df['BB_MA20'] + (df['BB_STD'] * 2)
        df['BB_LOWER'] = df['BB_MA20'] - (df['BB_STD'] * 2)
        
        # RSI 계산 (14일)
        delta = df['종가'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # MACD 계산
        df['EMA12'] = df['종가'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['종가'].ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD'] - df['Signal']
        
        # 최근 60개 데이터만 사용 (최근 3개월)
        df_recent = df.tail(60).copy()
        
        # matplotlib 한글 폰트 설정
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 차트 그리기
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), gridspec_kw={'height_ratios': [3, 1]})
        
        # 캔들차트 그리기
        width = 0.6
        for idx, (date, row) in enumerate(df_recent.iterrows()):
            open_p = row['시가']
            close_p = row['종가']
            high_p = row['고가']
            low_p = row['저가']
            
            color = 'red' if close_p >= open_p else 'blue'
            
            # 고가-저가 선
            ax1.plot([idx, idx], [low_p, high_p], color=color, linewidth=1)
            
            # 캔들
            height = abs(close_p - open_p)
            bottom = min(open_p, close_p)
            ax1.bar(idx, height, width=width, bottom=bottom, color=color, alpha=0.8)
        
        # 이동평균선 그리기
        ax1.plot(range(len(df_recent)), df_recent['MA5'], label='MA5', color='green', linewidth=2)
        ax1.plot(range(len(df_recent)), df_recent['MA20'], label='MA20', color='red', linewidth=2)
        ax1.plot(range(len(df_recent)), df_recent['MA60'], label='MA60', color='orange', linewidth=2)
        
        # 볼린저밴드 그리기
        ax1.fill_between(range(len(df_recent)), df_recent['BB_UPPER'], df_recent['BB_LOWER'], 
                         alpha=0.1, color='purple', label='Bollinger Band')
        ax1.plot(range(len(df_recent)), df_recent['BB_UPPER'], color='purple', linewidth=1, linestyle='--', alpha=0.5)
        ax1.plot(range(len(df_recent)), df_recent['BB_LOWER'], color='purple', linewidth=1, linestyle='--', alpha=0.5)
        
        ax1.set_title(f'{company_name} ({code}) 일봉 차트', fontsize=14, fontweight='bold')
        ax1.legend(loc='upper left')
        ax1.set_ylabel('가격(원)', fontsize=10)
        ax1.grid(True, alpha=0.3)
        
        # 거래량 차트
        for idx, (date, row) in enumerate(df_recent.iterrows()):
            color = 'red' if row['종가'] >= row['시가'] else 'blue'
            ax2.bar(idx, row['거래량'], color=color, alpha=0.6, width=width)
        
        ax2.set_ylabel('거래량', fontsize=10)
        ax2.set_xlabel('날짜', fontsize=10)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 이미지로 변환
        from io import BytesIO
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        buf.seek(0)
        chart_image = buf.getvalue()
        plt.close()
        
        # === 기술분석 데이터 추출 ===
        last_row = df_recent.iloc[-1]
        last_2_row = df_recent.iloc[-2] if len(df_recent) > 1 else last_row
        
        ma5_last = df_recent['MA5'].iloc[-1]
        ma20_last = df_recent['MA20'].iloc[-1]
        ma60_last = df_recent['MA60'].iloc[-1]
        
        rsi_last = df_recent['RSI'].iloc[-1]
        macd_last = df_recent['MACD'].iloc[-1]
        signal_last = df_recent['Signal'].iloc[-1]
        macd_hist = df_recent['MACD_Histogram'].iloc[-1]
        
        bb_upper = df_recent['BB_UPPER'].iloc[-1]
        bb_lower = df_recent['BB_LOWER'].iloc[-1]
        
        # 고점/저점 및 조정률 계산
        high_60 = df_recent['고가'].max()
        low_60 = df_recent['저가'].min()
        high_full = df['고가'].max()  # 전체 데이터에서 최고점
        
        close_price = last_row['종가']
        open_price = last_row['시가']
        
        # 고점 대비 조정률
        adjust_ratio = ((high_full - close_price) / high_full * 100) if high_full > 0 else 0
        
        # 거래량 분석
        vol_avg_20 = df_recent['거래량'].tail(20).mean()
        vol_last = last_row['거래량']
        vol_vol_ratio = (vol_last / vol_avg_20 - 1) * 100
        
        if vol_last > vol_avg_20 * 1.2:
            vol_status = "📈 증량 (강한 신호)"
            vol_interpret = f"거래량 {vol_vol_ratio:.1f}% 증가 - 추세 신뢰도 높음"
        elif vol_last > vol_avg_20:
            vol_status = "↗️ 약간 증량"
            vol_interpret = f"거래량 {vol_vol_ratio:.1f}% 증가"
        else:
            vol_status = "↘️ 감량"
            vol_interpret = f"거래량 {abs(vol_vol_ratio):.1f}% 감소 - 수익 실현 가능성"
        
        # 데드크로스/골든크로스 감지
        ma5_prev = df.iloc[-2]['MA5'] if len(df) > 1 else ma5_last
        ma20_prev = df.iloc[-2]['MA20'] if len(df) > 1 else ma20_last
        
        cross_signal = ""
        if ma5_prev <= ma20_prev and ma5_last > ma20_last:
            cross_signal = "🔺 **골든크로스 발생**: MA5가 MA20을 상향 돌파 - 매수 신호"
        elif ma5_prev >= ma20_prev and ma5_last < ma20_last:
            cross_signal = "🔻 **데드크로스 발생**: MA5가 MA20을 하향 돌파 - 매도 신호"
        
        # 추세 판단
        if close_price > ma5_last > ma20_last > ma60_last:
            trend = "💪 강한 상승"
            ma_status = "완벽한 정배열"
        elif close_price > ma20_last > ma60_last and close_price > ma5_last:
            trend = "📈 상승"
            ma_status = "양호한 정배열"
        elif close_price > ma60_last and close_price > ma20_last:
            trend = "➡️ 혼합"
            ma_status = "부분 정배열"
        elif close_price < ma20_last and close_price > ma60_last:
            trend = "⚠️ 조정 구간"
            ma_status = "조정 배열"
        else:
            trend = "📉 약세"
            ma_status = "약세 배열"
        
        # RSI 해석
        if rsi_last > 70:
            rsi_status = "🔴 과매수 (70 이상)"
        elif rsi_last > 60:
            rsi_status = "⚠️ 강한 매수 신호 (60-70)"
        elif rsi_last > 40:
            rsi_status = "⚪ 중립 (40-60)"
        elif rsi_last > 30:
            rsi_status = "💙 약한 매도 신호 (30-40)"
        else:
            rsi_status = "🔵 과매도 (30 이하)"
        
        # 볼린저밴드와 현재가의 관계
        price_range = bb_upper - bb_lower
        price_position = (close_price - bb_lower) / price_range * 100 if price_range > 0 else 50
        
        if price_position > 80:
            bb_signal = "🔴 상단 밴드 권근 (과매수)"
        elif price_position > 60:
            bb_signal = "⚠️ 상단 구간 (차익 실현 주의)"
        elif price_position < 20:
            bb_signal = "🔵 하단 밴드 권근 (과매도)"
        elif price_position < 40:
            bb_signal = "💙 하단 구간 (반등 기회)"
        else:
            bb_signal = "밴드 중심 부근 (정상 범위)"
        
        # 최근 캔들 분석
        if close_price > open_price:
            candle_type = "양봉"
        else:
            candle_type = "음봉"
        
        candle_size = abs(close_price - open_price)
        candle_avg_5 = df_recent['종가'].diff().tail(5).abs().mean()
        
        if candle_size > candle_avg_5 * 1.5:
            candle_strength = "강한 변동"
        elif candle_size < candle_avg_5 * 0.5:
            candle_strength = "약한 변동"
        else:
            candle_strength = "정상 변동"
        
        # MACD 신호
        if macd_hist > 0 and macd_last > signal_last:
            macd_signal = "🔺 상승 신호 (MACD > Signal)"
        elif macd_hist < 0 and macd_last < signal_last:
            macd_signal = "🔻 하락 신호 (MACD < Signal)"
        else:
            macd_signal = "⚪ 중립"
        
        # 추가 분석: 변동성, 지지/저항 강도
        atr = (df_recent['고가'] - df_recent['저가']).rolling(14).mean().iloc[-1]
        volatility = (atr / close_price * 100)  # 변동성 %
        
        # 고점까지 거리와 저점까지 거리
        dist_to_high = ((high_60 - close_price) / close_price * 100)
        dist_to_low = ((close_price - low_60) / low_60 * 100)
        
        # 뉴스 가져오기 (20개로 증가) - 주요 경제지만
        allowed_news_sites = [
            'mk.co.kr', 'hankyung.com', 'sedaily.com', 'mt.co.kr', 'money.mt.co.kr',
            'edaily.co.kr', 'fnnews.com', 'asiae.co.kr', 'heraldcorp.com', 'heraldbiz.com', 
            'ajunews.com', 'dt.co.kr', 'etnews.com', 'n.news.naver.com', 'news.naver.com'
        ]
        news_list = get_company_news(company_name, max_news=20, allowed_sites=allowed_news_sites)
        
        # === 단순화를 위한 미리 계산된 텍스트 ===
        # 거래량 의미 계산
        trend_direction = "상승" if close_price > ma20_last else "하락"
        vol_meaning = f"증량으로 현재 추세({trend_direction})의 신뢰도 상승" if vol_last > vol_avg_20 else "감량으로 추세 약화 신호 - 수익 실현 또는 관망 국면"
        
        # 캔들 해석 계산
        candle_direction = "상승" if close_price > open_price else "하락"
        candle_interpretation = f"큰 폭의 움직임으로 강한 신호. {candle_direction} 추세의 신뢰도 높음" if candle_size > candle_avg_5 * 1.5 else "작은 폭의 움직임으로 약한 신호. 추세 전환 신호는 아직 미약" if candle_size < candle_avg_5 * 0.5 else "정상 범위의 변동으로 일반적인 거래량"
        
        # MA 위치 계산
        ma5_pos = "위" if close_price > ma5_last else "아래"
        ma5_trend = "상승" if close_price > ma5_last else "하락"
        ma20_pos = "위" if close_price > ma20_last else "아래"
        ma20_trend = "상승" if close_price > ma20_last else "하락"
        ma60_pos = "위" if close_price > ma60_last else "아래"
        ma60_trend = "상승" if close_price > ma60_last else "하락"
        
        # RSI 추가 해석 계산
        rsi_interpretation = "과매수 권역으로 차익 실현 신호" if rsi_last > 70 else "강한 매수 상태로 상승 지속 가능" if rsi_last > 60 else "중립 구간으로 방향성 불명확" if 40 < rsi_last < 60 else "과매도 권역에 근접하여 반등 기회 즉앞" if rsi_last > 30 else "과매도 구간"
        
        # MACD 상세 설명
        macd_detail = "MACD가 신호선을 하향 돌파하며 하락 추세 강화" if macd_hist < 0 else "MACD가 신호선을 상향 돌파하며 상승 추세 시작"
        
        # 볼린저밴드 상세 설명
        bb_detail = "과매수 구간이며 밴드가 좁혀지는 추세 - 변동성 축소 신호" if price_position > 80 else "정상 구간" if 20 < price_position < 80 else "과매도 구간이며 반등 기회 증대"
        
        # 변동성 해석 계산
        volatility_interpretation = "높은 변동성: 급등락 위험이 높음. 손절과 익절 수준 미리 설정 권장" if volatility > 3 else "정상 변동성" if volatility > 1.5 else "낮은 변동성: 쏠림 현상이 나타날 수 있음"
        
        # 패턴 판단 계산
        pattern = "되돌림 조정 패턴 - 고점에서 하락 후 반등 구간" if close_price < high_60 and close_price > low_60 else "추가 상승 패턴 - 계속된 고가 경신" if close_price > high_60 else "추가 하락 패턴 - 저점 재시도 가능"
        
        # 시나리오 확률 계산
        bull_prob = "높음" if rsi_last < 40 or (close_price < ma20_last and macd_last > signal_last) else "중간" if close_price > ma60_last else "낮음"
        bear_prob = "높음" if rsi_last > 70 or (close_price > ma20_last and macd_hist < 0) else "중간" if close_price > ma60_last else "낮음"
        
        # 뉴스 평가 계산 (구체적인 분석)
        df_news = analyze_news_sentiment(news_list, company_name)
        news_eval = generate_news_analysis_text(df_news)
        
        # 신규 진입자 조언 계산
        entry_advice = f"기다림: MA20({ma20_last:,.0f}원) 이탈 후 MA60 근처 진입 추천" if close_price > ma20_last else f"매수 기회: MA60({ma60_last:,.0f}원)과 RSI 30 이하에서 양봉 형성 시 진입"
        
        # 보유자 조언 계산
        holder_advice = f"현재 수익 상황 양호. MA20({ma20_last:,.0f}원)이 지지될 때까지 홀딩" if close_price > ma20_last else f"손실 중. MA60({ma60_last:,.0f}원)이 언제 지지되는지 관찰"
        
        # RSI 신호 평가
        rsi_signal = "긍정" if rsi_last < 40 or close_price < ma60_last else "부정" if rsi_last > 70 else "중립"
        rsi_detail = "과매도" if rsi_last < 30 else "약한 매도" if rsi_last < 40 else "강한 매수" if rsi_last > 60 else "중립"
        
        # 상황 분석 계산
        situation = f"고점({high_60:,.0f}원)에서 되돌려 내려오는 중. MA20 이탈 시 MA60까지 추가 하락 가능성 증가" if close_price < ma20_last else "상승 추세 유지중. 고점 돌파 시 추가 상승 경향 가능"
        
        technical_report = f"""
## 📊 {company_name} ({code}) 상세 기술적 분석 보고서
**분석일**: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}

---

###  시장 상황 요약

**현재가**: {close_price:,.0f}원 | **추세**: {trend}
**고점 대비**: {adjust_ratio:.1f}% 조정 | **고점**: {high_full:,.0f}원 | **저점**: {low_60:,.0f}원

**⚠️ 핵심 평가**: {"상승 추세의 조정 구간 진입 - 반등 기회 주시" if close_price < ma20_last and close_price > ma60_last else "상승 추세 진행 중" if close_price > ma20_last and ma5_last > ma20_last else "하락세 강화 - 추가 하락 가능성"}

---

### 1️⃣ 이동평균선 및 추세 분석 (상세)

**배열 상태**: {ma_status}
- **MA5(초록, 5일선)**: {ma5_last:,.0f}원
- **MA20(빨강, 20일선)**: {ma20_last:,.0f}원 
- **MA60(주황, 60일선)**: {ma60_last:,.0f}원

{cross_signal if cross_signal else ''}

**이동평균선 해석**:
- 현재가가 MA5 {ma5_pos}: 단기 추세 {ma5_trend}
- 현재가가 MA20 {ma20_pos}: 중기 추세 {ma20_trend}  
- 현재가가 MA60 {ma60_pos}: 장기 추세 {ma60_trend}

**상황 분석**: {situation}

---

### 2️⃣ 보조지표 종합 분석 (RSI, MACD, 볼린저밴드)

**RSI(상대강도지수)**: {rsi_last:.1f} → {rsi_status}
- 과매수(70 이상): 수익 실현 압박 예상
- 강한 매수(60-70): 추가 상승 여력 있음
- 중립(40-60): 방향성 약함
- 약한 매도(30-40): 반등 신호 주시  
- 과매도(30 이하): 강한 반등 기회

**분석**: RSI {rsi_last:.1f}는 {rsi_interpretation}

**MACD**: {macd_signal}
- MACD값: {macd_last:.4f} / 신호선: {signal_last:.4f}
- {macd_detail}

**볼린저밴드**: {bb_signal}
- 상단: {bb_upper:,.0f}원 | 중간: {ma20_last:,.0f}원 | 하단: {bb_lower:,.0f}원
- 밴드 내 위치: {price_position:.1f}% (0%=하단, 100%=상단)
- {bb_detail}

---

### 3️⃣ 거래량 및 캔들 분석

**거래량**: {vol_status}
- 현재: {vol_last:,.0f}주 | 20일 평균: {vol_avg_20:,.0f}주 | 변화율: {vol_vol_ratio:+.1f}%

**의미**: {vol_meaning}

**캔들 분석**: {candle_type} ({candle_strength})
- 변동폭: {candle_size:,.0f}원 | 5일 평균: {candle_avg_5:,.0f}원

**해석**: {candle_interpretation}

---

### 4️⃣ 변동성 및 지지/저항 분석

**ATR 기반 변동성**: {volatility:.2f}% (하루 평균 변동폭)
- {volatility_interpretation}

**지지/저항 강도**:
- 💪 **강력 저항**: {high_60:,.0f}원 (고점)
  ├─ 돌파 시: 추가 상승 가능성 → 목표가: {high_60 + (high_60 - ma20_last):,.0f}원
  └─ 실패: 조정 재개

- ⚠️ **중요 저항/지지**: {ma20_last:,.0f}원 (MA20선)
  ├─ 이탈 시: 추세 전환 신호  
  └─ 유지: 중기 추세 지속

- 💙 **약한 지지**: {low_60:,.0f}원 (저점)
  └─ 이탈: 추가 하락 위험

---

### 5️⃣ 패턴 및 단기 시나리오

**현재 패턴**: {pattern}

**단기 시나리오 (3~5영업일)**:

**상승 시나리오** (확률 {bull_prob}):
1. 현재가 → {ma20_last:,.0f}원 (MA20) 반등
2. MA20 돌파 → {high_60:,.0f}원 (고점) 재도전
3. 고점 돌파 → {high_60 + (high_60 - low_60) * 0.5:,.0f}원 (신고가)

**하락 시나리오** (확률 {bear_prob}):
1. 현재가 → {ma20_last:,.0f}원 (MA20) 이탈
2. MA20 이탈 → {ma60_last:,.0f}원 (MA60) 추락
3. MA60 이탈 → {low_60:,.0f}원 (저점) 재시도

---

### 💼 종합 투자 의견

**📊 뉴스 기반 분석**:

{news_eval}

---

**주요 기술 신호**:
- {rsi_signal}: RSI {rsi_detail}
- ✅ 긍정: MACD {macd_signal}
- {'✅ 긍정' if close_price > ma20_last else '❌ 부정'}: 이동평균선 {ma_status}

**최종 평가**:

**보유자**:
- {holder_advice}
- 손절: {ma60_last * 0.95:,.0f}원 | 익절: {high_60 * 1.05:,.0f}원

**신규 진입자**:
- {entry_advice}

---

⚠️ **면책사항**: 본 분석은 기술적 분석 기반의 교육용 정보입니다. 실제 투자는 다각적 조사와 개인 판단 하에 진행하시기 바랍니다.
"""
        
        # 재무지표 가져오기 및 투자가치 분석 추가
        fundamental = get_fundamental_data(code, market)
        
        if fundamental:
            # 기술적 신호 구성 (모멘텀 점수용 volume_ratio 추가)
            technical_signals = {
                'rsi': rsi_last,
                'macd_signal': 'bullish' if macd_last > signal_last else 'bearish',
                'ma_alignment': 'bullish' if close_price > ma20_last > ma60_last else 
                                'bearish' if close_price < ma20_last < ma60_last else 'neutral',
                'volume_ratio': vol_last / vol_avg_20 if vol_avg_20 > 0 else 1.0
            }
            
            # 투자가치 분석 실행 (뉴스 항목 제거)
            investment_analysis = analyze_investment_value(
                fundamental, 
                technical_signals, 
                close_price
            )
            
            # 투자가치 분석을 먼저 배치하고, 그 다음에 상세 기술적 분석 추가
            analysis = investment_analysis['analysis_text'] + "\n\n---\n\n" + technical_report
        else:
            # fundamental 데이터가 없으면 기술적 분석만 표시
            analysis = technical_report
        
        return chart_image, analysis, df_news
        
    except Exception as e:
        return None, f"분석 중 오류: {str(e)}", pd.DataFrame()


# 차트 이미지 가져오기 함수
def get_chart_image(code):
    """네이버 증권에서 차트 이미지 가져오기"""
    try:
        # 네이버 차트 API endpoint
        url = f"https://finance.naver.com/item/fchart.naver?code={code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        # 페이지 요청
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'euc-kr'
        
        # HTML에서 차트 이미지 URL 추출
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 차트 이미지 찾기 (여러 ID 시도)
        img_tag = soup.find('img', {'id': 'img_chart_area'})
        
        if not img_tag:
            img_tag = soup.find('img', {'id': '_img_fr'})
        
        if img_tag and img_tag.get('src'):
            img_url = img_tag['src']
            # 상대 URL을 절대 URL로 변환
            if img_url.startswith('/'):
                img_url = 'https://finance.naver.com' + img_url
            elif not img_url.startswith('http'):
                img_url = 'https://finance.naver.com' + img_url
            
            # 이미지 다운로드
            img_response = requests.get(img_url, headers=headers, timeout=10)
            if img_response.status_code == 200:
                return img_response.content
        
        return None
    except Exception as e:
        st.error(f"차트 이미지 가져오기 중 오류: {e}")
        return None


def get_market_data(sosok, page):
    # 필요한 지표 설정 (PBR, EPS, 외국인/기관 순매수 추가)
    fields = [
        'per', 'pbr', 'eps', 'bps', 'frgn_rate', 
        'frgn_buy_vol', 'inst_buy_vol', 
        'sales', 'operating_profit', 'net_income'
    ]
    field_params = "".join([f"&fieldIds={f}" for f in fields])
    url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}{field_params}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://finance.naver.com/sise/sise_market_sum.naver'
    }

    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser', from_encoding='euc-kr')
        table = soup.find('table', {'class': 'type_2'})

        # 데이터프레임 읽기
        df = pd.read_html(StringIO(str(table)))[0]
        df = df[df['종목명'].notnull()].copy()
        df.columns = [col.strip() for col in df.columns]

        # 종목코드 및 링크 추출
        rows = table.find_all('tr')[2:]
        codes = []
        clean_changes = []
        
        for row in rows:
            tds = row.find_all('td')
            if len(tds) > 1 and tds[1].find('a'):
                # 코드 추출
                href = tds[1].find('a')['href']
                code_match = re.search(r'code=(\d+)', href)
                if code_match:
                    codes.append(code_match.group(1))
                
                # 전일비 아이콘 처리
                raw_text = tds[3].get_text(strip=True)
                num_only = re.sub(r'[^0-9]', '', raw_text)
                img = tds[3].find('img')
                prefix = ""
                if img:
                    alt = img.get('alt', '')
                    if "상승" in alt: prefix = "+"
                    elif "하락" in alt: prefix = "-"
                
                if not num_only or num_only == '0':
                    clean_changes.append("0")
                else:
                    clean_changes.append(f"{prefix}{int(num_only):,}")

        # 데이터 보정
        if len(codes) == len(df):
            df['코드'] = codes
            df['상세페이지'] = [f"https://finance.naver.com/item/main.naver?code={c}" for c in codes]
            # --- 추가: 기술분석 링크 생성 ---
            df['기술분석'] = [f"https://finance.naver.com/item/fchart.naver?code={c}" for c in codes]
            
        if len(clean_changes) == len(df):
            df['전일비'] = clean_changes

        return df
    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류 발생: {e}")
        return pd.DataFrame()

# 페이지 상단 앵커 및 스크롤 기능
st.markdown('<div id="top"></div>', unsafe_allow_html=True)

# Session state 초기화
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'list'  # list, select, detail, ranking
if 'selected_stock_code' not in st.session_state:
    st.session_state.selected_stock_code = None
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None
if 'ranking_market' not in st.session_state:
    st.session_state.ranking_market = None

# 뒤로가기 버튼 처리 (detail 모드일 때)
if st.session_state.view_mode == 'detail':
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← 목록으로 돌아가기"):
            st.session_state.view_mode = 'list'
            st.session_state.selected_stock_code = None
            st.session_state.selected_stock_name = None
            st.rerun()
    with col2:
        if st.button("📊 종목 선택하기"):
            st.session_state.view_mode = 'select'
            st.rerun()

# 뒤로가기 버튼 처리 (ranking 모드일 때)
if st.session_state.view_mode == 'ranking':
    if st.button("← 목록으로 돌아가기"):
        st.session_state.view_mode = 'list'
        st.session_state.ranking_market = None
        st.rerun()

# select 모드일 때 돌아가기
if st.session_state.view_mode == 'select':
    if st.button("← 목록으로 돌아가기"):
        st.session_state.view_mode = 'list'
        st.rerun()

# 버튼 레이아웃 (list 모드일 때만 표시)
if st.session_state.view_mode == 'list':
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    with col1: 
        if st.button("🔵 코스피(KOSPI) TOP 100", use_container_width=True):
            st.session_state.market_type = "kospi"
    with col2: 
        if st.button("🔴 코스닥(KOSDAQ) TOP 100", use_container_width=True):
            st.session_state.market_type = "kosdaq"
    with col3:
        if st.button("📊 종목 분석", use_container_width=True):
            # 현재 선택된 시장이 있으면 그대로, 없으면 코스피로 기본 설정
            if 'market_type' not in st.session_state or st.session_state.market_type is None:
                st.session_state.market_type = "kospi"
            st.session_state.view_mode = 'select'
            st.rerun()
    with col4:
        if st.button("🏆 추천순위", type="primary", use_container_width=True):
            st.session_state.view_mode = 'ranking'
            st.rerun()

# ========== SELECT 화면 (종목 선택) ==========
if st.session_state.view_mode == 'select':
    st.markdown("## 📊 종목 선택")
    
    # 코스피/코스닥 선택
    market_option = st.selectbox(
        "시장 선택",
        options=["코스피(KOSPI)", "코스닥(KOSDAQ)"],
        index=0 if st.session_state.get('market_type', 'kospi') == 'kospi' else 1,
        key='market_selector'
    )
    
    # 시장 변경 감지
    new_market = 'kospi' if '코스피' in market_option else 'kosdaq'
    if new_market != st.session_state.get('market_type'):
        st.session_state.market_type = new_market
        # 캐시 키 변경으로 데이터 새로 로드
        st.rerun()
    
    m_code = "0" if st.session_state.market_type == "kospi" else "1"
    
    # TOP 100 데이터 로드 (캐싱)
    cache_key = f"market_data_{st.session_state.market_type}"
    if cache_key not in st.session_state:
        with st.spinner("시장 데이터를 불러오는 중..."):
            df_raw = pd.concat([get_market_data(m_code, 1), get_market_data(m_code, 2)], ignore_index=True).head(100)
            st.session_state[cache_key] = df_raw
    else:
        df_raw = st.session_state[cache_key]
    
    # 종목 코드 추출
    if '코드' not in df_raw.columns or df_raw['코드'].isna().all():
        df_raw['코드'] = ""
        for idx, row in df_raw.iterrows():
            if row['상세페이지'] and 'code=' in str(row['상세페이지']):
                code = str(row['상세페이지']).split('code=')[-1]
                df_raw.at[idx, '코드'] = code
        st.session_state[cache_key] = df_raw  # 업데이트
    
    # 종목 선택 UI
    company_options = df_raw[df_raw['코드'] != ''].apply(
        lambda x: f"{x['종목명']} ({x['코드']})", axis=1
    ).tolist()
    
    if company_options:
        # 기본 선택: 1위 종목 (시가총액 1위)
        default_index = 0
        
        col1, col2 = st.columns([4, 1])
        with col1:
            selected_company = st.selectbox(
                "종목 선택 (시가총액 순위)",
                options=company_options,
                index=default_index,
                key=f'company_selector_{st.session_state.market_type}'  # 시장별 고유 key
            )
        with col2:
            if st.button("📈 분석 보기", type="primary", use_container_width=True):
                company_name = selected_company.split(" (")[0]
                company_code = selected_company.split("(")[1].rstrip(")")
                st.session_state.selected_stock_name = company_name
                st.session_state.selected_stock_code = company_code
                st.session_state.view_mode = 'detail'
                st.rerun()
    else:
        st.error("종목 데이터를 불러올 수 없습니다.")
    
    st.stop()  # select 화면 종료

market_selected = st.session_state.get("market_type", None)

if market_selected and st.session_state.view_mode == 'list':
    m_code = "0" if market_selected == "kospi" else "1"
    
    # 데이터를 session_state에 캐시하여 한 번만 로드
    cache_key = f"market_data_{market_selected}"
    
    if cache_key not in st.session_state:
        with st.spinner("최신 데이터를 불러오고 있습니다..."):
            # 1, 2페이지 합쳐서 TOP 100 생성
            df_raw = pd.concat([get_market_data(m_code, 1), get_market_data(m_code, 2)], ignore_index=True).head(100)
            st.session_state[cache_key] = df_raw
    else:
        df_raw = st.session_state[cache_key]
    
    # 데이터 처리 계속
    if True:  # 들여쓰기 유지를 위한 블록

        # 컬럼명 정리
        rename_map = {
            '외국인비율': '외국인비중',
            '외국인순매수량': '외국인매매',
            '기관순매수량': '기관매매',
        }
        df_raw.rename(columns=rename_map, inplace=True)

        # 'N' 컬럼 정수화 및 데이터 타입 정리
        df_raw['N'] = pd.to_numeric(df_raw['N'], errors='coerce').fillna(0).astype(int)
        
        # 종목 코드 추출
        df_raw['코드'] = ""
        for idx, row in df_raw.iterrows():
            if row['상세페이지'] and 'code=' in str(row['상세페이지']):
                code = str(row['상세페이지']).split('code=')[-1]
                df_raw.at[idx, '코드'] = code

        # PBR이 없거나 비어있으면 추정 계산하여 추가
        # 우선: 현재가/ BPS 기반 계산, 없으면 PER * (ROE/100) 근사식 사용
        def to_num(val):
            try:
                if pd.isna(val):
                    return None
                s = str(val)
                s = s.replace(',', '').replace('%', '').strip()
                if s == '' or s == '-' or s == 'None':
                    return None
                return float(s)
            except:
                return None

        if 'PBR' not in df_raw.columns:
            df_raw['PBR'] = None

        for idx, row in df_raw.iterrows():
            try:
                existing = to_num(row.get('PBR', None))
                if existing is not None:
                    df_raw.at[idx, 'PBR'] = existing
                    continue

                # 현재가와 BPS가 있으면 사용
                price = to_num(row.get('현재가', None))
                bps = to_num(row.get('BPS', None)) or to_num(row.get('BPS(원)', None))
                if price and bps and bps > 0:
                    df_raw.at[idx, 'PBR'] = price / bps
                    continue

                # PER 및 ROE로 근사: PBR = PER * (ROE / 100)
                per = to_num(row.get('PER', None))
                roe = to_num(row.get('ROE', None))
                if per is not None and roe is not None:
                    df_raw.at[idx, 'PBR'] = per * (roe / 100.0)
                    continue

                df_raw.at[idx, 'PBR'] = None
            except:
                df_raw.at[idx, 'PBR'] = None

        # 열 순서 배치 (PBR 추가, 컬럼 최적화)
        target_cols = [
            'N', '종목명', '현재가', '전일비', '등락률', '시가총액', 
            'PER', 'PBR', 'ROE', 'EPS', '외국인비중'
        ]
        final_df = df_raw[[c for c in target_cols if c in df_raw.columns]].copy()

        # 숫자형 변환
        num_cols = ['현재가', '시가총액', 'PER', 'PBR', 'ROE', 'EPS', '외국인비중']
        for c in num_cols:
            if c in final_df.columns:
                final_df[c] = pd.to_numeric(final_df[c].astype(str).str.replace(',', '').str.replace('%', ''), errors='coerce')

        # 등락률 기준 컬러 참조 생성
        color_ref = pd.to_numeric(final_df['등락률'].astype(str).str.replace('%', '').str.replace('+', ''), errors='coerce')

        # 스타일 정의 함수
        def apply_stock_color(column):
            return [
                'color: red' if color_ref.iloc[i] > 0 else 'color: #4DA6FF' if color_ref.iloc[i] < 0 else ''
                for i in range(len(column))
            ]

        # 데이터프레임 렌더링 (컬럼 폭 최적화로 스크롤 최소화)
        st.dataframe(
            final_df.style.apply(apply_stock_color, subset=['전일비', '등락률']).format({
                'N': '{:d}',
                '현재가': '{:,.0f}', 
                '시가총액': '{:,.0f}', 
                'PER': '{:.2f}',
                'PBR': '{:.2f}',
                'ROE': '{:.1f}', 
                'EPS': '{:,.0f}',
                '외국인비중': '{:.1f}%'
            }, na_rep="-"),
            use_container_width=True,
            hide_index=True,
            column_config={
                "N": st.column_config.NumberColumn("순위", width=50),
            "종목명": st.column_config.TextColumn("종목명", width=100),
            "현재가": st.column_config.NumberColumn("현재가", width=80),
            "전일비": st.column_config.TextColumn("전일비", width=70),
            "등락률": st.column_config.TextColumn("등락률", width=60),
            "시가총액": st.column_config.NumberColumn("시총", width=80),
            "PER": st.column_config.NumberColumn("PER", width=55),
            "PBR": st.column_config.NumberColumn("PBR", width=55),
            "ROE": st.column_config.NumberColumn("ROE", width=55),
            "EPS": st.column_config.NumberColumn("EPS", width=70),
            "외국인비중": st.column_config.NumberColumn("외국인%", width=60)
            }
        )

        st.success(f"✅ {'KOSPI' if market_selected == 'kospi' else 'KOSDAQ'} 상위 100개 종목을 불러왔습니다.")

# ========== DETAIL 화면 (종목 분석) ==========
if st.session_state.view_mode == 'detail':
    company_name = st.session_state.selected_stock_name
    company_code = st.session_state.selected_stock_code
    
    # 현재 시장 타입 가져오기
    m_code = "0" if st.session_state.get('market_type', 'kospi') == "kospi" else "1"
    cache_key = f"market_data_{st.session_state.get('market_type', 'kospi')}"
    
    # 현재가 정보 찾기
    current_price = "정보없음"
    if cache_key in st.session_state:
        df_raw = st.session_state[cache_key]
        company_row = df_raw[df_raw['코드'] == company_code]
        if len(company_row) > 0:
            current_price = company_row.iloc[0]['현재가']
    
    with st.spinner(f"📈 {company_name} 차트를 분석 중입니다..."):
        current_market = "KOSPI" if st.session_state.get('market_type', 'kospi') == 'kospi' else "KOSDAQ"
        
        # 일봉 차트 및 분석 데이터 가져오기
        chart_image, analysis_text, df_news = get_ohlcv_and_analysis(
            company_code, 
            company_name, 
            current_price, 
            market=current_market
        )
        
        if chart_image:
            st.markdown(f"## 📊 {company_name} ({company_code}) 일봉 차트 분석")

            # 차트 이미지 표시
            try:
                st.image(chart_image, width=None, caption="일봉 차트 (이동평균선: 초록5일, 빨강20일, 주황60일, 보라 볼린저밴드)")
            except Exception:
                st.image(chart_image, caption="일봉 차트 (이동평균선: 초록5일, 빨강20일, 주황60일, 보라 볼린저밴드)")

            st.divider()
            
            # 뉴스 테이블 표시
            st.markdown("### 📰 시장 뉴스")
            
            if not df_news.empty and '분류' in df_news.columns:
                positive_news = df_news[df_news['분류'] == '긍정']
                negative_news = df_news[df_news['분류'] == '부정']
                neutral_news = df_news[df_news['분류'] == '중립']
                
                tab1, tab2, tab3 = st.tabs([
                    f"✅ 긍정 ({len(positive_news)})", 
                    f"⚠️ 부정 ({len(negative_news)})", 
                    f"⚪ 중립 ({len(neutral_news)})"
                ])
                
                with tab1:
                    if not positive_news.empty:
                        for idx, row in positive_news.iterrows():
                            st.markdown(f"**[{row['뉴스']}]({row['링크']})** ({row['날짜']})")
                    else:
                        st.info("긍정적 뉴스가 없습니다.")
                
                with tab2:
                    if not negative_news.empty:
                        for idx, row in negative_news.iterrows():
                            st.markdown(f"**[{row['뉴스']}]({row['링크']})** ({row['날짜']})")
                    else:
                        st.info("부정적 뉴스가 없습니다.")
                
                with tab3:
                    if not neutral_news.empty:
                        for idx, row in neutral_news.iterrows():
                            st.markdown(f"**[{row['뉴스']}]({row['링크']})** ({row['날짜']})")
                    else:
                        st.info("중립적 뉴스가 없습니다.")
            else:
                st.info(f"📰 {company_name} 관련 주요 뉴스가 없거나, 주가와 무관한 기사만 있습니다. (경조사, 광고 등은 자동으로 제외됩니다)")
            
            st.divider()
            
            # 기술분석 텍스트
            st.markdown(analysis_text)
            
            # 하단 네비게이션
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔼 위로 가기", key="scroll_top", use_container_width=True):
                    # 종목 선택 화면으로 돌아가기
                    st.session_state.view_mode = 'select'
                    st.rerun()
            with col2:
                if st.button("← 목록으로 돌아가기", key="back_to_list", use_container_width=True):
                    st.session_state.view_mode = 'list'
                    st.session_state.selected_stock_code = None
                    st.session_state.selected_stock_name = None
                    st.rerun()
        else:
            st.error(f"❌ {company_name} 차트를 분석할 수 없습니다.\n오류: {analysis_text}")
            
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔼 위로 가기", key="scroll_top_error", use_container_width=True):
                    # 종목 선택 화면으로 돌아가기
                    st.session_state.view_mode = 'select'
                    st.rerun()
            with col2:
                if st.button("← 목록으로 돌아가기", key="back_to_list_error", use_container_width=True):
                    st.session_state.view_mode = 'list'
                    st.session_state.selected_stock_code = None
                    st.session_state.selected_stock_name = None
                    st.rerun()

# ========== RANKING 화면 (추천순위) ==========
if st.session_state.view_mode == 'ranking':
    st.header("🏆 종목 추천순위")
    st.write("투자 매력도 점수 기반 TOP 종목 순위")
    
    # 시장 선택
    if st.session_state.ranking_market is None:
        st.subheader("시장을 선택하세요")
        
        # 분석 대상 개수 선택 (시장 선택 전에 먼저 보여줌)
        st.write("**분석할 종목 개수 선택** (시가총액 상위 기준)")
        size_options = [100, 50, 30, 10]
        if 'ranking_size' not in st.session_state:
            st.session_state.ranking_size = 100
        
        selected_size = st.selectbox(
            "분석 대상 개수", 
            options=size_options, 
            index=size_options.index(st.session_state.ranking_size),
            key='ranking_size_selector',
            help="시가총액 상위 N개 종목에 대해서만 평가합니다. 숫자가 작을수록 빠릅니다."
        )
        st.session_state.ranking_size = selected_size
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔵 코스피(KOSPI) 추천순위", use_container_width=True):
                st.session_state.ranking_market = "kospi"
                st.rerun()
        with col2:
            if st.button("🔴 코스닥(KOSDAQ) 추천순위", use_container_width=True):
                st.session_state.ranking_market = "kosdaq"
                st.rerun()
        st.stop()
    
    # 선택된 시장의 데이터 가져오기
    market_selected = st.session_state.ranking_market
    m_code = "0" if market_selected == "kospi" else "1"
    selected_n = st.session_state.get('ranking_size', 100)
    
    st.subheader(f"{'🔵 코스피' if market_selected == 'kospi' else '🔴 코스닥'} 추천순위 (상위 {selected_n}개 분석)")
    
    with st.spinner("종목 점수를 계산 중입니다... (1~2분 소요)"):
        # TOP 100 데이터 가져오기
        df1 = get_market_data(m_code, 1)
        df2 = get_market_data(m_code, 2)
        
        if df1.empty or df2.empty:
            st.error("데이터를 가져올 수 없습니다.")
            st.stop()
        
        df_all = pd.concat([df1, df2], ignore_index=True).head(selected_n)
        
        # 코드 컬럼 확인 및 디버깅
        if '코드' not in df_all.columns:
            st.error(f"코드 컬럼이 없습니다. 사용 가능한 컬럼: {', '.join(df_all.columns)}")
            st.stop()
        
        st.info(f"분석 대상: {len(df_all)}개 종목")
        
        # 각 종목의 점수 계산
        ranking_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        error_count = 0
        
        total = len(df_all)
        for idx, (_, row) in enumerate(df_all.iterrows()):
            status_text.text(f"분석 중... {idx+1}/{total} (실패: {error_count})")
            progress_bar.progress((idx + 1) / total)
            
            try:
                code = row.get('코드', '')
                company_name = row.get('종목명', '')
                
                if not code or not company_name:
                    error_count += 1
                    continue
                
                # 재무지표 가져오기
                fundamental = get_fundamental_data(code, "KOSPI" if market_selected == "kospi" else "KOSDAQ")
                
                if not fundamental:
                    error_count += 1
                    continue
                
                # 기본 기술적 신호 (기술 데이터 없이도 재무만으로 점수 계산)
                technical_signals = {
                    'rsi': 50,  # 중립값
                    'macd_signal': 'neutral',
                    'ma_alignment': 'neutral',
                    'volume_ratio': 1.0  # 평균
                }
                
                close_price = fundamental.get('current_price', 0)
                
                # 기술적 데이터 가져오기 시도 (실패해도 계속 진행)
                try:
                    if stock is not None:
                        end_date = datetime.now().strftime('%Y%m%d')
                        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
                        df_price = stock.get_market_ohlcv(start_date, end_date, code)
                        
                        if df_price is not None and len(df_price) > 20:
                            df_price['MA20'] = df_price['종가'].rolling(window=20).mean()
                            df_price['MA60'] = df_price['종가'].rolling(window=60).mean()
                            
                            # RSI 계산
                            delta = df_price['종가'].diff()
                            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                            rs = gain / loss
                            df_price['RSI'] = 100 - (100 / (1 + rs))
                            
                            last_row = df_price.iloc[-1]
                            close_price = last_row['종가']
                            ma20 = df_price['MA20'].iloc[-1]
                            ma60 = df_price['MA60'].iloc[-1]
                            rsi = df_price['RSI'].iloc[-1]
                            
                            vol_avg = df_price['거래량'].tail(20).mean()
                            vol_last = last_row['거래량']
                            
                            if not pd.isna(rsi) and not pd.isna(ma20) and not pd.isna(ma60):
                                technical_signals = {
                                    'rsi': rsi,
                                    'macd_signal': 'neutral',
                                    'ma_alignment': 'bullish' if close_price > ma20 > ma60 else 
                                                    'bearish' if close_price < ma20 < ma60 else 'neutral',
                                    'volume_ratio': vol_last / vol_avg if vol_avg > 0 else 1.0
                                }
                except Exception as tech_error:
                    # 기술적 분석 실패해도 재무지표로 계속 진행
                    pass
                
                # 투자 매력도 계산
                investment_analysis = analyze_investment_value(fundamental, technical_signals, close_price if close_price > 0 else 1000)
                
                # 점수 기반 등급 부여 (사용자 지정 임계값)
                total_score_val = investment_analysis.get('total_score', 0)
                if total_score_val >= 90:
                    grade = 'A'
                elif total_score_val >= 80:
                    grade = 'B'
                elif total_score_val >= 70:
                    grade = 'C'
                elif total_score_val >= 60:
                    grade = 'D'
                elif total_score_val >= 50:
                    grade = 'E'
                else:
                    grade = 'F'
                
                ranking_data.append({
                    '순위': 0,
                    '종목명': company_name,
                    '코드': code,
                    '총점': investment_analysis['total_score'],
                    '등급': grade,
                    '재무지표': investment_analysis['scores']['fundamental'],
                    '가치평가': investment_analysis['scores']['valuation'],
                    '수급분석': investment_analysis['scores']['supply_demand'],
                    '기술적분석': investment_analysis['scores']['technical'],
                    '모멘텀': investment_analysis['scores']['momentum'],
                    'PER': fundamental.get('PER', 0),
                    'PBR': fundamental.get('PBR', 0),
                    'ROE': fundamental.get('ROE', 0),
                    'EPS': fundamental.get('EPS', 0),
                    '외국인비율': fundamental.get('foreign_ratio', 0)
                })
                    
            except Exception as e:
                error_count += 1
                continue
        
        progress_bar.empty()
        status_text.empty()
        
        if not ranking_data:
            st.error(f"순위 데이터를 계산할 수 없습니다. (분석 실패: {error_count}/{total})")
            st.warning("다음 사항을 확인해주세요:")
            st.write("- 네트워크 연결 상태")
            st.write("- pykrx 라이브러리 설치 여부")
            st.write("- 시장 운영 시간 (평일 9:00-15:30)")
            if st.button("다시 시도"):
                st.session_state.ranking_market = None
                st.rerun()
            st.stop()
        
        st.info(f"✅ 성공: {len(ranking_data)}개 종목, ❌ 실패: {error_count}개 종목")
        
        # 데이터프레임 생성 및 정렬
        df_ranking = pd.DataFrame(ranking_data)
        df_ranking = df_ranking.sort_values('총점', ascending=False).reset_index(drop=True)
        df_ranking['순위'] = range(1, len(df_ranking) + 1)
        
        # 결과 표시
        st.success(f"✅ 총 {len(df_ranking)}개 종목 분석 완료")
        
        # 테이블 표시 (컬럼 순서 조정: PER, PBR, ROE 순서로)
        display_df = df_ranking[[
            '순위', '종목명', '총점', '등급',
            '재무지표', '가치평가', '수급분석', '기술적분석', '모멘텀',
            'PER', 'PBR', 'ROE', 'EPS', '외국인비율'
        ]].copy()
        
        # 숫자 포맷팅 (간결하게)
        display_df['총점'] = display_df['총점'].apply(lambda x: f"{x:.1f}")
        display_df['PER'] = display_df['PER'].apply(lambda x: f"{x:.1f}" if x > 0 else "-")
        display_df['PBR'] = display_df['PBR'].apply(lambda x: f"{x:.2f}")
        display_df['ROE'] = display_df['ROE'].apply(lambda x: f"{x:.1f}")
        display_df['EPS'] = display_df['EPS'].apply(lambda x: f"{int(x/1000)}K" if abs(x) >= 1000 else f"{int(x)}")
        display_df['외국인비율'] = display_df['외국인비율'].apply(lambda x: f"{x:.1f}")
        
        # 컬럼명 축약
        display_df.columns = [
            '순위', '종목명', '점수', '등급',
            '재무', '가치', '수급', '기술', '모멘텀',
            'PER', 'PBR', 'ROE', 'EPS', '외국인%'
        ]
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=600,
            hide_index=True,
            column_config={
                "순위": st.column_config.NumberColumn(width="small"),
                "종목명": st.column_config.TextColumn(width="medium"),
                "점수": st.column_config.TextColumn(width="small"),
                "등급": st.column_config.TextColumn(width="small"),
                "재무": st.column_config.NumberColumn(width="small"),
                "가치": st.column_config.NumberColumn(width="small"),
                "수급": st.column_config.NumberColumn(width="small"),
                "기술": st.column_config.NumberColumn(width="small"),
                "모멘텀": st.column_config.NumberColumn(width="small"),
                "PER": st.column_config.TextColumn(width="small"),
                "PBR": st.column_config.TextColumn(width="small"),
                "ROE": st.column_config.TextColumn(width="small"),
                "EPS": st.column_config.TextColumn(width="small"),
                "외국인%": st.column_config.TextColumn(width="small")
            }
        )
        
        # 상위 10종목 하이라이트
        st.subheader("🥇 TOP 10 종목 - 상세 분석")
        st.write("투자 매력도 상위 10개 종목의 우수성 평가")
        
        top10 = df_ranking.head(10)
        for idx, row in top10.iterrows():
            # 선정 이유 분석
            reasons = []
            
            # 재무지표 평가
            if row['재무지표'] >= 20:
                reasons.append(f"✅ **우수한 재무건전성** (ROE {row['ROE']:.1f}%, EPS {row['EPS']:,.0f}원)")
            elif row['재무지표'] >= 15:
                reasons.append(f"✓ 양호한 재무지표 (ROE {row['ROE']:.1f}%)")
            
            # 가치평가 분석
            if row['가치평가'] >= 12:
                reasons.append(f"✅ **저평가 구간** (PBR {row['PBR']:.2f}배 - 상승 여력 큼)")
            elif row['가치평가'] >= 9:
                reasons.append(f"✓ 적정 밸류에이션 (PBR {row['PBR']:.2f}배)")
            
            # 수급분석 평가
            if row['수급분석'] >= 23:
                reasons.append(f"✅ **강력한 수급** (외국인 비율 {row['외국인비율']:.1f}% - 기관/외국인 매수세 우세)")
            elif row['수급분석'] >= 18:
                reasons.append(f"✓ 양호한 수급 (외국인 {row['외국인비율']:.1f}%)")
            
            # 기술적분석 평가
            if row['기술적분석'] >= 15:
                reasons.append("✅ **우수한 기술적 신호** (이평선 정배열 및 RSI 적정 구간)")
            elif row['기술적분석'] >= 12:
                reasons.append("✓ 양호한 기술적 흐름")
            
            # 모멘텀 평가
            if row['모멘텀'] >= 7:
                reasons.append("✅ **강한 모멘텀** (거래량 급증 - 시장 관심도 상승)")
            elif row['모멘텀'] >= 5:
                reasons.append("✓ 거래량 증가세")
            
            # 종합 평가
            if row['총점'] >= 85:
                summary = "🌟 **종합평가**: 재무, 밸류, 수급, 기술 전 부문 우수. 중장기 투자 최적 종목"
            elif row['총점'] >= 75:
                summary = "⭐ **종합평가**: 대부분 지표 우수. 안정적 투자 가능"
            else:
                summary = "✓ **종합평가**: 전반적으로 양호. 단기 트레이딩 유리"
            
            if not reasons:
                reasons.append("종합 점수가 상위권에 위치")
            
            with st.expander(f"**{row['순위']}위. {row['종목명']}** ({row['등급']}등급, 총점: {row['총점']:.1f}점)"):
                st.markdown(f"### 📊 선정 이유")
                for reason in reasons:
                    st.markdown(f"- {reason}")
                st.markdown(f"\n{summary}")
                
                st.markdown("---")
                st.markdown("### 📈 상세 점수")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("재무지표", f"{row['재무지표']:.1f}/25")
                    st.metric("가치평가", f"{row['가치평가']:.1f}/15")
                with col2:
                    st.metric("수급분석", f"{row['수급분석']:.1f}/30")
                    st.metric("기술적분석", f"{row['기술적분석']:.1f}/20")
                with col3:
                    st.metric("모멘텀", f"{row['모멘텀']:.1f}/10")
                    st.write(f"**PER**: {row['PER']:.1f} | **PBR**: {row['PBR']:.2f} | **ROE**: {row['ROE']:.1f}%")
                    st.write(f"**EPS**: {row['EPS']:,.0f}원 | **외국인**: {row['외국인비율']:.1f}%")
