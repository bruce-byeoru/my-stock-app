import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
import re


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
        if len(clean_changes) == len(df):
            df['전일비'] = clean_changes

        return df
    except Exception as e:
        st.error(f"데이터를 가져오는 중 오류 발생: {e}")
        return pd.DataFrame()

# 버튼 레이아웃
col1, col2 = st.columns(2)
with col1: kospi = st.button("🔵 코스피(KOSPI) TOP 100")
with col2: kosdaq = st.button("🔴 코스닥(KOSDAQ) TOP 100")

if kospi or kosdaq:
    m_code = "0" if kospi else "1"
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

        # 열 순서 배치 (N을 첫 번째로)
        target_cols = [
            'N', '종목명', '상세페이지', '현재가', '전일비', '등락률', '시가총액', 
            'PER', 'PBR', 'EPS', '외국인비중', '외국인매매', '기관매매'
        ]
        final_df = df_raw[[c for c in target_cols if c in df_raw.columns]].copy()

        # 숫자형 변환 (스타일링 및 계산용)
        num_cols = ['현재가', '시가총액', 'PER', 'PBR', 'EPS', '외국인비중', '외국인매매', '기관매매']
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

        # 데이터프레임 렌더링
        st.dataframe(
            final_df.style.apply(apply_stock_color, subset=['전일비', '등락률']).format({
                'N': '{:d}',
                '현재가': '{:,.0f}', 
                '시가총액': '{:,.0f}', 
                'PER': '{:.2f}', 
                'PBR': '{:.2f}', 
                'EPS': '{:,.0f}',
                '외국인비중': '{:.2f}%',
                '외국인매매': '{:,.0f}',
                '기관매매': '{:,.0f}'
            }, na_rep="-"),
            use_container_width=True,
            hide_index=True,
            column_config={
                "N": st.column_config.NumberColumn("순위", width="small"),
                "종목명": st.column_config.TextColumn("종목명", pinned=True),
                "상세페이지": st.column_config.LinkColumn("상세보기", display_text="🔗 열기"),
                "등락률": st.column_config.TextColumn("등락률")
            }
        )

        st.success(f"✅ {'KOSPI' if kospi else 'KOSDAQ'} 상위 100개 종목을 불러왔습니다.")
