# my-stock-app — USD/KRW 실시간 환율 모니터

간단한 Streamlit 앱으로 USD/KRW 환율을 실시간 모니터링합니다.

주요 파일
- `currency.py` — 대시보드 로직(데이터 수집, 차트, UI)
- `streamlit_app.py` — Streamlit 엔트리포인트
- `requirements.txt` — 배포 시 필요 패키지

로컬 실행
```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Streamlit Community Cloud에 배포하기
1. https://share.streamlit.io 에 로그인합니다.
2. "New app" → GitHub 리포지토리 선택 → 브랜치 `main` 선택
3. `File in repository`에 `streamlit_app.py` 경로를 입력하고 "Deploy" 클릭

참고
- 타임스탬프는 KST(Asia/Seoul)로 표시됩니다.
- 당일 최저/최고일 때 메인 환율 숫자 색상이 바뀝니다 (최저: 짙은 하늘색, 최고: 빨간색).

문제가 있거나 자동 배포(GitHub Actions) 설정을 원하시면 알려주세요.
