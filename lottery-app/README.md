# 로또 & 연금복권 시뮬레이터

Next.js 14와 React로 구현된 로또와 연금복권 당첨 번호 추적 및 시뮬레이션 웹 애플리케이션입니다.

## 주요 기능

- 📊 **통합 대시보드**: 로또와 연금복권을 탭으로 전환
- 🎲 **번호 생성**: 수동 입력 또는 랜덤 생성
- 🔍 **시뮬레이션**: 과거 당첨 내역과 비교하여 당첨 횟수 계산
- 🏆 **통계 리포트**: 상위 10개 번호 세트 및 상세 통계
- 🌐 **API 연동**: 동행복권 공식 API (CORS 프록시 처리)

## 기술 스택

- **Frontend**: Next.js 14, React 18, TypeScript
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **API**: Next.js API Routes (CORS 프록시)

## 폴더 구조

```
lottery-app/
├── app/
│   ├── api/
│   │   ├── lotto/
│   │   │   └── route.ts         # 로또 API 프록시
│   │   └── pension/
│   │       └── route.ts         # 연금복권 API 프록시
│   ├── globals.css              # 전역 스타일
│   ├── layout.tsx               # 루트 레이아웃
│   └── page.tsx                 # 메인 페이지
├── components/
│   └── LotterySimulator.tsx     # 메인 시뮬레이터 컴포넌트
├── lib/
│   ├── lottery-utils.ts         # 핵심 로직 (생성, 비교, 시뮬레이션)
│   └── lottery-service.ts       # API 서비스 레이어
├── types/
│   └── lottery.ts               # TypeScript 타입 정의
├── next.config.js
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── postcss.config.js
```

## 시작하기

### 1. 의존성 설치

```bash
npm install
```

### 2. 개발 서버 실행

```bash
npm run dev
```

### 3. 브라우저에서 열기

```
http://localhost:3000
```

## 사용 방법

1. **복권 유형 선택**: 로또 6/45 또는 연금복권 720+ 탭 선택
2. **기간 설정**: 시작 회차와 종료 회차 입력
3. **번호 입력**:
   - 랜덤: 생성할 번호 세트 개수 입력
   - 수동: 직접 번호를 입력 (한 줄에 하나씩)
4. **시뮬레이션 시작**: 버튼 클릭하여 실행
5. **결과 확인**: 상위 10개 번호 세트와 당첨 통계 확인

## API 정보

### 로또 API
- **엔드포인트**: `/api/lotto?drwNo={회차}`
- **원본**: `https://www.dhlottery.co.kr/common.do?method=getLottoNumber`

### 연금복권 API
- **엔드포인트**: `/api/pension?round={회차}`
- **원본**: `https://www.dhlottery.co.kr/common.do?method=get720Number`

> **참고**: API 실패 시 자동으로 가상 데이터로 대체됩니다.

## 라이선스

MIT
