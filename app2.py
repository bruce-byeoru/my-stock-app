# ... (앞선 크롤링 및 데이터 전처리 로직은 동일)

if kospi or kosdaq:
    m_code = "0" if kospi else "1"
    with st.spinner("데이터를 분석 중입니다..."):
        # 1. 데이터 가져오기
        df = pd.concat([get_market_data(m_code, 1), get_market_data(m_code, 2)], ignore_index=True).head(100)

        # 2. [수정] 'N' 컬럼을 정수로 변환하고 첫 번째 열로 배치
        # NaN 값이 있을 수 있으므로 fillna(0) 후 정수형 변환
        df['N'] = pd.to_numeric(df['N'], errors='coerce').fillna(0).astype(int)

        rename_map = {
            '외국인비율': '외국인비중',
            '외국인순매수량': '외국인매매',
            '기관순매수량': '기관매매',
        }
        df.rename(columns=rename_map, inplace=True)

        # 3. [수정] 열 순서 설정 ('N'을 가장 앞으로)
        target_cols = [
            'N', '종목명', '상세페이지', '현재가', '전일비', '등락률', '시가총액', 
            'PER', 'PBR', 'EPS', '외국인비중', '외국인매매', '기관매매'
        ]
        
        # 존재하는 컬럼만 필터링하여 순서 재배치
        available_cols = [c for c in target_cols if c in df.columns]
        final_df = df[available_cols].copy()

        # 숫자 형변환 (포맷팅을 위해)
        num_cols = ['현재가', '시가총액', 'PER', 'PBR', 'EPS']
        for c in num_cols:
            if c in final_df.columns:
                final_df[c] = pd.to_numeric(final_df[c].astype(str).str.replace(',', ''), errors='coerce')

        color_ref = pd.to_numeric(final_df['등락률'].astype(str).str.replace('%', '').str.replace('+', ''), errors='coerce')

        # 4. 출력
        st.dataframe(
            final_df.style.apply(lambda x: [
                'color: red' if color_ref.loc[i]
