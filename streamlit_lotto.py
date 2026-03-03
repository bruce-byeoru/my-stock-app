import streamlit as st

st.set_page_config(page_title="Lotto App (Wrapper)", layout="wide")
st.title("로또 / 연금복권 앱 (Streamlit 래퍼)")

st.markdown("""
이 페이지는 내부적으로 실행 중인 Next.js 앱(로컬:3000)을 iframe으로 임베드합니다.

사용 방법:
1. 이 개발 환경에서 Next.js 앱을 실행하세요 (`lottery-app` 폴더에서 `npm run dev`) — 기본 포트는 `3000` 입니다.
2. 이 Streamlit 페이지를 실행하세요:
   `streamlit run streamlit_lotto.py --server.port 8501 --server.address 0.0.0.0`
3. VS Code 포트 포워딩 또는 ngrok을 사용해 `3000`(Next.js)와 `8501`(Streamlit)을 모바일에서 접근 가능하도록 공개하세요.

주의: Docker/devcontainer에서 실행 시 host 접근성 때문에 포트 포워딩이 필요합니다.
""")

# 사용자가 임의 URL을 지정할 수 있게 함 (기본: localhost:3000)
app_url = st.text_input('앱 URL (Next.js)', value='http://localhost:3000')

st.info('먼저 Next.js 앱이 실행중인지 확인하세요. 실행중이면 아래에 앱이 표시됩니다.')

cols = st.columns([1, 3])
with cols[0]:
    st.write('앱 상태 확인')
    if st.button('열기 in 새창'):
        st.write('새 탭으로 열기를 시도합니다...')
        js = f"window.open('{app_url}', '_blank')"
        st.components.v1.html(f"<script>{js}</script>", height=10)

with cols[1]:
    # iframe 으로 앱을 임베드
    st.markdown('### 앱 미리보기')
    st.components.v1.html(f'<iframe src="{app_url}" width="100%" height="800" style="border:1px solid #ddd"></iframe>', height=820)

st.markdown('---')
st.markdown('추가 팁: 모바일에서 접근하려면 VS Code의 포트 패널에서 `3000`과 `8501`을 공개하거나 `ngrok`으로 3000 포트를 터널하세요.')
