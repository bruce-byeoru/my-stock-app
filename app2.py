

import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
import re

def get_market_data(sosok, page):
    fields = ['per', 'pbr', 'eps', 'frgn_rate', 'frgn_buy_vol', 'inst_buy_vol', 'sales', 'operating_profit', 'net_income']
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
        
        # --- [추가] 종목 코드 및 링크 생성 ---
        rows = table.find_all('tr')[2:]
        codes = []
        for row in rows:
            tds = row.find_all('td')
            if len(tds) > 1 and tds[1].find('a'):
                href = tds[1].find('a')['href']
                code = re.search(r'code=(\d+)', href).group(1)
                codes.append(code)
        
        if len(codes) == len(df):
            # 클릭 시 이동할 URL 생성
            df['상세페이지'] = [f"https://finance.naver.com/item/main.naver?code={c}" for c in codes]
        # -----------------------------------

        # 전일비 화살표 처리 (기존 로직 유지)
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
                clean_changes.append(f"{prefix}{int(num_only):,}" if num_only and num_only != '0' else "0")

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
    with st.spinner("데이터를 가져오는 중..."):
        df = pd.concat([get_market_data(m_code, 1), get_market_data(m_code, 2)], ignore_index=True).head(100)

        # 컬럼 정리
        target_cols = [
            'N', '종목명', '상세페이지', '현재가', '전일비', '등락률', '시가총액', 
            'PER', 'PBR', 'EPS', '외국인비중', '외국인매매', '기관매매'
        ]
        final_df = df[[c for c in target_cols if c in df.columns]].copy()

        # 숫자 형변환
        num_cols = ['현재가', '시가총액', 'PER', 'PBR', 'EPS']
        for c in num_cols:
            if c in final_df.columns:
                final_df[c] = pd.to_numeric(final_df[c].astype(str).str.replace(',', ''), errors='coerce')

        color_ref = pd.to_numeric(final_df['등락률'].astype(str).str.replace('%', '').str.replace('+', ''), errors='coerce')

        # 데이터프레임 출력
        st.dataframe(
            final_df.style.apply(lambda x: [
                'color: red' if color_ref.loc[i] > 0 else 'color: blue' if color_ref.loc[i] < 0 else ''
                for i in x.index
            ], subset=['전일비', '등락률']).format({
                '현재가': '{:,.0f}', '시가총액': '{:,.0f}', 'PER': '{:.2f}', 'PBR': '{:.2f}'
            }, na_rep="-"),
            use_container_width=True,
            hide_index=True,
            column_config={
                "종목명": st.column_config.TextColumn("종목명", pinned=True),
                "상세페이지": st.column_config.LinkColumn(
                    "상세보기", 
                    help="클릭하면 네이버 증권으로 이동합니다",
                    display_text="🔗 열기" # 링크 주소 대신 보여줄 텍스트
                ),
            }
        )
