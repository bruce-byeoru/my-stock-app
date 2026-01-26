import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
import re

st.set_page_config(page_title="국내 증시 TOP 100 통합 분석", layout="wide")
st.title("📊 국내 증시 시가총액 TOP 100 (상세 지표 통합)")

def get_market_data(sosok, page):
    # 요청할 모든 지표 필드 ID를 파라미터에 추가
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
        
        df = pd.read_html(StringIO(str(table)))[0]
        df = df[df['종목명'].notnull()].copy()
        df.columns = [col.strip() for col in df.columns]

        rows = table.find_all('tr')[2:]
        clean_changes = []
        for row in rows:
            tds = row.find_all('td')
            if len(tds) > 3:
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
        
        if len(clean_changes) == len(df):
            df['전일비'] = clean_changes
            
        return df
    except:
        return pd.DataFrame()

# 버튼 구성
col1, col2 = st.columns(2)
with col1: kospi = st.button("🔵 코스피(KOSPI) TOP 100")
with col2: kosdaq = st.button("🔴 코스닥(KOSDAQ) TOP 100")

if kospi or kosdaq:
    m_code = "0" if kospi else "1"
    with st.spinner("모든 재무 지표와 매매 현황을 가져오는 중입니다..."):
        df = pd.concat([get_market_data(m_code, 1), get_market_data(m_code, 2)], ignore_index=True).head(100)
        
        rename_map = {
            '외국인비율': '외국인비중',
            '외국인순매수량': '외국인매매',
            '기관순매수량': '기관매매',
            '매출액': '매출',
            '당기순이익': '순이익'
        }
        df.rename(columns=rename_map, inplace=True)
        
        target_cols = [
            'N', '종목명', '현재가', '전일비', '등락률', '시가총액', 
            'PER', 'PBR', 'EPS', '외국인비중', 
            '외국인매매', '기관매매', '매출', '영업이익', '순이익'
        ]
        
        final_df = df[[c for c in target_cols if c in df.columns]].copy()

        num_cols = ['현재가', '시가총액', 'PER', 'PBR', 'EPS', '외국인비중', '외국인매매', '기관매매', '매출', '영업이익', '순이익']
        for c in num_cols:
            if c in final_df.columns:
                final_df[c] = pd.to_numeric(final_df[c].astype(str).str.replace(',', '').str.replace('%', ''), errors='coerce')

        color_ref = pd.to_numeric(final_df['등락률'].astype(str).str.replace('%', '').str.replace('+', ''), errors='coerce')

        # [수정 포인트] use_container_width=True 추가 및 컬럼 설정
        st.dataframe(
            final_df.style.apply(lambda x: [
                'color: red' if color_ref.loc[i] > 0 else 'color: blue' if color_ref.loc[i] < 0 else ''
                for i in x.index
            ], subset=['전일비', '등락률']).format({
                'N': '{:.0f}', 
                '현재가': '{:,.0f}', 
                '시가총액': '{:,.0f}', 
                'PER': '{:.2f}', 
                'PBR': '{:.2f}', 
                'EPS': '{:,.0f}',
                '외국인비중': '{:.2f}%',
                '외국인매매': '{:,.0f}',
                '기관매매': '{:,.0f}',
                '매출': '{:,.0f}',
                '영업이익': '{:,.0f}',
                '순이익': '{:,.0f}'
            }, na_rep="-"),
            use_container_width=True, # 화면 너비에 맞춰 자동 조절
            hide_index=True,
            column_config={
                "종목명": st.column_config.TextColumn("종목명", pinned=True), # 종목명 좌측 고정 (모바일 유용)
                "등락률": st.column_config.TextColumn("등락률", help="전일 대비 등락 비율"),
            }
        )

        st.success("✅ 너비가 자동 조절된 통합 지표 표입니다. (모바일 대응 완료)")