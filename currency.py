"""
실시간 환율 모니터링 대시보드
- USD/KRW 환율 실시간 모니터링
- 60일 평균 및 볼린저 밴드 기반 매수 시점 판단
- 업무용 미니멀 디자인

사용법:
  streamlit run currency.py
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import plotly.graph_objects as go

# 페이지 설정
st.set_page_config(
    page_title="환율 모니터",
    page_icon="💱",
    layout="centered",
    initial_sidebar_state="expanded"
)

# CSS 스타일 - 미니멀 & 업무용
st.markdown("""
<style>
    .main-header {
        font-size: 18px;
        font-weight: 500;
        color: #333;
        margin-bottom: 10px;
    }
    .rate-normal {
        font-size: 48px;
        font-weight: 700;
        color: #222;
        margin: 10px 0;
    }
    .rate-alert {
        font-size: 48px;
        font-weight: 700;
        color: #d32f2f;
        margin: 10px 0;
    }
    .rate-low {
        font-size: 48px;
        font-weight: 700;
        color: #0277bd;
        margin: 10px 0;
    }
    .rate-high {
        font-size: 48px;
        font-weight: 700;
        color: #d32f2f;
        margin: 10px 0;
    }
    .indicator {
        color: #d32f2f;
        font-size: 24px;
        margin-left: 10px;
    }
    .subtitle {
        font-size: 13px;
        color: #666;
        margin: 5px 0;
    }
    .metric-box {
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 4px;
        margin: 8px 0;
    }
    .metric-label {
        font-size: 12px;
        color: #666;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 16px;
        font-weight: 600;
        color: #333;
    }
</style>
""", unsafe_allow_html=True)


def get_exchange_rate_data(days=90, interval='1d'):
    """
    yfinance를 사용해 USD/KRW 환율 데이터 가져오기
    days: 가져올 일수 (기본 90일)
    interval: 데이터 간격 ('1m', '5m', '1h', '1d' 등)
    """
    try:
        # KRW=X는 USD/KRW 환율 티커
        ticker = yf.Ticker("KRW=X")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 데이터 다운로드
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if df.empty:
            return None
        
        # Close 가격만 사용
        df = df[['Close']].copy()
        df.columns = ['Rate']
        df.index = pd.to_datetime(df.index)

        # 타임스탬프를 KST(Asia/Seoul)로 변환하여 표시 시 로컬 시간이 나오도록 처리
        # yfinance는 보통 tz-aware 인덱스를 반환하지만, 경우에 따라 naive한 타임스탬프가 올 수 있으므로
        # 안전하게 처리: naive이면 UTC로 로컬라이즈한 뒤 KST로 변환, tz-aware이면 바로 변환
        try:
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert('Asia/Seoul')
            else:
                df.index = df.index.tz_convert('Asia/Seoul')
        except Exception:
            # 변환 실패 시 그대로 둠
            pass
        
        return df
    except Exception as e:
        st.error(f"데이터 가져오기 실패: {e}")
        return None


def calculate_bollinger_bands(data, window=20, num_std=2):
    """
    볼린저 밴드 계산
    """
    rolling_mean = data.rolling(window=window).mean()
    rolling_std = data.rolling(window=window).std()
    
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    
    return rolling_mean, upper_band, lower_band


def check_buy_timing(current_rate, df, lookback_days=60):
    """
    매수 시점 판단 로직
    - 60일 평균 대비 1% 이하
    - 볼린저 밴드 하단선 도달
    
    반환: (is_buy_time, reason, avg_60d, lower_band)
    """
    if df is None or len(df) < lookback_days:
        return False, "데이터 부족", None, None
    
    # 최근 60일 데이터
    recent_data = df.tail(lookback_days).copy()
    
    # 60일 평균
    avg_60d = recent_data['Rate'].mean()
    
    # 볼린저 밴드 계산 (20일 기준)
    _, _, lower_band = calculate_bollinger_bands(recent_data['Rate'], window=20, num_std=2)
    current_lower_band = lower_band.iloc[-1] if not lower_band.empty else None
    
    # 매수 시점 판단
    is_buy_time = False
    reason = []
    
    # 조건 1: 60일 평균 대비 1% 이하
    if current_rate <= avg_60d * 0.99:
        is_buy_time = True
        reason.append(f"60일 평균({avg_60d:.2f}) 대비 1% 이하")
    
    # 조건 2: 볼린저 밴드 하단선 이하
    if current_lower_band and current_rate <= current_lower_band:
        is_buy_time = True
        reason.append(f"볼린저 하단선({current_lower_band:.2f}) 도달")
    
    reason_text = ", ".join(reason) if reason else "정상 범위"
    
    return is_buy_time, reason_text, avg_60d, current_lower_band


def create_chart(df, current_rate, avg_60d, lower_band, chart_period='당일'):
    """
    엑셀 리포트 스타일의 심플한 차트 생성
    chart_period: '당일', '일별', '월별'
    """
    # 차트 기간에 따라 데이터 필터링
    if chart_period == '당일':
        # 오늘 데이터만
        today = datetime.now().date()
        plot_data = df[df.index.date == today].copy()
        if plot_data.empty:  # 당일 데이터가 없으면 최근 1일
            plot_data = df.tail(20).copy()
    elif chart_period == '일별':
        # 최근 30일
        plot_data = df.tail(30).copy()
    else:  # 월별
        # 최근 90일
        plot_data = df.tail(90).copy()
    
    fig = go.Figure()
    
    # 환율 라인
    fig.add_trace(go.Scatter(
        x=plot_data.index,
        y=plot_data['Rate'],
        mode='lines',
        name='환율',
        line=dict(color='#666', width=2),
        hovertemplate='%{y:.2f}<extra></extra>'
    ))
    
    # 60일 평균선
    if avg_60d:
        fig.add_hline(
            y=avg_60d,
            line_dash="dash",
            line_color="#999",
            annotation_text=f"60일 평균: {avg_60d:.2f}",
            annotation_position="right"
        )
    
    # 볼린저 하단선
    if lower_band:
        _, _, lower = calculate_bollinger_bands(plot_data['Rate'], window=20, num_std=2)
        fig.add_trace(go.Scatter(
            x=plot_data.index,
            y=lower,
            mode='lines',
            name='볼린저 하단',
            line=dict(color='#d32f2f', width=1, dash='dot'),
            hovertemplate='%{y:.2f}<extra></extra>'
        ))
    
    # 현재 환율 마커
    if not plot_data.empty:
        fig.add_trace(go.Scatter(
            x=[plot_data.index[-1]],
            y=[current_rate],
            mode='markers',
            name='현재',
            marker=dict(color='#d32f2f', size=10),
            hovertemplate='%{y:.2f}<extra></extra>'
        ))
    
    # 레이아웃 - 엑셀 스타일
    fig.update_layout(
        plot_bgcolor='white',
        paper_bgcolor='white',
        height=350,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=False,
        xaxis=dict(
            showgrid=True,
            gridcolor='#e0e0e0',
            gridwidth=1,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='#e0e0e0',
            gridwidth=1,
            title=None
        ),
        hovermode='x unified'
    )
    
    return fig


def main():
    """
    메인 Streamlit 앱
    """
    
    # 사이드바 - 업데이트 주기 설정
    st.sidebar.title("설정")
    
    refresh_options = {
        "10초": 10,
        "30초": 30,
        "1분": 60,
        "3분": 180,
        "5분": 300,
        "10분": 600,
        "1시간": 3600
    }
    
    selected_refresh = st.sidebar.selectbox(
        "업데이트 주기",
        options=list(refresh_options.keys()),
        index=2  # 기본값: 1분
    )
    
    refresh_interval = refresh_options[selected_refresh]
    
    # 차트 보기 주기 설정
    chart_period = st.sidebar.selectbox(
        "차트 보기 주기",
        options=["당일", "일별", "월별"],
        index=0  # 기본값: 당일
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**다음 업데이트:** {selected_refresh} 후")
    
    # 메인 컨테이너
    main_container = st.empty()
    
    while True:
        with main_container.container():
            # 헤더
            st.markdown('<div class="main-header">USD/KRW 환율</div>', unsafe_allow_html=True)
            
            # 데이터 로드 (차트 기간에 따라)
            with st.spinner('데이터 로딩 중...'):
                if chart_period == '당일':
                    # 당일 데이터는 더 짧은 인터벌로 가져오기
                    df = get_exchange_rate_data(days=5, interval='5m')  # 5분 간격
                elif chart_period == '일별':
                    df = get_exchange_rate_data(days=90, interval='1d')  # 일별
                else:  # 월별
                    df = get_exchange_rate_data(days=180, interval='1d')  # 일별
            
            if df is not None and not df.empty:
                current_rate = df['Rate'].iloc[-1]
                last_update = df.index[-1].strftime('%Y-%m-%d %H:%M')
                
                # 당일 최고/최저가 계산 (당일 데이터가 있는 경우에만 계산)
                today = datetime.now().date()
                today_data = df[df.index.date == today]
                has_today = not today_data.empty
                if has_today:
                    today_high = today_data['Rate'].max()
                    today_low = today_data['Rate'].min()
                else:
                    today_high = None
                    today_low = None
                
                # 매수 시점 판단
                is_buy_time, reason, avg_60d, lower_band = check_buy_timing(current_rate, df, lookback_days=60)
                
                # 현재 환율 표시 (당일 최저/최고가 또는 매수 시점에 따라 색상 변경)
                rate_class = "rate-normal"
                indicator = ""

                # 당일 데이터가 있을 때만 최저/최고 표시를 적용
                if has_today and today_low is not None and np.isclose(current_rate, today_low, atol=1e-6):
                    rate_class = "rate-low"
                elif has_today and today_high is not None and np.isclose(current_rate, today_high, atol=1e-6):
                    rate_class = "rate-high"
                elif is_buy_time:  # 매수 시점
                    rate_class = "rate-alert"
                    indicator = '<span class="indicator">●</span>'
                
                st.markdown(
                    f'<div class="{rate_class}">{current_rate:,.2f} {indicator}</div>',
                    unsafe_allow_html=True
                )
                
                st.markdown(f'<div class="subtitle">최종 업데이트: {last_update}</div>', unsafe_allow_html=True)
                
                # 변화량
                if len(df) >= 2:
                    prev_rate = df['Rate'].iloc[-2]
                    change = current_rate - prev_rate
                    change_pct = (change / prev_rate) * 100
                    change_color = "#d32f2f" if change >= 0 else "#2e7d32"
                    st.markdown(
                        f'<div class="subtitle" style="color: {change_color};">'
                        f'{"▲" if change >= 0 else "▼"} {abs(change):.2f} ({abs(change_pct):.2f}%)</div>',
                        unsafe_allow_html=True
                    )
                
                st.markdown("---")
                
                # 통계 정보
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                    st.markdown('<div class="metric-label">당일 최저</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="metric-value" style="color: #0277bd;">{today_low:,.2f}</div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col2:
                    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                    st.markdown('<div class="metric-label">당일 최고</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="metric-value" style="color: #d32f2f;">{today_high:,.2f}</div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with col3:
                    st.markdown('<div class="metric-box">', unsafe_allow_html=True)
                    st.markdown('<div class="metric-label">60일 평균</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="metric-value">{avg_60d:,.2f}</div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # 차트
                fig = create_chart(df, current_rate, avg_60d, lower_band, chart_period)
                st.plotly_chart(fig, width='stretch')
                
                # 상태 정보 (은밀하게)
                if is_buy_time:
                    st.caption(f"📊 {reason}")
            
            else:
                st.error("환율 데이터를 가져올 수 없습니다.")
        
        # 자동 리프레시
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
