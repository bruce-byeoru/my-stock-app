"""
저평가 우량주 발굴 앱 — KIS Open API + Naver Finance + yfinance
멀티팩터 스코어링: 저PBR + 고ROE(3년가중) + 고배당 + 고영업이익률 + 재무건전성
"""

import streamlit as st
import pandas as pd
import requests
import re
import time
import os
from datetime import datetime

import plotly.express as px
import plotly.graph_objects as go
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

load_dotenv()

st.set_page_config(
    page_title="저평가 우량주 발굴기",
    page_icon="📈",
    layout="wide",
)

KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

WEIGHTS = {
    "pbr_score":  0.20,
    "roe_score":  0.25,
    "div_score":  0.15,
    "per_score":  0.15,
    "opm_score":  0.15,
    "frgn_score": 0.10,
}


@st.cache_data(ttl=82800, show_spinner="🔑 KIS 액세스 토큰 발급 중...")
def get_kis_token(app_key: str, app_secret: str) -> str:
    url = f"{KIS_BASE_URL}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}
    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json().get("access_token", "")


def kis_headers(token, tr_id, app_key, app_secret):
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": tr_id,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_detail(ticker, token, app_key, app_secret):
    url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = kis_headers(token, "FHKST01010100", app_key, app_secret)
    params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        resp.raise_for_status()
        return resp.json().get("output", {})
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_finance(ticker, token, app_key, app_secret):
    url = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/finance/financial-ratio"
    headers = kis_headers(token, "FHPST01850000", app_key, app_secret)
    params = {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker, "fid_div_cls_code": "0"}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=8)
        resp.raise_for_status()
        output = resp.json().get("output", [])
        if isinstance(output, list) and len(output) > 0:
            return output[0]
        return {}
    except Exception as e:
        return {"error": str(e)}


_NAVER_POST_URL = "https://finance.naver.com/sise/field_submit.nhn"
_NAVER_GET_URL  = "https://finance.naver.com/sise/sise_market_sum.nhn"
_NAVER_HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/sise/sise_market_sum.nhn",
}
_FIELD_IDS = ["market_sum", "per", "pbr", "roe", "dividend", "frgn_rate"]


def _parse_page(soup, market):
    table = soup.select_one("table.type_2")
    if not table:
        return []
    rows = []
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 12:
            continue
        a = tds[1].select_one("a")
        if not a:
            continue
        name  = a.get_text(strip=True)
        href  = a.get("href", "")
        m     = re.search(r"code=(\d{6})", href)
        if not m:
            continue
        ticker = m.group(1)

        def _f(i):
            txt = tds[i].get_text(strip=True).replace(",", "").replace("%", "")
            try:
                return float(txt)
            except ValueError:
                return None

        price     = _f(2)
        mktcap    = _f(6)
        dividend  = _f(7)
        frgn_rate = _f(8)
        per       = _f(9)
        roe       = _f(10)
        pbr       = _f(11)
        div_yield = round(dividend / price * 100, 2) if (dividend and price and price > 0) else 0.0
        rows.append({
            "종목명": name, "티커": ticker, "시장": market,
            "현재가": price, "시가총액(억)": mktcap,
            "배당금": dividend or 0, "DIV": div_yield,
            "외국인비율": frgn_rate or 0,
            "PER": per, "ROE": roe, "PBR": pbr,
        })
    return rows


@st.cache_data(ttl=3600, show_spinner="📊 네이버 금융 전체 종목 수집 중... (1~3분 소요)")
def load_market_fundamentals(markets):
    SOSOK = {"KOSPI": 0, "KOSDAQ": 1}
    all_rows = []
    for market in markets:
        sosok = SOSOK.get(market, 0)
        session = requests.Session()
        session.headers.update(_NAVER_HEADERS)
        post_data = {
            "menu": "market_sum",
            "fieldIds": _FIELD_IDS,
            "returnUrl": f"{_NAVER_GET_URL}?sosok={sosok}",
        }
        try:
            resp = session.post(_NAVER_POST_URL, data=post_data, timeout=20)
        except Exception as e:
            st.warning(f"{market} 1페이지 요청 실패: {e}")
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        all_rows.extend(_parse_page(soup, market))
        page = 2
        consecutive_empty = 0
        while True:
            try:
                r = session.get(_NAVER_GET_URL, params={"sosok": sosok, "page": page}, timeout=15)
                s = BeautifulSoup(r.text, "html.parser")
                page_rows = _parse_page(s, market)
                if not page_rows:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                else:
                    consecutive_empty = 0
                    all_rows.extend(page_rows)
                page += 1
                time.sleep(0.12)
            except Exception as e:
                st.warning(f"{market} {page}페이지 오류: {e}")
                page += 1
                if page > 500:
                    break
                continue
    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(all_rows)


def _yf_suffix(market):
    return ".KS" if market == "KOSPI" else ".KQ"


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_financial_depth(ticker, market):
    """
    yfinance 심층 재무 분석
    - opm_avg3       : 3년 평균 영업이익률(%)
    - opm_list       : 연도별 OPM 리스트
    - opm_no_loss    : 3년 연속 적자 없음 여부
    - roe_w          : 가중 ROE (0.5/0.3/0.2)
    - current_ratio  : 유동비율(%)
    - icr            : 이자보상배율
    - div_3yr        : 최근 3년 연간 배당금 리스트 (최신→과거)
    - div_3yr_ok     : 3년 연속 배당 지급 여부
    - div_growing    : 배당금 유지 또는 우상향 여부
    - div_payout     : 배당성향(%)
    - div_payout_warn: 배당성향 100% 초과 경고
    - ocf_2yr        : 최근 2년 영업활동현금흐름 리스트
    - ocf_ok         : 최근 2년 연속 음수 아님 여부
    - listed_years   : 상장 기간(년, 약산)
    - ma200          : 200일 이동평균
    - above_ma200    : 현재가가 200일선 위 여부
    - return_6m      : 최근 6개월 수익률(%)
    - trend_warn     : 추세 경고 여부
    """
    empty = {
        "opm_avg3": None, "opm_list": [], "opm_no_loss": None,
        "roe_w": None, "current_ratio": None, "icr": None,
        "div_3yr": [], "div_3yr_ok": None, "div_growing": None,
        "div_payout": None, "div_payout_warn": False,
        "ocf_2yr": [], "ocf_ok": None,
        "listed_years": None, "ma200": None, "above_ma200": None,
        "return_6m": None, "trend_warn": False,
        "ok": False
    }
    try:
        suffix = _yf_suffix(market)
        yft    = yf.Ticker(ticker + suffix)
        fin    = yft.financials
        bs     = yft.balance_sheet
        if fin is None or fin.empty:
            return empty
        result = dict(empty)

        # ── 3년 영업이익률 ──────────────────────────────────
        if "Operating Income" in fin.index and "Total Revenue" in fin.index:
            oi = fin.loc["Operating Income"].dropna().sort_index(ascending=False)
            tr = fin.loc["Total Revenue"].dropna().sort_index(ascending=False)
            common_idx = oi.index.intersection(tr.index)[:3]
            opm_vals = []
            for idx in common_idx:
                rev = tr[idx]
                if rev and rev != 0:
                    opm_vals.append(round(float(oi[idx]) / float(rev) * 100, 2))
            result["opm_list"]    = opm_vals
            result["opm_avg3"]    = round(sum(opm_vals) / len(opm_vals), 1) if opm_vals else None
            result["opm_no_loss"] = not all(v <= 0 for v in opm_vals) if opm_vals else None

        # ── 3년 ROE 가중평균 (0.5/0.3/0.2) ────────────────────
        if "Net Income" in fin.index and bs is not None and "Common Stock Equity" in bs.index:
            ni  = fin.loc["Net Income"].dropna().sort_index(ascending=False)
            eq  = bs.loc["Common Stock Equity"].dropna().sort_index(ascending=False)
            common_idx = ni.index.intersection(eq.index)[:3]
            if len(common_idx) >= 2:
                wts = [0.5, 0.3, 0.2][:len(common_idx)]
                roe_vals = []
                for idx in common_idx:
                    e = float(eq[idx])
                    if e != 0:
                        roe_vals.append(float(ni[idx]) / e * 100)
                if roe_vals:
                    wts2 = wts[:len(roe_vals)]
                    result["roe_w"] = round(sum(v * w for v, w in zip(roe_vals, wts2)) / sum(wts2), 1)

        # ── 유동비율 ────────────────────────────────────────
        if bs is not None and "Current Assets" in bs.index and "Current Liabilities" in bs.index:
            ca = bs.loc["Current Assets"].dropna().sort_index(ascending=False)
            cl = bs.loc["Current Liabilities"].dropna().sort_index(ascending=False)
            common = ca.index.intersection(cl.index)
            if len(common) > 0:
                lat = common[0]
                if float(cl[lat]) != 0:
                    result["current_ratio"] = round(float(ca[lat]) / float(cl[lat]) * 100, 1)

        # ── 이자보상배율 ──────────────────────────────────────
        if "EBIT" in fin.index and "Interest Expense" in fin.index:
            ebit = fin.loc["EBIT"].dropna().sort_index(ascending=False)
            ie   = fin.loc["Interest Expense"].dropna().abs().sort_index(ascending=False)
            common = ebit.index.intersection(ie.index)
            if len(common) > 0:
                lat = common[0]
                if float(ie[lat]) > 0:
                    result["icr"] = round(float(ebit[lat]) / float(ie[lat]), 1)

        # ── 배당 이력 (3년) ───────────────────────────────────
        # yfinance dividends: DatetimeIndex → 연도별 합산
        try:
            divs = yft.dividends
            if divs is not None and not divs.empty:
                divs.index = pd.to_datetime(divs.index).tz_localize(None)
                cur_year = datetime.now().year
                yr_divs = []
                for yr in [cur_year - 1, cur_year - 2, cur_year - 3]:
                    s = divs[str(yr)] if str(yr) in divs.index.year.astype(str).values else pd.Series([])
                    yr_divs.append(float(s.sum()) if len(s) > 0 else 0.0)
                result["div_3yr"]    = yr_divs   # [가장최근년, 2년전, 3년전]
                result["div_3yr_ok"] = all(v > 0 for v in yr_divs)
                # 배당 우상향 여부: 최근년 >= 전년 >= 전전년 (각 단계 비교)
                if len(yr_divs) >= 2:
                    result["div_growing"] = yr_divs[0] >= yr_divs[1]
        except Exception:
            pass

        # ── 배당성향 (최근 1년) ───────────────────────────────
        try:
            ni_key = "Net Income"
            if ni_key in fin.index:
                ni_latest   = fin.loc[ni_key].dropna().sort_index(ascending=False).iloc[0]
                divs_latest = result["div_3yr"][0] if result["div_3yr"] else 0.0
                # 발행주식수 추정: shares outstanding
                info  = yft.info
                sh    = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding") or 0
                if sh > 0 and ni_latest > 0:
                    total_div = divs_latest * sh
                    payout    = total_div / ni_latest * 100
                    result["div_payout"]      = round(payout, 1)
                    result["div_payout_warn"] = payout > 100
        except Exception:
            pass

        # ── 영업활동현금흐름 (최근 2년) ───────────────────────
        try:
            cf = yft.cashflow
            if cf is not None and not cf.empty:
                ocf_key = next((k for k in cf.index if "Operating" in k and "Cash" in k), None)
                if ocf_key:
                    ocf = cf.loc[ocf_key].dropna().sort_index(ascending=False)[:2]
                    ocf_vals = [float(v) for v in ocf.values]
                    result["ocf_2yr"] = ocf_vals
                    # 2년 연속 음수이면 False
                    if len(ocf_vals) >= 2:
                        result["ocf_ok"] = not all(v < 0 for v in ocf_vals[:2])
                    elif len(ocf_vals) == 1:
                        result["ocf_ok"] = ocf_vals[0] >= 0
        except Exception:
            pass

        # ── 주가 기술적 지표: 200일MA, 6개월 수익률, 상장기간 ──
        try:
            hist = yf.download(ticker + suffix, period="2y", progress=False, auto_adjust=True)
            if hist is not None and not hist.empty:
                if isinstance(hist.columns, pd.MultiIndex):
                    hist.columns = hist.columns.get_level_values(0)
                close = hist["Close"].dropna()
                # 상장 기간 (년)
                earliest = close.index[0]
                result["listed_years"] = round((datetime.now() - pd.Timestamp(earliest)).days / 365, 1)
                # 200일 이동평균
                if len(close) >= 200:
                    ma200 = float(close.rolling(200).mean().dropna().iloc[-1])
                    cur   = float(close.iloc[-1])
                    result["ma200"]       = round(ma200, 0)
                    result["above_ma200"] = cur >= ma200
                # 최근 6개월 수익률
                if len(close) >= 126:
                    ret6m = (float(close.iloc[-1]) / float(close.iloc[-126]) - 1) * 100
                    result["return_6m"] = round(ret6m, 1)
                    # 추세 경고: 200일선 하향 OR 6개월 -20% 이상 언더퍼폼
                    if result["above_ma200"] is False or (ret6m <= -20):
                        result["trend_warn"] = True
        except Exception:
            pass

        result["ok"] = True
        return result
    except Exception:
        return empty


_DEPTH_COLS = [
    "opm_avg3", "opm_list", "opm_no_loss", "roe_w", "current_ratio", "icr",
    "div_3yr", "div_3yr_ok", "div_growing", "div_payout", "div_payout_warn",
    "ocf_2yr", "ocf_ok",
    "listed_years", "ma200", "above_ma200", "return_6m", "trend_warn",
]


def batch_fetch_financials(df, progress_placeholder):
    df = df.copy()
    total = len(df)
    for col in _DEPTH_COLS:
        df[col] = None
    for i, (idx, row) in enumerate(df.iterrows()):
        d = fetch_financial_depth(row["티커"], row["시장"])
        for col in _DEPTH_COLS:
            df.at[idx, col] = d.get(col)
        progress_placeholder.progress(
            (i + 1) / total,
            text=f"📊 심층 분석 중... {i+1}/{total} ({row['종목명']})"
        )
    return df


def normalize(series, ascending=True):
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(50.0, index=series.index)
    norm = (series - mn) / (mx - mn) * 100
    return norm if ascending else (100 - norm)


def compute_scores(df, w):
    df = df.copy()
    df = df[(df["PBR"] > 0) & (df["PBR"] < 50)]
    df = df[(df["PER"] > 0) & (df["PER"] < 200)]
    df = df[df["ROE"].notna() & (df["ROE"] > 0) & (df["ROE"] <= 200)]

    df["roe_for_score"] = df.apply(
        lambda r: r["roe_w"] if pd.notna(r.get("roe_w")) and r.get("roe_w", 0) > 0 else r["ROE"],
        axis=1
    )
    df["pbr_score"]  = normalize(df["PBR"],            ascending=False)
    df["roe_score"]  = normalize(df["roe_for_score"],   ascending=True)
    df["div_score"]  = normalize(df["DIV"],             ascending=True)
    df["per_score"]  = normalize(df["PER"],             ascending=False)
    df["frgn_score"] = normalize(df["외국인비율"],       ascending=True)

    if "opm_avg3" in df.columns and df["opm_avg3"].notna().any():
        opm_filled = df["opm_avg3"].fillna(df["opm_avg3"].median())
        df["opm_score"] = normalize(opm_filled, ascending=True)
    else:
        df["opm_score"] = 50.0

    df["종합점수"] = (
        df["pbr_score"]  * w.get("pbr_score",  0.20) +
        df["roe_score"]  * w.get("roe_score",  0.25) +
        df["div_score"]  * w.get("div_score",  0.15) +
        df["per_score"]  * w.get("per_score",  0.15) +
        df["opm_score"]  * w.get("opm_score",  0.15) +
        df["frgn_score"] * w.get("frgn_score", 0.10)
    )

    # 배당 성장 가점 / 배당성향 감점
    if "div_growing" in df.columns:
        df.loc[df["div_growing"] == True,  "종합점수"] += 5
    if "div_payout" in df.columns:
        df.loc[df["div_payout"] > 100,     "종합점수"] -= 5
    if "div_3yr_ok" in df.columns:
        df.loc[df["div_3yr_ok"] == True,   "종합점수"] += 2   # 3년 연속 배당 소폭 가점
    if "above_ma200" in df.columns:
        df.loc[df["above_ma200"] == True,  "종합점수"] += 3   # 200일선 위 가점

    df["종합점수"] = df["종합점수"].clip(0, 100).round(1)
    # 태그 부여
    df["태그"] = df.apply(assign_tag, axis=1)
    return df.sort_values("종합점수", ascending=False)


def calc_fair_price(current_price, pbr, roe, required_return=0.10):
    if not (current_price and pbr and roe and required_return > 0 and pbr > 0):
        return 0
    bps = current_price / pbr
    fair_pbr = (roe / 100) / required_return
    return round(bps * fair_pbr)


def assign_tag(row):
    """
    종목 태그 부여
    💎 다이아몬드 우량주: 모든 조건 충족 + 200일선 위
    ⚠️ 저평가 소외주  : 재무 양호하나 200일선 아래 (가격 추세 부진)
    🛑 분석 주의     : ROE 비정상 or 배당성향 100% 초과
    """
    roe         = row.get("ROE", 0) or 0
    payout      = row.get("div_payout") or 0
    div_3yr_ok  = row.get("div_3yr_ok")
    opm         = row.get("opm_avg3") or 0
    above_ma200 = row.get("above_ma200")
    div_growing = row.get("div_growing")
    roe_w       = row.get("roe_w") or roe
    score       = row.get("종합점수", 0) or 0

    # 🛑 분석 주의
    if roe > 80 or payout > 100:
        return "🛑 분석 주의"

    # 💎 다이아몬드: 재무 우량 + 배당 지속 + 200일선 위 + 고점수
    diamond = (
        above_ma200 is True
        and div_3yr_ok is True
        and div_growing is True
        and opm >= 8
        and roe_w >= 10
        and score >= 55
    )
    if diamond:
        return "💎 다이아몬드 우량주"

    # ⚠️ 저평가 소외주: 200일선 아래지만 재무 양호
    if above_ma200 is False and score >= 45:
        return "⚠️ 저평가 소외주"

    return "—"


# ────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 설정")
    st.subheader("🔑 KIS API 인증")
    app_key    = st.text_input("APP Key",    value=os.getenv("KIS_APP_KEY", ""),    type="password")
    app_secret = st.text_input("APP Secret", value=os.getenv("KIS_APP_SECRET", ""), type="password")
    if app_key and app_secret:
        st.success("API 키 입력 완료")
    else:
        st.info(".env 파일에 KIS_APP_KEY / KIS_APP_SECRET을 설정하거나 직접 입력하세요.")

    st.divider()
    st.subheader("🔍 1차 필터 (네이버 금융 스캔)")
    markets     = st.multiselect("대상 시장", ["KOSPI", "KOSDAQ"], default=["KOSPI", "KOSDAQ"])
    mktcap_min  = st.slider("최소 시가총액 (억원)",            0, 10000, 1000, 500)
    roe_max     = st.slider("ROE 상한 (%) — 초과 시 자본잠식 의심", 20, 300, 80)
    st.markdown("**코스피 필터**")
    pbr_max     = st.slider("PBR 상한",           0.1,  10.0,  1.5, 0.1)
    per_max     = st.slider("PER 상한",            1,    200,   30)
    roe_min     = st.slider("ROE 최소 (%)",        0,     40,    8)
    div_min     = st.slider("배당수익률 최소 (%)", 0.0,  10.0,  0.0, 0.5)
    st.markdown("**코스닥 전용 필터**")
    kosdaq_pbr_max = st.slider("코스닥 PBR 상한",           0.1, 20.0, 5.0, 0.5)
    kosdaq_per_max = st.slider("코스닥 PER 상한",            1,   500,  80)
    kosdaq_roe_min = st.slider("코스닥 ROE 최소 (%)",        0,    40,   5)
    kosdaq_div_min = st.slider("코스닥 배당수익률 최소 (%)", 0.0, 10.0,  0.0, 0.5)

    st.divider()
    st.subheader("🔬 심층 재무 분석 (yfinance)")
    deep_enabled = st.checkbox(
        "심층 분석 활성화", value=True,
        help="3년 OPM·가중ROE·유동비율·이자보상배율을 yfinance에서 추가 수집합니다. 종목 수에 따라 1~5분 추가 소요. 결과는 캐시됩니다."
    )
    if deep_enabled:
        st.markdown("**영업이익률(OPM) 필터**")
        kospi_opm_min  = st.slider("코스피 OPM 최소 (%)",  0.0, 30.0,  5.0, 0.5,
            help="3년 평균 영업이익률 하한. 5% 미만은 원가 상승 시 적자 전환 위험.")
        kosdaq_opm_min = st.slider("코스닥 OPM 최소 (%)", 0.0, 30.0,  8.0, 0.5,
            help="성장 기술주는 8~10% 이상.")
        require_opm_no_loss = st.checkbox("3년 연속 영업적자 종목 제외", value=True)
        st.markdown("**재무 건전성 필터**")
        current_ratio_min = st.slider("유동비율 최소 (%)",        0, 400,  150, 25,
            help="150% 이상: 단기 부채 상환 여력 충분.")
        icr_min           = st.slider("이자보상배율 최소 (배)", 0.0, 20.0, 3.0, 0.5,
            help="3배 이상: 영업이익으로 이자를 3배 이상 감당.")
        apply_cr_icr      = st.checkbox("유동비율/이자보상배율 필터 적용", value=True)
        st.markdown("**하드 필터 (데이터 없으면 통과)**")
        require_div_3yr  = st.checkbox("3년 연속 배당 미지급 종목 제외", value=False,
            help="배당 이력이 확인된 경우에만 필터 적용. 데이터 없으면 통과.")
        require_ocf_ok   = st.checkbox("영업현금흐름 2년 연속 음수 제외", value=True,
            help="2년 연속 영업CF 음수 종목 제외. 데이터 없으면 통과.")
        require_listing  = st.checkbox("상장 2년 미만 종목 제외", value=True,
            help="상장 기간이 짧아 재무 신뢰도가 낮은 종목 제외.")
    else:
        kospi_opm_min = 0.0; kosdaq_opm_min = 0.0; require_opm_no_loss = False
        current_ratio_min = 0; icr_min = 0.0; apply_cr_icr = False
        require_div_3yr = False; require_ocf_ok = False; require_listing = False

    st.divider()
    st.subheader("⚖️ 팩터 가중치")
    w_pbr  = st.slider("저PBR  가중치",          0, 50, 20) / 100
    w_roe  = st.slider("고ROE  가중치 (3년 가중)", 0, 50, 25) / 100
    w_div  = st.slider("고배당 가중치",           0, 50, 15) / 100
    w_per  = st.slider("저PER  가중치",           0, 50, 15) / 100
    w_opm  = st.slider("고OPM  가중치",           0, 50, 15) / 100
    w_frgn = st.slider("외국인비율 가중치",        0, 50, 10) / 100
    total_w = w_pbr + w_roe + w_div + w_per + w_opm + w_frgn
    if abs(total_w - 1.0) > 0.01:
        st.warning(f"가중치 합계: {total_w:.2f} (1.0 권장)")
    weights_cfg = {
        "pbr_score": w_pbr, "roe_score": w_roe, "div_score": w_div,
        "per_score": w_per, "opm_score": w_opm, "frgn_score": w_frgn,
    }

    st.divider()
    required_return = st.slider("요구수익률 (적정주가 계산, %)", 5, 20, 10) / 100
    st.caption(f"데이터: 네이버 금융 + yfinance | 기준: {datetime.today().strftime('%Y-%m-%d')}")

    scan_btn = st.button("🚀 종목 스캔 시작", type="primary", use_container_width=True)
    if st.button("🗑️ 캐시 초기화 (재수집)", use_container_width=True):
        st.cache_data.clear()
        for key in ["scored_df", "scan_time", "raw_count", "deep_enabled"]:
            st.session_state.pop(key, None)
        st.success("캐시 초기화 완료. 다시 스캔하세요.")


st.title("📈 저평가 우량주 발굴기")
st.caption("네이버 금융 + yfinance | 멀티팩터: 저PBR + 고ROE(3년가중) + 고OPM + 고배당 + 재무건전성")

tab_scan, tab_detail, tab_guide = st.tabs(["🔎 종목 스캔", "🏢 개별 종목 분석", "📖 분석 가이드"])


with tab_scan:

    # ── 스캔 실행 ─────────────────────────────────────────
    if scan_btn:
        if not markets:
            st.error("대상 시장을 1개 이상 선택하세요.")
            st.stop()

        # Stage 1: 네이버 금융 전종목 수집
        with st.spinner("📥 [Stage 1] 네이버 금융 전체 종목 수집 중... (최초 실행 시 1~3분 소요)"):
            raw_df = load_market_fundamentals(tuple(sorted(markets)))

        if raw_df.empty:
            st.error("데이터를 가져올 수 없습니다.")
            st.stop()

        # 1차 필터
        cmask = (
            raw_df["시가총액(억)"].notna() & (raw_df["시가총액(억)"] >= mktcap_min) &
            raw_df["ROE"].notna() & (raw_df["ROE"] <= roe_max)
        )
        kospi_mask = (
            cmask & (raw_df["시장"] == "KOSPI") &
            raw_df["PBR"].notna() & (raw_df["PBR"] > 0) & (raw_df["PBR"] <= pbr_max) &
            raw_df["PER"].notna() & (raw_df["PER"] > 0) & (raw_df["PER"] <= per_max) &
            (raw_df["ROE"] >= roe_min) & (raw_df["DIV"] >= div_min)
        )
        kosdaq_mask = (
            cmask & (raw_df["시장"] == "KOSDAQ") &
            raw_df["PBR"].notna() & (raw_df["PBR"] > 0) & (raw_df["PBR"] <= kosdaq_pbr_max) &
            raw_df["PER"].notna() & (raw_df["PER"] > 0) & (raw_df["PER"] <= kosdaq_per_max) &
            (raw_df["ROE"] >= kosdaq_roe_min) & (raw_df["DIV"] >= kosdaq_div_min)
        )
        filtered = raw_df[kospi_mask | kosdaq_mask].copy()
        if filtered.empty:
            st.warning("조건에 맞는 종목이 없습니다. 필터 조건을 완화하세요.")
            st.stop()

        st.success(f"✅ [Stage 1] {len(raw_df):,}개 수집 → {len(filtered)}개 통과")

        # Stage 2: yfinance 심층 분석
        if deep_enabled:
            st.info(
                f"🔬 [Stage 2] {len(filtered)}개 종목 심층 재무 분석 중... "
                f"(예상 소요 {max(10, len(filtered))}~{max(20, len(filtered)*2)}초)"
            )
            prog = st.progress(0, text="준비 중...")
            filtered = batch_fetch_financials(filtered, prog)
            prog.empty()

            # OPM 필터
            def _opm_ok(row):
                opm = row.get("opm_avg3")
                if opm is None or (isinstance(opm, float) and pd.isna(opm)):
                    return True  # 데이터 없으면 통과 (관대)
                thr = kospi_opm_min if row["시장"] == "KOSPI" else kosdaq_opm_min
                if opm < thr:
                    return False
                if require_opm_no_loss:
                    if row.get("opm_no_loss") is False:
                        return False
                return True

            b4 = len(filtered)
            filtered = filtered[filtered.apply(_opm_ok, axis=1)]
            st.success(f"✅ OPM 필터 적용: {b4}개 → {len(filtered)}개")

            # 유동비율 / 이자보상배율 필터
            if apply_cr_icr:
                def _cr_icr_ok(row):
                    cr  = row.get("current_ratio")
                    icr = row.get("icr")
                    if cr  is not None and not (isinstance(cr,  float) and pd.isna(cr))  and cr  < current_ratio_min: return False
                    if icr is not None and not (isinstance(icr, float) and pd.isna(icr)) and icr < icr_min:           return False
                    return True

                b4 = len(filtered)
                filtered = filtered[filtered.apply(_cr_icr_ok, axis=1)]
                st.success(f"✅ 유동비율/이자보상배율 필터: {b4}개 → {len(filtered)}개")

            # 하드필터: 3년 연속 배당
            if require_div_3yr:
                def _div_ok(row):
                    v = row.get("div_3yr_ok")
                    if v is None or (isinstance(v, float) and pd.isna(v)): return True
                    return bool(v)
                b4 = len(filtered)
                filtered = filtered[filtered.apply(_div_ok, axis=1)]
                st.success(f"✅ 3년 연속 배당 필터: {b4}개 → {len(filtered)}개")

            # 하드필터: 영업현금흐름 2년 연속 음수 제외
            if require_ocf_ok:
                def _ocf_ok(row):
                    v = row.get("ocf_ok")
                    if v is None or (isinstance(v, float) and pd.isna(v)): return True
                    return bool(v)
                b4 = len(filtered)
                filtered = filtered[filtered.apply(_ocf_ok, axis=1)]
                st.success(f"✅ 영업현금흐름 필터: {b4}개 → {len(filtered)}개")

            # 하드필터: 상장 2년 미만 제외
            if require_listing:
                def _listing_ok(row):
                    v = row.get("listed_years")
                    if v is None or (isinstance(v, float) and pd.isna(v)): return True
                    return float(v) >= 2.0
                b4 = len(filtered)
                filtered = filtered[filtered.apply(_listing_ok, axis=1)]
                st.success(f"✅ 상장기간 필터: {b4}개 → {len(filtered)}개")
        else:
            for col in ["opm_avg3", "roe_w", "opm_no_loss", "current_ratio", "icr"]:
                filtered[col] = None

        if filtered.empty:
            st.warning("심층 필터 후 조건에 맞는 종목이 없습니다. 필터 조건을 완화하세요.")
            st.stop()

        # Stage 3: 스코어링
        scored = compute_scores(filtered, weights_cfg)
        scored["적정주가(원)"] = scored.apply(
            lambda r: calc_fair_price(r["현재가"], r["PBR"], r["ROE"], required_return), axis=1
        )

        st.session_state["scored_df"]    = scored
        st.session_state["scan_time"]    = datetime.now().strftime("%Y-%m-%d %H:%M")
        st.session_state["raw_count"]    = len(raw_df)
        st.session_state["deep_enabled"] = deep_enabled

    # ── 결과 표시 (세션 있으면 항상 표시) ────────────────────
    if "scored_df" in st.session_state:
        scored    = st.session_state["scored_df"]
        scan_time = st.session_state.get("scan_time", "")
        raw_count = st.session_state.get("raw_count", 0)
        was_deep  = st.session_state.get("deep_enabled", False)

        st.caption(
            f"마지막 스캔: **{scan_time}** | 전체 수집: {raw_count:,}개 | "
            f"심층 분석: {'✅' if was_deep else '⬜ (비활성)'}"
        )

        top = scored.head(1).iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🥇 1위 종목", top["종목명"], f"점수 {top['종합점수']}")
        c2.metric("통과 종목 수", f"{len(scored)}개", f"전체 {raw_count:,}개 중")
        c3.metric("평균 PBR", f"{scored['PBR'].mean():.2f}")
        c4.metric("평균 ROE", f"{scored['ROE'].mean():.1f}%")

        if was_deep and "opm_avg3" in scored.columns and scored["opm_avg3"].notna().any():
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("평균 OPM(3년)", f"{scored['opm_avg3'].mean():.1f}%")
            c6.metric("평균 유동비율",
                f"{scored['current_ratio'].mean():.0f}%" if scored["current_ratio"].notna().any() else "N/A")
            c7.metric("평균 이자보상배율",
                f"{scored['icr'].mean():.1f}배" if scored["icr"].notna().any() else "N/A")
            c8.metric("가중ROE 계산된 종목", f"{scored['roe_w'].notna().sum()}개")

        st.divider()
        st.subheader("🏆 종합 점수 상위 종목")

        # ── 시장별 필터 라디오 버튼 ──────────────────────────
        _avail_markets = sorted(scored["시장"].unique().tolist())
        _mkt_opts = ["전체"] + _avail_markets
        _mkt_sel  = st.radio(
            "📌 시장 필터", _mkt_opts, horizontal=True, index=0,
            help="코스피 또는 코스닥만 필터링하거나 전체를 볼 수 있습니다."
        )
        scored_show = scored if _mkt_sel == "전체" else scored[scored["시장"] == _mkt_sel]
        if scored_show.empty:
            st.warning(f"{_mkt_sel} 종목이 없습니다. '전체'로 다시 선택하세요.")
            scored_show = scored

        _tag_col = ["태그"] if (was_deep and "태그" in scored_show.columns) else []
        base_cols = _tag_col + ["종목명", "시장", "티커", "종합점수", "PBR", "ROE", "DIV", "PER",
                     "외국인비율", "현재가", "시가총액(억)", "적정주가(원)"]
        base_cols_safe = [c for c in base_cols if c in scored_show.columns]
        display_df = scored_show[base_cols_safe].head(50).copy().reset_index(drop=True)
        if was_deep:
            display_df["OPM_3yr(%)"]    = scored_show["opm_avg3"].head(50).values    if "opm_avg3"       in scored_show.columns else None
            display_df["ROE_가중(%)"]    = scored_show["roe_w"].head(50).values       if "roe_w"          in scored_show.columns else None
            display_df["유동비율(%)"]    = scored_show["current_ratio"].head(50).values if "current_ratio" in scored_show.columns else None
            display_df["이자보상배율"]   = scored_show["icr"].head(50).values         if "icr"            in scored_show.columns else None
            if "div_3yr_ok" in scored_show.columns:
                display_df["3년배당"] = scored_show["div_3yr_ok"].head(50).map(
                    lambda x: "✅연속" if x is True else ("❌미지급" if x is False else "-")
                ).values
            if "div_growing" in scored_show.columns:
                display_df["배당추이"] = scored_show["div_growing"].head(50).map(
                    lambda x: "📈상승" if x is True else ("📉하락" if x is False else "-")
                ).values
            if "above_ma200" in scored_show.columns:
                display_df["200일선"] = scored_show["above_ma200"].head(50).map(
                    lambda x: "🔼위" if x is True else ("🔽아래" if x is False else "-")
                ).values
            # ── 평균 배당율(3년) ─────────────────────────────
            if "div_3yr" in scored_show.columns:
                def _avg_div_yield(r):
                    try:
                        vals = r["div_3yr"]
                        if isinstance(vals, str):
                            vals = eval(vals)
                        price = float(r["현재가"]) if r["현재가"] else 0
                        if vals and price > 0:
                            nonzero = [float(v) for v in vals if v and float(v) > 0]
                            if nonzero:
                                return round(sum(nonzero) / len(nonzero) / price * 100, 2)
                    except Exception:
                        pass
                    return None
                display_df["평균배당율(%)"] = scored_show.head(50).apply(_avg_div_yield, axis=1).values
        display_df.index += 1

        def color_score(val):
            if val >= 70:   return "background-color: #1a7f4b; color: white"
            elif val >= 50: return "background-color: #4caf7d; color: white"
            elif val >= 30: return "background-color: #fff3cd"
            return ""

        fmt = {
            "PBR": "{:.2f}", "ROE": "{:.1f}%", "DIV": "{:.2f}%", "PER": "{:.1f}",
            "외국인비율": "{:.1f}%", "현재가": "{:,.0f}원",
            "시가총액(억)": "{:,.0f}", "적정주가(원)": "{:,.0f}", "종합점수": "{:.1f}",
        }
        if was_deep:
            fmt.update({"OPM_3yr(%)": "{:.1f}", "ROE_가중(%)": "{:.1f}",
                        "유동비율(%)": "{:.0f}", "이자보상배율": "{:.1f}",
                        "평균배당율(%)": "{:.2f}"})
        st.dataframe(
            display_df.style.map(color_score, subset=["종합점수"]).format(fmt, na_rep="-"),
            use_container_width=True, height=600
        )

        # OPM 3년 추이 상세 (expander)
        if was_deep and "opm_list" in scored_show.columns:
            with st.expander("📋 상위 20종목 OPM 3년 추이 상세"):
                opm_rows = []
                for _, row in scored_show.head(20).iterrows():
                    try:    vals = eval(str(row.get("opm_list", "[]")))
                    except: vals = []
                    entry = {
                        "종목명": row["종목명"], "시장": row["시장"],
                        "OPM평균(%)": row.get("opm_avg3"),
                        "3년연속흑자": "✅" if row.get("opm_no_loss") else "❌" if row.get("opm_no_loss") is False else "-",
                    }
                    for j, v in enumerate(vals[:3]):
                        entry[f"OPM Y{j+1}(%)"] = v
                    opm_rows.append(entry)
                opm_df = pd.DataFrame(opm_rows)
                fmt2   = {c: "{:.1f}" for c in opm_df.columns if "OPM" in c}
                st.dataframe(opm_df.style.format(fmt2, na_rep="-"),
                             use_container_width=True, hide_index=True)

        # 배당율 3년 추이 상세 (expander)
        if was_deep and "div_3yr" in scored_show.columns:
            with st.expander("📋 상위 20종목 배당율 3년 추이 상세"):
                div_rows = []
                for _, row in scored_show.head(20).iterrows():
                    try:
                        vals = row.get("div_3yr", [])
                        if isinstance(vals, str):
                            vals = eval(vals)
                    except Exception:
                        vals = []
                    price = float(row.get("현재가") or 0)
                    cur_yr = datetime.now().year
                    entry = {
                        "종목명":       row["종목명"],
                        "시장":         row["시장"],
                        "현재배당율(%)": row.get("DIV"),
                        "3년연속배당":   "✅" if row.get("div_3yr_ok") is True else ("❌" if row.get("div_3yr_ok") is False else "-"),
                        "배당추이":      "📈상승" if row.get("div_growing") is True else ("📉하락" if row.get("div_growing") is False else "-"),
                    }
                    yr_labels = [str(cur_yr - 1), str(cur_yr - 2), str(cur_yr - 3)]
                    for j, v in enumerate(vals[:3]):
                        yr = yr_labels[j]
                        entry[f"{yr}배당(원)"]  = round(float(v), 0) if v else None
                        entry[f"{yr}배당율(%)"] = round(float(v) / price * 100, 2) if (v and price > 0) else None
                    div_rows.append(entry)
                div_df  = pd.DataFrame(div_rows)
                fmt_div = {c: "{:.2f}" for c in div_df.columns if "배당율" in c}
                fmt_div.update({c: "{:,.0f}" for c in div_df.columns if "배당(원)" in c})
                fmt_div["현재배당율(%)"] = "{:.2f}"
                st.dataframe(div_df.style.format(fmt_div, na_rep="-"),
                             use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("📊 시각화")
        chart_df = scored_show.head(30)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**ROE vs PBR 산점도** (버블 크기 = 배당수익률)")
            fig_sc = px.scatter(
                chart_df, x="PBR", y="ROE", size="DIV", color="종합점수",
                hover_name="종목명", text="종목명", color_continuous_scale="RdYlGn",
                title="이상적 위치: 좌상단 (저PBR + 고ROE)",
                labels={"PBR": "PBR (낮을수록 저평가)", "ROE": "ROE %"},
            )
            fig_sc.update_traces(textposition="top center", textfont_size=9)
            st.plotly_chart(fig_sc, use_container_width=True)
        with col_b:
            st.markdown("**상위 20종목 종합 점수 막대차트**")
            top20 = scored_show.head(20).sort_values("종합점수")
            fig_bar = px.bar(
                top20, x="종합점수", y="종목명", orientation="h",
                color="종합점수", color_continuous_scale="RdYlGn",
                text="종합점수", title="종합점수 상위 20종목",
            )
            fig_bar.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig_bar.update_layout(showlegend=False, yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_bar, use_container_width=True)

        if was_deep and "opm_avg3" in scored_show.columns and scored_show["opm_avg3"].notna().any():
            st.subheader("🫧 영업이익률(3년평균) vs ROE 산점도")
            opm_chart = scored_show[scored_show["opm_avg3"].notna()].head(40)
            roe_col = "roe_for_score" if "roe_for_score" in opm_chart.columns else "ROE"
            fig_opm = px.scatter(
                opm_chart, x="opm_avg3", y=roe_col,
                size="시가총액(억)", color="종합점수",
                hover_name="종목명", text="종목명",
                color_continuous_scale="RdYlGn",
                labels={"opm_avg3": "3년평균 OPM (%)", roe_col: "ROE (%)"},
                title="우상단: 영업 경쟁력 + 자본 효율성 동시 우수"
            )
            fig_opm.update_traces(textposition="top center", textfont_size=8)
            fig_opm.add_vline(x=10, line_dash="dash", line_color="gray",
                annotation_text="OPM 10% (경제적 해자)")
            st.plotly_chart(fig_opm, use_container_width=True)

        st.subheader("🕸️ 상위 5종목 팩터 레이더 차트")
        categories  = ["저PBR", "고ROE", "고배당", "저PER", "고OPM", "외국인비율"]
        factor_cols = ["pbr_score", "roe_score", "div_score", "per_score", "opm_score", "frgn_score"]
        fig_radar   = go.Figure()
        colors      = ["#e63946", "#2a9d8f", "#e9c46a", "#457b9d", "#a8dadc", "#f4a261"]
        for i, (_, row) in enumerate(scored_show.head(5).iterrows()):
            vals = [row.get(c, 50) for c in factor_cols]
            fig_radar.add_trace(go.Scatterpolar(
                r=vals + vals[:1], theta=categories + [categories[0]],
                fill="toself", name=row["종목명"], line_color=colors[i],
            ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            showlegend=True, height=450,
        )
        st.plotly_chart(fig_radar, use_container_width=True)

        st.divider()
        today_str = datetime.today().strftime("%Y%m%d")
        dl_cols = [c for c in [
            "종목명","시장","티커","종합점수","PBR","ROE","DIV","PER","외국인비율",
            "현재가","시가총액(억)","적정주가(원)",
            "opm_avg3","roe_w","current_ratio","icr","opm_no_loss",
        ] if c in scored.columns]
        csv = scored[dl_cols].to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 전체 결과 CSV 다운로드", data=csv,
            file_name=f"저평가우량주_{today_str}.csv", mime="text/csv")

    else:
        st.info("👈 왼쪽 사이드바에서 조건을 설정하고 **[종목 스캔 시작]** 버튼을 누르세요.")
        st.markdown("""
        ### 분석 팩터 및 가중치
        | 팩터 | 기본 가중치 | 의미 |
        |---|---|---|
        | **저PBR** | 20% | 자산 대비 주가 저평가 |
        | **고ROE** (3년 가중) | 25% | Y0×0.5 + Y1×0.3 + Y2×0.2 → 꾸준한 실력 |
        | **고OPM** (3년 평균) | 15% | 본업 수익성 — 일회성 이익 제거 |
        | **고배당** | 15% | 배당수익률 |
        | **저PER** | 15% | 이익 대비 주가 저평가 |
        | **외국인비율** | 10% | 글로벌 우량주 검증 |

        ### 심층 재무 필터 (가짜 우량주 제거)
        | 필터 | 기준 | 효과 |
        |---|---|---|
        | **OPM ≥ 5~10%** | 3년 평균 | 일회성 이익 기업 제거 |
        | **유동비율 ≥ 150%** | 최근 기준 | 단기 부채 위험 차단 |
        | **이자보상배율 ≥ 3배** | 최근 기준 | 레버리지 ROE 착시 방지 |
        | **ROE 3년 가중평균** | — | 반짝 실적 왜곡 제거 |
        """)


with tab_detail:
    st.subheader("🏢 개별 종목 KIS API 상세 분석")

    if not app_key or not app_secret:
        st.warning("KIS API 키를 사이드바에 입력해야 개별 종목 상세 분석이 가능합니다.")
    else:
        col_in, col_bt = st.columns([2, 1])
        with col_in:
            ticker_input = st.text_input("종목 코드 (6자리)", placeholder="예) 005930 (삼성전자)")
        with col_bt:
            detail_btn = st.button("🔍 상세 조회", type="primary")

        if "scored_df" in st.session_state:
            st.markdown("또는 **스캔 결과에서 선택:**")
            scored_df = st.session_state["scored_df"]
            opts = [f"{r['종목명']} ({r['티커']})" for _, r in scored_df.head(30).iterrows()]
            sel  = st.selectbox("스캔 상위 30종목", ["선택하세요..."] + opts)
            if sel != "선택하세요...":
                ticker_input = sel.split("(")[-1].replace(")", "").strip()

        if detail_btn or (ticker_input and len(ticker_input) == 6):
            if not ticker_input or len(ticker_input) != 6:
                st.error("6자리 종목 코드를 입력하세요.")
            else:
                with st.spinner(f"🔑 {ticker_input} 데이터 조회 중..."):
                    try:
                        token = get_kis_token(app_key, app_secret)
                    except Exception as e:
                        st.error(f"토큰 발급 실패: {e}"); st.stop()
                    price_data   = get_stock_detail(ticker_input, token, app_key, app_secret)
                    finance_data = get_stock_finance(ticker_input, token, app_key, app_secret)

                if "error" in price_data and not price_data.get("stck_prpr"):
                    st.error(f"현재가 조회 실패: {price_data['error']}")
                else:
                    name          = price_data.get("hts_kor_isnm", ticker_input)
                    current_price = int(price_data.get("stck_prpr", 0))
                    change_rate   = float(price_data.get("prdy_ctrt", 0))
                    st.markdown(f"## {name} `{ticker_input}`")
                    st.metric("현재가", f"{current_price:,}원", f"{change_rate:+.2f}%")
                    st.divider()

                    per  = float(price_data.get("per", 0) or 0)
                    pbr  = float(price_data.get("pbr", 0) or 0)
                    eps  = int(float(price_data.get("eps", 0) or 0))
                    bps  = int(float(price_data.get("bps", 0) or 0))
                    if bps > 0 and eps > 0:
                        roe_calc   = round(eps / bps * 100, 2)
                        fair_price = round(bps * (roe_calc/100) / required_return) if required_return > 0 else 0
                    elif pbr > 0:
                        roe_calc   = 0.0
                        fair_price = calc_fair_price(current_price, pbr, roe_calc, required_return)
                    else:
                        roe_calc   = 0.0
                        fair_price = 0
                    margin = round((fair_price - current_price) / current_price * 100, 1) if current_price > 0 else 0

                    c1,c2,c3,c4,c5 = st.columns(5)
                    c1.metric("PBR", f"{pbr:.2f}"); c2.metric("PER", f"{per:.1f}")
                    c3.metric("EPS", f"{eps:,}원"); c4.metric("BPS", f"{bps:,}원")
                    c5.metric("ROE (추정)", f"{roe_calc:.1f}%")
                    st.divider()

                    col_fair, col_gauge = st.columns(2)
                    with col_fair:
                        st.markdown("### 🎯 적정주가 분석")
                        st.markdown(f"""
                        | 항목 | 값 |
                        |---|---|
                        | 현재주가 | {current_price:,}원 |
                        | **적정주가** | **{fair_price:,}원** |
                        | **안전마진** | **{margin:+.1f}%** |
                        | 요구수익률 | {required_return*100:.0f}% |
                        """)
                        if   margin >  20: st.success(f"✅ {margin:.1f}% 저평가")
                        elif margin >   0: st.info(f"ℹ️ {margin:.1f}% 저평가")
                        elif margin > -20: st.warning(f"⚠️ {abs(margin):.1f}% 고평가")
                        else:              st.error(f"🔴 {abs(margin):.1f}% 고평가 — 주의")
                    with col_gauge:
                        fig_g = go.Figure(go.Indicator(
                            mode="gauge+number+delta",
                            value=current_price,
                            delta={"reference": fair_price, "relative": True, "valueformat": ".1%"},
                            title={"text": "현재가 vs 적정주가"},
                            gauge={
                                "axis": {"range": [0, max(current_price, fair_price) * 1.5]},
                                "bar": {"color": "#2a9d8f"},
                                "steps": [
                                    {"range": [0, fair_price*0.8], "color": "#1a7f4b"},
                                    {"range": [fair_price*0.8, fair_price], "color": "#4caf7d"},
                                    {"range": [fair_price, fair_price*1.2], "color": "#fff3cd"},
                                    {"range": [fair_price*1.2, max(current_price,fair_price)*1.5], "color": "#f4cccc"},
                                ],
                                "threshold": {"line": {"color": "red", "width": 3}, "value": fair_price},
                            },
                            number={"suffix": "원", "valueformat": ","},
                        ))
                        fig_g.update_layout(height=300)
                        st.plotly_chart(fig_g, use_container_width=True)

                    # yfinance 심층 재무
                    st.divider()
                    st.subheader("🔬 심층 재무 분석 (yfinance)")
                    mkt_suffix = ".KS"
                    if "scored_df" in st.session_state:
                        _m = st.session_state["scored_df"]
                        _m = _m[_m["티커"] == ticker_input]
                        if not _m.empty and _m.iloc[0]["시장"] == "KOSDAQ":
                            mkt_suffix = ".KQ"
                    det_mkt = "KOSPI" if mkt_suffix == ".KS" else "KOSDAQ"
                    with st.spinner("yfinance 재무데이터 수집 중..."):
                        fd = fetch_financial_depth(ticker_input, det_mkt)

                    if fd.get("ok"):
                        # 태그 및 추세 경고
                        tag_row_dict = {
                            "ROE": roe_calc, "roe_w": fd.get("roe_w"),
                            "div_payout": fd.get("div_payout"), "div_3yr_ok": fd.get("div_3yr_ok"),
                            "opm_avg3": fd.get("opm_avg3"), "above_ma200": fd.get("above_ma200"),
                            "div_growing": fd.get("div_growing"), "종합점수": 50,
                        }
                        tag_val = assign_tag(tag_row_dict)
                        tag_col, _ = st.columns([1, 3])
                        tag_col.markdown(f"### {tag_val}")
                        if fd.get("trend_warn"):
                            st.warning(
                                "⚠️ **하락 추세 주의**: 현재 주가가 200일 이동평균선 아래에 있거나 "
                                "최근 6개월 수익률이 -20% 이하입니다. "
                                "바닥을 충분히 다지는 것을 확인한 후 진입을 권장합니다."
                            )
                        elif fd.get("above_ma200") is True:
                            st.success("✅ 주가가 200일 이동평균선 위에 있습니다 (상승 추세).")

                        # 배당 요약
                        div_parts = []
                        if fd.get("div_3yr_ok") is True:  div_parts.append("3년 연속 배당: ✅")
                        elif fd.get("div_3yr_ok") is False: div_parts.append("3년 연속 배당: ❌")
                        if fd.get("div_growing") is True:  div_parts.append("배당 추이: 📈 상승")
                        elif fd.get("div_growing") is False: div_parts.append("배당 추이: 📉 하락")
                        if fd.get("div_payout"):           div_parts.append(f"배당성향: {fd['div_payout']:.1f}%" + (" ⚠️" if fd.get("div_payout_warn") else ""))
                        if div_parts:
                            st.info(" | ".join(div_parts))

                        fc1,fc2,fc3,fc4 = st.columns(4)
                        fc1.metric("OPM 3년 평균",  f"{fd['opm_avg3']:.1f}%"  if fd["opm_avg3"]       else "N/A")
                        fc2.metric("ROE 가중평균",   f"{fd['roe_w']:.1f}%"     if fd["roe_w"]          else "N/A")
                        fc3.metric("유동비율",       f"{fd['current_ratio']:.0f}%" if fd["current_ratio"]  else "N/A")
                        fc4.metric("이자보상배율",   f"{fd['icr']:.1f}배"      if fd["icr"]            else "N/A")

                        if fd["opm_list"]:
                            opm_vals   = fd["opm_list"]
                            y_lbls     = [f"Y{i+1}(최근{i}년전)" for i in range(len(opm_vals))]
                            bar_colors = ["#1a7f4b" if v>=10 else "#4caf7d" if v>=5 else "#f4cccc" for v in opm_vals]
                            fig_ob = go.Figure(go.Bar(
                                x=y_lbls[::-1], y=opm_vals[::-1],
                                marker_color=bar_colors[::-1],
                                text=[f"{v:.1f}%" for v in opm_vals[::-1]],
                                textposition="outside",
                            ))
                            fig_ob.add_hline(y=5,  line_dash="dash", line_color="orange", annotation_text="5% 하한")
                            fig_ob.add_hline(y=10, line_dash="dash", line_color="green",  annotation_text="10% 경제적 해자")
                            fig_ob.update_layout(
                                title="영업이익률 3년 추이", yaxis_title="OPM (%)", height=300,
                                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
                                xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333"),
                            )
                            st.plotly_chart(fig_ob, use_container_width=True)

                        st.markdown("##### 재무 건전성 체크리스트")
                        checks = []
                        if fd.get("opm_avg3") is not None:
                            ok = fd["opm_avg3"] >= 5
                            checks.append(f"{'✅' if ok else '❌'} 3년 평균 OPM {fd['opm_avg3']:.1f}% (기준: ≥5%)")
                        if fd.get("current_ratio") is not None:
                            ok = fd["current_ratio"] >= 150
                            checks.append(f"{'✅' if ok else '❌'} 유동비율 {fd['current_ratio']:.0f}% (기준: ≥150%)")
                        if fd.get("icr") is not None:
                            ok = fd["icr"] >= 3
                            checks.append(f"{'✅' if ok else '❌'} 이자보상배율 {fd['icr']:.1f}배 (기준: ≥3배)")
                        if fd.get("opm_no_loss") is not None:
                            checks.append(f"{'✅' if fd['opm_no_loss'] else '❌'} 3년 연속 영업적자 {'없음' if fd['opm_no_loss'] else '있음'}")
                        for c in checks:
                            st.markdown(c)
                    else:
                        st.info("yfinance 데이터를 가져올 수 없습니다. (비상장 또는 데이터 미제공)")

                    # 주가 차트
                    st.divider()
                    st.subheader("📈 주가 차트")
                    yf_tick = ticker_input + mkt_suffix
                    try:
                        hist = yf.download(yf_tick, period="2y", progress=False, auto_adjust=True)
                        if hist.empty:
                            alt  = ".KQ" if mkt_suffix == ".KS" else ".KS"
                            hist = yf.download(ticker_input + alt, period="2y", progress=False, auto_adjust=True)
                        if not hist.empty:
                            if isinstance(hist.columns, pd.MultiIndex):
                                hist.columns = hist.columns.get_level_values(0)
                            cperiod   = st.radio("기간", ["3개월", "6개월", "1년", "2년"], index=2, horizontal=True)
                            days_map  = {"3개월": 63, "6개월": 126, "1년": 252, "2년": 504}
                            hist_show = hist.tail(days_map[cperiod])
                            # ── 200일 이동평균 (전체 2년 기준으로 계산 → 정확도 높음) ──
                            ma200_series = hist["Close"].rolling(200).mean()
                            ma200_show   = ma200_series.reindex(hist_show.index)
                            fig_p = go.Figure()
                            fig_p.add_trace(go.Candlestick(
                                x=hist_show.index,
                                open=hist_show["Open"], high=hist_show["High"],
                                low=hist_show["Low"],   close=hist_show["Close"],
                                name="주가", increasing_line_color="#e63946", decreasing_line_color="#457b9d",
                            ))
                            for win, clr, lbl in [(5,"#2a9d8f","MA5"),(20,"#e9c46a","MA20"),(60,"#f4a261","MA60")]:
                                ma = hist_show["Close"].rolling(win).mean()
                                fig_p.add_trace(go.Scatter(x=hist_show.index, y=ma, name=lbl,
                                    line=dict(color=clr, width=1.5), opacity=0.85))
                            # ── 200일선 강조 (굵은 주황선) ──────────────────────────
                            fig_p.add_trace(go.Scatter(
                                x=ma200_show.index, y=ma200_show.values,
                                name="MA200 (200일선)",
                                line=dict(color="#ff6b35", width=3, dash="solid"),
                                opacity=1.0,
                            ))
                            bb_ma  = hist_show["Close"].rolling(20).mean()
                            bb_std = hist_show["Close"].rolling(20).std()
                            fig_p.add_trace(go.Scatter(
                                x=list(hist_show.index)+list(hist_show.index[::-1]),
                                y=list(bb_ma+2*bb_std)+list((bb_ma-2*bb_std)[::-1]),
                                fill="toself", fillcolor="rgba(150,100,200,0.1)",
                                line=dict(color="rgba(150,100,200,0.3)"), name="볼린저밴드"))
                            fig_p.update_layout(
                                height=450, xaxis_rangeslider_visible=False,
                                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                                margin=dict(l=0,r=0,t=30,b=0),
                                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="white",
                                xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333", tickformat=","),
                            )
                            st.plotly_chart(fig_p, use_container_width=True)
                            vol_colors = ["#e63946" if c>=o else "#457b9d"
                                          for c,o in zip(hist_show["Close"], hist_show["Open"])]
                            fig_v = go.Figure(go.Bar(x=hist_show.index, y=hist_show["Volume"],
                                marker_color=vol_colors, name="거래량"))
                            fig_v.update_layout(height=150, margin=dict(l=0,r=0,t=5,b=0),
                                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                                font_color="white", showlegend=False,
                                xaxis=dict(gridcolor="#333"), yaxis=dict(gridcolor="#333", tickformat=",.0f"))
                            st.plotly_chart(fig_v, use_container_width=True)
                        else:
                            st.info("주가 차트 데이터 없음.")
                    except Exception as e:
                        st.info(f"주가 차트 로딩 실패: {e}")

                    if finance_data and "error" not in finance_data:
                        st.divider()
                        st.subheader("📊 KIS API 재무비율 (최근 결산)")
                        fin_items = {
                            "ROE": finance_data.get("roe", "-"),
                            "부채비율": finance_data.get("lblt_rate", "-"),
                            "영업이익률": finance_data.get("bsop_prfi_rate", "-"),
                            "순이익률": finance_data.get("thtr_ntin_rate", "-"),
                            "유동비율": finance_data.get("crnt_rate", "-"),
                        }
                        st.dataframe(
                            pd.DataFrame({"항목": list(fin_items.keys()), "값": list(fin_items.values())}),
                            use_container_width=True, hide_index=True
                        )


with tab_guide:
    st.subheader("📖 저평가 우량주 발굴 가이드 (장기 투자 버전)")
    st.markdown("""
    ### 핵심 전략: 저PBR + 고ROE(지속성) + 고OPM + 재무건전성

    ---

    ### 1️⃣ PBR — 저평가 여부
    - **PBR < 1.0** → 해산 가치 이하. KOSPI 기준 PBR < 1.5 선호.

    ---

    ### 2️⃣ ROE — 수익성 (3년 가중평균)
    - 단일 연도 ROE 왜곡 방지: **Y0×0.5 + Y1×0.3 + Y2×0.2**
    - '꾸준한 실력' 기업에 더 높은 점수 부여

    ---

    ### 3️⃣ 영업이익률(OPM) — 본업 경쟁력 ⭐
    | 수준 | 의미 |
    |---|---|
    | 5% 미만 | 원가 상승 시 적자 전환 위험 ⚠️ |
    | 5~10% | 일반 제조·서비스업 평균 |
    | 10% 이상 | 경제적 해자 🟢 |
    | 20% 이상 | 독점적 기술력/브랜드 💎 |

    > **3년 평균 OPM ≥ 7% & 3년 연속 흑자** 조건으로 일회성 이익 기업 제거.

    ---

    ### 4️⃣ 재무 건전성 — 부채의 덫 방지
    | 지표 | 기준 | 이유 |
    |---|---|---|
    | **유동비율 ≥ 150%** | 단기 현금화 자산 충분 | 유동성 위기 방어 |
    | **이자보상배율 ≥ 3배** | 영업이익 > 이자×3 | 레버리지 ROE 착시 방지 |

    ---

    ### 5️⃣ 적정주가 계산

    $$\text{적정 PBR} = \frac{ROE\,(\%)}{\text{요구수익률}\,(\%)}$$
    $$\text{적정주가} = BPS \times \text{적정 PBR}$$

    **예시**: ROE 15%, BPS 10,000원, 요구수익률 10%  
    → 적정 PBR = 1.5 → 적정주가 = **15,000원**

    ---

    ### 🧭 투자 판단 흐름
    ```
    1차: PBR + PER + ROE + 배당수익률 필터 (네이버 금융 전종목)
    2차: OPM 3년 평균 ≥ 5~10%, 3년 연속 흑자 확인 (yfinance)
    3차: 유동비율 ≥ 150%, 이자보상배율 ≥ 3배 (yfinance)
    최종: 멀티팩터 종합점수 70점 이상 → 강력 후보 🟢
    ```

    ---

    ### 📊 데이터 출처
    - **시장 전종목 재무**: 네이버 금융 시가총액 시세표
    - **3년 OPM·유동비율·이자보상배율**: Yahoo Finance (yfinance)
    - **가격·BPS·EPS**: 한국투자증권 KIS Open API
    """)
