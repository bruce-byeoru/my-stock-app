// 로또 데이터 타입
export interface LottoData {
  drwNo: number
  drwNoDate: string
  drwtNo1: number
  drwtNo2: number
  drwtNo3: number
  drwtNo4: number
  drwtNo5: number
  drwtNo6: number
  bnusNo: number
  firstWinamnt: number
  firstPrzwnerCo: number
}

// 연금복권 데이터 타입
export interface PensionLotteryData {
  round: number
  drawDate: string
  group: number
  num1: number
  num2: number
  num3: number
  num4: number
  num5: number
  num6: number
}

// 사용자 번호 세트
export interface NumberSet {
  id: number
  numbers: number[]
  stats: {
    rank1: number
    rank2: number
    rank3: number
    rank4: number
    rank5: number
    rank6?: number
    rank7?: number
  }
  // Optional bitmask representation for fast matching (1-based bits)
  mask?: bigint
}

// 시뮬레이션 세션(Try)
export interface SimulationSession {
  id: string
  label: string
  lotteryType: 'lotto' | 'pension'
  startRound: number
  endRound: number
  totalRequested: number
  totalSimulated: number
  isBackground: boolean
  status: 'running' | 'done' | 'error'
  progress: number
  createdAt: number
  completedAt?: number
  allResults: NumberSet[]
  errorMsg?: string
  debugInfo?: string
}

// 시뮬레이션 결과
export interface SimulationResult {
  totalSets: number
  topSets: NumberSet[]
  periodInfo: {
    startRound: number
    endRound: number
    totalRounds: number
  }
}
