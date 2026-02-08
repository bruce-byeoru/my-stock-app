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
    """뉴스 제목 기반으로 구체적인 긍정/부정 요소 분석"""
    # 긍정/부정 키워드: 주가에 직접적인 영향을 줄 수 있는 키워드를 우선으로 둠
    positive_keywords = [
        '상승', '증가', '호황', '호전', '강세', '반등', '부양', '부족', '수급',
        '신규', '신사업', '신제품', '개선', '확대', '성장', '기대', '이익',
        '수익', '영업익', '실적', '강화', '우호', '긍정', '추천', '역대',
        '최고', '신고가', '장점', '경쟁력', '선두', '기술', '혁신', '수익성',
        '가치', '매력', '기회', '투자', '증설', '신축', '회복', '개선', '매수',
        '전망', '전환', '차익', '좋은', '우수', '탁월', '우월', '독점', '세계',
        # 공장/생산/판매 관련 긍정 신호
        '양산', '수주', '공급', '납품', '매출', '점유율', '점유', '수요', '계약', '수출', '증가세', '호재', '성장동력', '수요증가', '양산'
    ]
    
    negative_keywords = [
        '하락', '감소', '악화', '부진', '약세', '침체', '불황', '적자',
        '손실', '하한가', '급락', '폭락', '위기', '위험', '문제', '분쟁',
        '파업', '구조조정', '감원', '폐업', '철수', '소송', '적발',
        '제재', '규제', '제한', '금지', '제조', '결함', '리콜', '부실',
        '매도', '약세', '우려', '악재', '손절', '공매', '조정', '하향'
    ]
    # 중립(일반 정보/제품 출시 등)으로 판단할 키워드
    neutral_info_keywords = ['출시', '출시한다', '출시 예정', '공개', '발표', '업데이트', '업그레이드', '런칭', '리뷰']
    
    analysis = {
        'positive': [],
        'negative': [],
        'keywords': {'positive': [], 'negative': []}
    }
    
    if not news_list:
        return analysis
    
    for news in news_list:
        title = news['title'].lower()
        
        for pos_kw in positive_keywords:
            if pos_kw in title:
                if news not in analysis['positive']:
                    analysis['positive'].append(news)
                if pos_kw not in analysis['keywords']['positive']:
                    analysis['keywords']['positive'].append(pos_kw)
                break
        
        for neg_kw in negative_keywords:
            if neg_kw in title:
                if news not in analysis['negative']:
                    analysis['negative'].append(news)
                if neg_kw not in analysis['keywords']['negative']:
                    analysis['keywords']['negative'].append(neg_kw)
                break
    
    return analysis

# .env 파일에서 환경 변수 로드
load_dotenv()

# 뉴스 크롤링 함수
def get_company_news(company_name, max_news=10):
    """Google News RSS 및 Naver 뉴스에서 회사 관련 뉴스 가져오기 (제목, URL, 날짜)"""
    all_news = []
    
    try:
        # Google News RSS 사용
        if feedparser:
            query = company_name.replace(' ', '%20')
            # Google News RSS URL (한국 뉴스, 최근 7일)
            url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
            
            feed = feedparser.parse(url)
            
            # 최대 20개까지 가져와서 필터링
            for entry in feed.entries[:20]:
                # 제목, URL, 발행 시간 추출
                title = entry.get('title', '제목 없음')
                link = entry.get('link', '#')
                published = entry.get('published', '날짜 없음')
                
                # 날짜 파싱
                try:
                    if 'published_parsed' in entry and entry.published_parsed:
                        from time import strftime
                        pub_date = strftime('%Y-%m-%d', entry.published_parsed)
                    elif 'T' in published:
                        pub_date = published.split('T')[0]
                    else:
                        pub_date = published[:10] if len(published) >= 10 else datetime.now().strftime('%Y-%m-%d')
                except:
                    pub_date = datetime.now().strftime('%Y-%m-%d')
                
                # HTML 태그 제거
                title = re.sub(r'<[^>]+>', '', title)
                
                # 중복 체크
                if title and not any(n['title'] == title for n in all_news):
                    all_news.append({
                        'title': title,
                        'url': link,
                        'date': pub_date
                    })
        
        # Naver 뉴스도 추가로 크롤링 (부족할 경우 대비)
        if len(all_news) < max_news:
            query = company_name
            url = f"https://search.naver.com/search.naver?where=news&query={query}&sort=date&pd=7"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=5)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 여러 가능한 선택자 시도
            articles = soup.find_all('div', class_=re.compile('news_wrap|newsflash_module|news_area'))[:20]
            
            for article in articles:
                if len(all_news) >= max_news:
                    break
                    
                # 제목과 링크 찾기
                title_elem = article.find('a', class_=re.compile('news_tit|title')) or article.find('a')
                # 날짜 찾기
                date_elem = article.find('span', class_=re.compile('info'))
                
                if title_elem:
                    title = title_elem.get('title', title_elem.get_text(strip=True))
                    link = title_elem.get('href', '#')
                    date = date_elem.get_text(strip=True) if date_elem else datetime.now().strftime('%Y-%m-%d')
                    
                    # 중복 체크
                    if title and not any(n['title'] == title for n in all_news):
                        all_news.append({
                            'title': title,
                            'url': link,
                            'date': date
                        })
        
        # 최소 개수 확보되면 반환
        if len(all_news) >= max_news:
            return all_news[:max_news]
        elif all_news:
            return all_news
        
        # 모두 실패시 빈 리스트 반환 (회사별 뉴스 없음)
        return []
    except Exception as e:
        # 네트워크 오류 등으로 뉴스를 가져올 수 없을 때 빈 리스트 반환
        return []

# 뉴스 기반 감정 분석 함수
def analyze_news_sentiment(news_list, company_name):
    """뉴스 제목 기반으로 구체적인 긍정/부정 요소 분석 및 DataFrame 반환"""
    positive_keywords = [
        '상승', '증가', '호황', '호전', '강세', '반등', '부양', '부족', '수급',
        '신규', '신사업', '신제품', '개선', '확대', '성장', '기대', '이익',
        '수익', '영업익', '실적', '강화', '우호', '긍정', '추천', '역대',
        '최고', '신고가', '장점', '경쟁력', '선두', '기술', '혁신', '수익성',
        '가치', '매력', '기회', '투자', '증설', '신축', '회복', '개선', '매수',
        '전망', '전환', '차익', '좋은', '우수', '탁월', '우월', '독점', '세계',
        # 공장/생산/판매 관련 긍정 신호
        '양산', '수주', '공급', '납품', '매출', '점유율', '점유', '수요', '계약', '수출', '증가세', '호재', '성장동력', '수요증가'
    ]
    
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
            '뉴스': news['title'],
            '링크': news['url'],
            '날짜': news['date']
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

# 일봉 차트 및 기술분석 함수
def get_ohlcv_and_analysis(code, company_name, current_price):
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
        
        # 뉴스 가져오기 (10개)
        news_list = get_company_news(company_name, max_news=10)
        
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
        
        analysis = f"""
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
    # 필요한 지표 설정
    fields = [
        'per', 'pbr', 'eps', 'frgn_rate', 
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
            df['상세페이지'] = [f"https://finance.naver.com/item/main.naver?code={c}" for c in codes]
            # --- 추가: 기술분석 링크 생성 ---
            df['기술분석'] = [f"https://finance.naver.com/item/fchart.naver?code={c}" for c in codes]
            
        if len(clean_changes) == len(df):
            df['전일비'] = clean_changes

        return df
    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류 발생: {e}")
        return pd.DataFrame()

# Session state 초기화
if 'view_mode' not in st.session_state:
    st.session_state.view_mode = 'list'
if 'selected_stock_code' not in st.session_state:
    st.session_state.selected_stock_code = None
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None

# 뒤로가기 버튼 처리 (detail 모드일 때)
if st.session_state.view_mode == 'detail':
    if st.button("← 목록으로 돌아가기"):
        st.session_state.view_mode = 'list'
        st.session_state.selected_stock_code = None
        st.session_state.selected_stock_name = None
        st.rerun()

# 버튼 레이아웃 (list 모드일 때만 표시)
if st.session_state.view_mode == 'list':
    col1, col2 = st.columns(2)
    with col1: 
        if st.button("🔵 코스피(KOSPI) TOP 100"):
            st.session_state.market_type = "kospi"
    with col2: 
        if st.button("🔴 코스닥(KOSDAQ) TOP 100"):
            st.session_state.market_type = "kosdaq"

market_selected = st.session_state.get("market_type", None)

if market_selected:
    m_code = "0" if market_selected == "kospi" else "1"
    with st.spinner("최신 데이터를 불러오고 있습니다..."):
        # 1, 2페이지 합쳐서 TOP 100 생성
        df_raw = pd.concat([get_market_data(m_code, 1), get_market_data(m_code, 2)], ignore_index=True).head(100)

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

        # 열 순서 배치 (분석 컬럼 추가)
        target_cols = [
            'N', '종목명', '상세페이지', '코드', '현재가', '전일비', '등락률', '시가총액', 
            'PER', 'ROE', 'EPS', '외국인비중', '외국인매매', '기관매매'
        ]
        final_df = df_raw[[c for c in target_cols if c in df_raw.columns]].copy()

        # 숫자형 변환 (스타일링 및 계산용)
        num_cols = ['현재가', '시가총액', 'PER', 'ROE', 'EPS', '외국인비중', '외국인매매', '기관매매']
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

        # view_mode에 따라 다른 화면 표시
        if st.session_state.view_mode == 'list':
            # 상단에 종목 분석 UI 배치
            company_options = df_raw[df_raw['코드'] != ''].apply(lambda x: f"{x['종목명']} ({x['코드']})", axis=1).tolist()
            
            if company_options:
                st.markdown("### 📊 종목 분석")
                col1, col2 = st.columns([4, 1])
                with col1:
                    selected_company = st.selectbox("분석할 종목 선택", options=company_options, label_visibility="collapsed", key='company_selector')
                with col2:
                    if st.button("📈 분석 보기", type="primary", use_container_width=True):
                        company_name = selected_company.split(" (")[0]
                        company_code = selected_company.split("(")[1].rstrip(")")
                        st.session_state.selected_stock_name = company_name
                        st.session_state.selected_stock_code = company_code
                        st.session_state.view_mode = 'detail'
                        st.rerun()
                
                st.divider()
            else:
                st.warning("종목 정보를 불러올 수 없습니다.")
            
            # 데이터프레임 렌더링
            st.dataframe(
                final_df.style.apply(apply_stock_color, subset=['전일비', '등락률']).format({
                    'N': '{:d}',
                    '현재가': '{:,.0f}', 
                    '시가총액': '{:,.0f}', 
                    'PER': '{:.2f}', 
                    'ROE': '{:.1f}', 
                    'EPS': '{:,.0f}',
                    '외국인비중': '{:.2f}%',
                    '외국인매매': '{:,.0f}',
                    '기관매매': '{:,.0f}'
                }, na_rep="-"),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "N": st.column_config.NumberColumn("순위", width=40),
                    "종목명": st.column_config.TextColumn("종목명", pinned=True),
                    "상세페이지": st.column_config.LinkColumn("상세", display_text="보기"),
                    "코드": None,  # 숨김
                    "등락률": st.column_config.TextColumn("등락률")
                }
            )

            st.success(f"✅ {'KOSPI' if market_selected == 'kospi' else 'KOSDAQ'} 상위 100개 종목을 불러왔습니다.")

        # detail 모드: 선택된 종목 분석 표시
        elif st.session_state.view_mode == 'detail':
            company_name = st.session_state.selected_stock_name
            company_code = st.session_state.selected_stock_code
            
            # 현재가 정보 찾기
            company_row = df_raw[df_raw['코드'] == company_code]
            if len(company_row) > 0:
                company_row = company_row.iloc[0]
                current_price = company_row['현재가']
            else:
                current_price = "정보없음"
            
            with st.spinner(f"📈 {company_name} 차트를 분석 중입니다..."):
                # 일봉 차트 및 분석 데이터 가져오기
                chart_image, analysis_text, df_news = get_ohlcv_and_analysis(company_code, company_name, current_price)
                
                if chart_image:
                    st.markdown(f"## 📊 {company_name} ({company_code}) 일봉 차트 분석")

                    # 차트 이미지 표시 (use_column_width deprecated -> width 사용)
                    try:
                        st.image(chart_image, width="stretch", caption="일봉 차트 (이동평균선: 초록5일, 빨강20일, 주황60일, 보라 볼린저밴드)")
                    except Exception:
                        # 일부 Streamlit 버전은 'stretch'를 지원하지 않을 수 있으므로 안전하게 정수 너비로 대체
                        st.image(chart_image, width=None, caption="일봉 차트 (이동평균선: 초록5일, 빨강20일, 주황60일, 보라 볼린저밴드)")

                    st.divider()
                    
                    # 뉴스 테이블 표시 (카테고리별)
                    if not df_news.empty:
                        st.markdown("### 📰 시장 뉴스")
                        
                        # 분류별로 분리
                        positive_news = df_news[df_news['분류'] == '긍정']
                        negative_news = df_news[df_news['분류'] == '부정']
                        neutral_news = df_news[df_news['분류'] == '중립']
                        
                        # 탭으로 표시
                        tab1, tab2, tab3 = st.tabs([f"✅ 긍정 ({len(positive_news)})", f"⚠️ 부정 ({len(negative_news)})", f"⚪ 중립 ({len(neutral_news)})"])
                        
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
                    
                    st.divider()
                    
                    # 기술분석 텍스트
                    st.markdown(analysis_text)
                    
                    # 하단에도 돌아가기 버튼 추가
                    st.divider()
                    if st.button("← 목록으로 돌아가기", key="back_button_bottom"):
                        st.session_state.view_mode = 'list'
                        st.session_state.selected_stock_code = None
                        st.session_state.selected_stock_name = None
                        st.rerun()
                else:
                    st.error(f"❌ {company_name} 차트를 분석할 수 없습니다.\n오류: {analysis_text}")
                    
                    # 에러 시에도 돌아가기 버튼
                    st.divider()
                    if st.button("← 목록으로 돌아가기", key="back_button_error"):
                        st.session_state.view_mode = 'list'
                        st.session_state.selected_stock_code = None
                        st.session_state.selected_stock_name = None
                        st.rerun()
