/**
 * 다음 차수 예측 엔진
 *
 * 5개 모듈로 후보 번호를 선별하고 가중치 기반으로 5세트를 생성합니다.
 * Math.random() 사용을 최소화하고 데이터 기반 확률적 선택(Weighted Random)을 사용합니다.
 */

import { LottoData, PensionLotteryData } from '@/types/lottery'

// ─── 타입 ───────────────────────────────────────────────────────────────────

export interface NumberScore {
  num: number
  total: number
  reasons: string[]
  scores: {
    staircase: number   // 계단/사선 흐름
    carryover: number   // 이월수·이웃수
    cold: number        // 장기 미출현 회귀
    section: number     // 구간 멸실 채움
    endDigit: number    // 끝수·연번
  }
}

export interface PredictionSet {
  numbers: number[]
  reasons: string[]        // 번호별 주요 근거
  structureInfo: {
    sum: number
    odd: number
    even: number
    low: number
    high: number
    consecutivePairs: number
  }
}

export interface PredictionResult {
  sets: PredictionSet[]
  moduleReports: {
    staircase: string[]
    carryover: string[]
    cold: string[]
    section: string[]
    endDigit: string[]
  }
  scoreboard: NumberScore[]   // 전 번호 1-45 점수 (높은 순)
}

// ─── 구간 정의 ──────────────────────────────────────────────────────────────
const SECTIONS = [
  { name: '1번대(1~10)',   min: 1,  max: 10 },
  { name: '10번대(11~20)', min: 11, max: 20 },
  { name: '20번대(21~30)', min: 21, max: 30 },
  { name: '30번대(31~40)', min: 31, max: 40 },
  { name: '40번대(41~45)', min: 41, max: 45 },
]

// ─── 헬퍼 ───────────────────────────────────────────────────────────────────
function getNums(row: LottoData): number[] {
  return [row.drwtNo1, row.drwtNo2, row.drwtNo3, row.drwtNo4, row.drwtNo5, row.drwtNo6]
}

/**
 * 가중치 배열에서 확률적 선택
 * weights[i] ∝ 번호 i+1 이 선택될 확률
 */
function weightedPick(weights: number[]): number {
  const totalW = weights.reduce((s, w) => s + w, 0)
  let rand = Math.random() * totalW
  for (let i = 0; i < weights.length; i++) {
    rand -= weights[i]
    if (rand <= 0) return i + 1
  }
  return weights.length // fallback
}

// ─── 메인 엔진 ──────────────────────────────────────────────────────────────

/**
 * @param allRows      회차 범위로 필터된 로또 당첨 데이터
 * @param windowSize   계단·구간 분석용 최근 회차 수(기본 10)
 */
export function runPredictionEngine(
  allRows: LottoData[],
  windowSize: number = 10,
): PredictionResult {
  const EMPTY: PredictionResult = {
    sets: [],
    moduleReports: { staircase: [], carryover: [], cold: [], section: [], endDigit: [] },
    scoreboard: [],
  }
  if (allRows.length < 5) return EMPTY

  // 회차 오름차순 정렬
  const sorted = [...allRows].sort((a, b) => a.drwNo - b.drwNo)
  const recent10 = sorted.slice(-Math.max(windowSize, 5))
  const recent5  = sorted.slice(-5)
  const last     = sorted[sorted.length - 1]

  // 전체 출현 빈도 (인덱스 0 = num 1)
  const freqAll = Array(46).fill(0)
  sorted.forEach(row => getNums(row).forEach(n => freqAll[n]++)  )

  // 번호별 스코어 초기화 (num 1~45)
  const scoreMap: NumberScore[] = Array.from({ length: 45 }, (_, i) => ({
    num: i + 1,
    total: 0,
    reasons: [],
    scores: { staircase: 0, carryover: 0, cold: 0, section: 0, endDigit: 0 },
  }))

  const reports = {
    staircase: [] as string[],
    carryover: [] as string[],
    cold:      [] as string[],
    section:   [] as string[],
    endDigit:  [] as string[],
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Module 1 : Staircase Tracker — 사선/계단 흐름 분석
  // ═══════════════════════════════════════════════════════════════════════════
  {
    // recent10 의 각 회차 번호 집합 (시간순)
    const frames = recent10.map(row => new Set(getNums(row)))

    // 탐지할 step 값 (±1, ±2)
    for (const step of [1, -1, 2, -2]) {
      // 번호 n 이 직전 회차에 있고, n-step 이 그 이전 회차에 있는 체인 탐색
      for (let n = 1; n <= 45; n++) {
        // 최신 프레임(frames[last])부터 역방향으로 체인 길이 측정
        let chainLen = 0
        let cur = n
        for (let r = frames.length - 1; r >= 0; r--) {
          if (frames[r].has(cur)) {
            chainLen++
            cur = cur - step  // 한 단계 이전에 있어야 할 값
          } else {
            break
          }
        }
        if (chainLen >= 2) {
          const next = n + step
          if (next >= 1 && next <= 45) {
            const score = chainLen * 4 // 체인 길이에 비례
            scoreMap[next - 1].scores.staircase += score
            const sign = step > 0 ? `+${step}` : `${step}`
            const msg = `계단 흐름(${sign}): ${chainLen}회 연속 ${sign} 간격 → 다음 예측값 ${next}`
            if (!scoreMap[next - 1].reasons.includes(msg)) scoreMap[next - 1].reasons.push(msg)
            if (!reports.staircase.includes(msg)) reports.staircase.push(msg)
          }
        }
      }
    }

    if (reports.staircase.length === 0)
      reports.staircase.push('최근 회차에서 뚜렷한 계단 패턴 미감지')
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Module 2 : Carry-over & Neighbors — 이월수·이웃수 가중치
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const lastNums = getNums(last)

    // 각 이월수 및 인접 번호 처리
    for (const n of lastNums) {
      // 이웃수 ±1, ±2
      const neighbors = [n - 2, n - 1, n + 1, n + 2].filter(x => x >= 1 && x <= 45)

      for (const nb of neighbors) {
        const freq = freqAll[nb]
        if (freq === 0) continue
        const avgGap = sorted.length / freq

        // 마지막 출현 이후 경과 회차
        let lastSeenIdx = -1
        for (let r = sorted.length - 1; r >= 0; r--) {
          if (getNums(sorted[r]).includes(nb)) { lastSeenIdx = r; break }
        }
        const gap = sorted.length - 1 - lastSeenIdx
        const ratio = gap / avgGap

        if (ratio >= 0.6) {
          const score = Math.min(6, Math.ceil(ratio * 2))
          scoreMap[nb - 1].scores.carryover += score
          const msg = `이월인접(${n}→${nb}): 평균주기 ${avgGap.toFixed(1)}회, 현재 ${gap}회 미출현(${(ratio * 100).toFixed(0)}%)`
          if (!scoreMap[nb - 1].reasons.includes(msg)) scoreMap[nb - 1].reasons.push(msg)
          reports.carryover.push(msg)
        }
      }

      // 이월수 자체 재출현 가중치
      const freq = freqAll[n]
      if (freq > 0) {
        const avgGap = sorted.length / freq
        // 직전 회차는 last 이므로 그 전부터 역탐색
        let prevSeenIdx = -1
        for (let r = sorted.length - 2; r >= 0; r--) {
          if (getNums(sorted[r]).includes(n)) { prevSeenIdx = r; break }
        }
        const gapFromPrev = sorted.length - 2 - prevSeenIdx
        if (gapFromPrev > avgGap * 0.4) {
          scoreMap[n - 1].scores.carryover += 3
          const msg = `이월수(${n}): 직전 회차 당첨 → 재출현 타이밍 가중치`
          if (!scoreMap[n - 1].reasons.includes(msg)) scoreMap[n - 1].reasons.push(msg)
          if (!reports.carryover.includes(msg)) reports.carryover.push(msg)
        }
      }
    }

    if (reports.carryover.length === 0)
      reports.carryover.push('이월수 분석: 유효한 이웃수 재출현 신호 없음')
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Module 3 : Cold & Cycle — 장기 미출현 및 회귀 분석
  // ═══════════════════════════════════════════════════════════════════════════
  {
    type ColdEntry = { num: number; gap: number; avgGap: number; ratio: number }
    const cold: ColdEntry[] = []

    for (let n = 1; n <= 45; n++) {
      const freq = freqAll[n]
      if (freq === 0) continue
      const avgGap = sorted.length / freq

      let lastSeenIdx = -1
      for (let r = sorted.length - 1; r >= 0; r--) {
        if (getNums(sorted[r]).includes(n)) { lastSeenIdx = r; break }
      }
      const gap = lastSeenIdx === -1 ? sorted.length : sorted.length - 1 - lastSeenIdx
      const ratio = gap / avgGap

      if (ratio >= 1.4) cold.push({ num: n, gap, avgGap: Math.round(avgGap * 10) / 10, ratio })
    }

    // ratio 높은 순 상위 12개
    cold.sort((a, b) => b.ratio - a.ratio).slice(0, 12).forEach((c, i) => {
      const score = Math.round(c.ratio * 3)
      scoreMap[c.num - 1].scores.cold += score
      const msg = `장기미출현(${c.num}): ${c.gap}회 미출현 (평균 ${c.avgGap}회의 ${(c.ratio * 100).toFixed(0)}%) ← 임계 초과`
      scoreMap[c.num - 1].reasons.push(msg)
      reports.cold.push(msg)
    })

    if (cold.length === 0)
      reports.cold.push('장기 미출현 번호 없음 (모든 번호 정상 주기 내 출현)')
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Module 4 : Section Analysis — 구간 멸실 및 채움
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const lookback = Math.min(5, recent5.length)
    const window   = recent5.slice(-lookback)

    const sectionStats = SECTIONS.map(sec => {
      let count = 0
      window.forEach(row => getNums(row).forEach(n => { if (n >= sec.min && n <= sec.max) count++ }))
      const size = sec.max - sec.min + 1
      const expected = (size / 45) * 6 * lookback
      return { ...sec, count, expected }
    })

    for (const sec of sectionStats) {
      const ratio = sec.count / sec.expected

      if (ratio === 0 || ratio < 0.4) {
        // 전멸 또는 극소 구간 → 채움 강가중치
        const score = ratio === 0 ? 8 : 4
        for (let n = sec.min; n <= sec.max; n++) {
          scoreMap[n - 1].scores.section += score
          const tag = `구간채움(${sec.name}): 최근 ${lookback}회 ${sec.count}번 출현 → 반등 기대`
          if (!scoreMap[n - 1].reasons.some(r => r.startsWith(`구간채움(${sec.name})`)))
            scoreMap[n - 1].reasons.push(tag)
        }
        reports.section.push(
          `${sec.name}: 최근 ${lookback}회차 출현 ${sec.count}회 (기대 ${sec.expected.toFixed(1)}회의 ${(ratio * 100).toFixed(0)}%) → 반등 예상`
        )
      } else if (ratio > 2.2) {
        // 과열 구간 → 소폭 차감 (확률적 균형)
        for (let n = sec.min; n <= sec.max; n++) scoreMap[n - 1].scores.section -= 2
        reports.section.push(`${sec.name}: 최근 ${lookback}회차 ${sec.count}회 (과열 ${(ratio * 100).toFixed(0)}%) → 억제`)
      }
    }

    if (reports.section.length === 0)
      reports.section.push('구간 분포 균형 양호 (전멸/과열 없음)')
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Module 5 : Ending Digit & Consecutives — 끝수·연번 빈도
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const lookback = Math.min(10, recent10.length)
    const window   = recent10.slice(-lookback)

    // 끝수 빈도 (최근 lookback 회차)
    const edCount = Array(10).fill(0)
    window.forEach(row => getNums(row).forEach(n => edCount[n % 10]++))

    // 강세 끝수 TOP 3 → 가중치
    const ranked = edCount
      .map((count, digit) => ({ digit, count }))
      .sort((a, b) => b.count - a.count)

    ranked.slice(0, 3).forEach(({ digit, count }) => {
      const cands = Array.from({ length: 45 }, (_, i) => i + 1).filter(n => n % 10 === digit)
      const score = Math.round(count * 0.6)
      cands.forEach(c => {
        scoreMap[c - 1].scores.endDigit += score
        const tag = `끝수강세(끝${digit}): 최근 ${lookback}회 ${count}번 출현 강세`
        if (!scoreMap[c - 1].reasons.some(r => r.includes(`끝수강세(끝${digit})`)))
          scoreMap[c - 1].reasons.push(tag)
      })
      reports.endDigit.push(`끝자리 ${digit}: 최근 ${lookback}회 ${count}개 출현 (강세)`)
    })

    // 약세 끝수 소폭 반등 가중치
    ranked.slice(-2).forEach(({ digit, count }) => {
      const cands = Array.from({ length: 45 }, (_, i) => i + 1).filter(n => n % 10 === digit)
      cands.forEach(c => { scoreMap[c - 1].scores.endDigit += 1 })
      reports.endDigit.push(`끝자리 ${digit}: 최근 ${lookback}회 ${count}개 출현 (약세 → 소폭 반등 가중)`)
    })

    // 최근 연번 패턴 분석
    const consecCounts: number[] = window.map(row => {
      const s = getNums(row).sort((a, b) => a - b)
      let c = 0
      for (let i = 0; i < s.length - 1; i++) if (s[i + 1] - s[i] === 1) c++
      return c
    })
    const avgConsec = consecCounts.reduce((s, n) => s + n, 0) / consecCounts.length
    reports.endDigit.push(`최근 ${lookback}회 평균 연번 쌍: ${avgConsec.toFixed(1)}개`)
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 총 점수 계산 + 네거티브 방지
  // ═══════════════════════════════════════════════════════════════════════════
  for (const s of scoreMap) {
    s.total = s.scores.staircase + s.scores.carryover + s.scores.cold +
              s.scores.section  + s.scores.endDigit
    s.total = Math.max(0, s.total) // 음수 방지
  }

  const scoreboard = [...scoreMap].sort((a, b) => b.total - a.total)

  // ═══════════════════════════════════════════════════════════════════════════
  // 예측 조합 생성 — 5세트
  // 구조: 합 100~170, 저번(≤22) 2~4개, 홀수 2~4개, 연번쌍 ≤2
  // ═══════════════════════════════════════════════════════════════════════════
  const sets: PredictionSet[] = []
  const usedKeys = new Set<string>()

  // 가중치 배열 (인덱스 i → num i+1)
  const weights = scoreMap.map(s => Math.max(0.5, s.total + 1))

  let attempts = 0
  while (sets.length < 5 && attempts < 20000) {
    attempts++

    // 가중치 기반으로 6개 비중복 선택
    const pickedSet = new Set<number>()
    const available = [...weights]
    let tries = 0
    while (pickedSet.size < 6 && tries < 100) {
      tries++
      const totalW = available.reduce((s, w) => s + w, 0)
      let rand = Math.random() * totalW
      let chosen = -1
      for (let i = 0; i < 45; i++) {
        rand -= available[i]
        if (rand <= 0) { chosen = i + 1; break }
      }
      if (chosen === -1) chosen = 45
      if (!pickedSet.has(chosen)) {
        pickedSet.add(chosen)
        available[chosen - 1] = 0 // 재선택 방지
      }
    }

    if (pickedSet.size < 6) continue

    const sorted6 = Array.from(pickedSet).sort((a, b) => a - b)
    const sum  = sorted6.reduce((s, n) => s + n, 0)
    const odd  = sorted6.filter(n => n % 2 === 1).length
    const low  = sorted6.filter(n => n <= 22).length
    let consec = 0
    for (let i = 0; i < sorted6.length - 1; i++)
      if (sorted6[i + 1] - sorted6[i] === 1) consec++

    if (sum < 100 || sum > 170)   continue
    if (odd < 2    || odd > 4)    continue
    if (low < 2    || low > 4)    continue
    if (consec > 2)               continue

    const key = sorted6.join(',')
    if (usedKeys.has(key)) continue
    usedKeys.add(key)

    // 번호별 근거 수집 (번호당 가장 높은 점수 근거 1개)
    const setReasons: string[] = sorted6.flatMap(n => {
      const entry = scoreMap.find(s => s.num === n)
      if (!entry || entry.reasons.length === 0) return []
      return [`[${n}번] ${entry.reasons[0]}`]
    })

    sets.push({
      numbers: sorted6,
      reasons: setReasons,
      structureInfo: { sum, odd, even: 6 - odd, low, high: 6 - low, consecutivePairs: consec },
    })
  }

  return { sets, moduleReports: reports, scoreboard }
}

// ═══════════════════════════════════════════════════════════════════════════
// 연금복권 전용 예측 엔진
// ═══════════════════════════════════════════════════════════════════════════

export interface PensionDigitScore {
  pos: number    // 1~6 (자리)
  digit: number  // 0~9
  total: number
  reasons: string[]
  scores: {
    trend: number      // 모듈1: 자리별 흐름(계단)
    carryover: number  // 모듈2: 이월·이웃수
    cold: number       // 모듈3: 장기 미출현
    section: number    // 모듈4: 저고 구간 분석
    pattern: number    // 모듈5: 전체 패턴(연번·끝수)
  }
}

export interface PensionPredictionSet {
  numbers: number[]   // length 6, each 0-9
  reasons: string[]
}

export interface PensionPredictionResult {
  sets: PensionPredictionSet[]
  moduleReports: {
    trend: string[]
    carryover: string[]
    cold: string[]
    section: string[]
    pattern: string[]
  }
  scoreboard: PensionDigitScore[]  // top 20 (pos, digit) 쌍
}

function getPensionNums(row: PensionLotteryData): number[] {
  return [row.num1, row.num2, row.num3, row.num4, row.num5, row.num6]
}

/**
 * 연금복권 다음 차수 예측 (5모듈 자리별 분석)
 * @param allRows    필터된 연금복권 당첨 데이터
 * @param windowSize 최근 회차 분석 범위 (기본 15)
 */
export function runPensionPredictionEngine(
  allRows: PensionLotteryData[],
  windowSize: number = 15,
): PensionPredictionResult {
  const EMPTY: PensionPredictionResult = {
    sets: [],
    moduleReports: { trend: [], carryover: [], cold: [], section: [], pattern: [] },
    scoreboard: [],
  }
  if (allRows.length < 5) return EMPTY

  // 회차 오름차순
  const sorted = [...allRows].sort((a, b) => a.round - b.round)
  const recent = sorted.slice(-Math.max(windowSize, 5))
  const last   = sorted[sorted.length - 1]
  const lastNums = getPensionNums(last)

  // 자리별 (pos 0~5) × 숫자 (0~9) 스코어 행렬
  const scoreMatrix: PensionDigitScore[][] = Array.from({ length: 6 }, (_, pos) =>
    Array.from({ length: 10 }, (_, digit) => ({
      pos: pos + 1, digit, total: 0, reasons: [],
      scores: { trend: 0, carryover: 0, cold: 0, section: 0, pattern: 0 },
    }))
  )

  // 자리별 전체 빈도
  const freqPos: number[][] = Array.from({ length: 6 }, () => Array(10).fill(0))
  sorted.forEach(row => {
    getPensionNums(row).forEach((d, pos) => { freqPos[pos][d]++ })
  })

  const reports = {
    trend:     [] as string[],
    carryover: [] as string[],
    cold:      [] as string[],
    section:   [] as string[],
    pattern:   [] as string[],
  }

  const totalRounds = sorted.length

  // ───────────────────────────────────────────────────────────────────────
  // Module 1: 자리별 흐름 (계단/추세) — 최근 N회에서 각 자리 값 증감 패턴 감지
  // ───────────────────────────────────────────────────────────────────────
  {
    const recentNums = recent.map(row => getPensionNums(row))
    for (let pos = 0; pos < 6; pos++) {
      const values = recentNums.map(n => n[pos])
      // 연속 증가 체인 확인 (+1)
      for (const step of [1, -1]) {
        let chainLen = 0
        let cur = values[values.length - 1]
        for (let i = values.length - 1; i >= 0; i--) {
          if (values[i] === cur) { chainLen++; cur = cur - step } else break
        }
        if (chainLen >= 2) {
          const next = values[values.length - 1] + step
          if (next >= 0 && next <= 9) {
            const score = chainLen * 5
            scoreMatrix[pos][next].scores.trend += score
            const sign = step > 0 ? `+${step}` : `${step}`
            const msg = `[${pos + 1}번자리] ${chainLen}회 연속 ${sign} 흐름 → 다음 예측: ${next}`
            scoreMatrix[pos][next].reasons.push(msg)
            reports.trend.push(msg)
          }
        }
      }
      // 최근 3회 평균 추세
      if (values.length >= 3) {
        const last3 = values.slice(-3)
        const avg = last3.reduce((s, v) => s + v, 0) / 3
        const trending = last3[2] - last3[0]
        if (Math.abs(trending) >= 2) {
          const pred = Math.max(0, Math.min(9, Math.round(last3[2] + trending / 2)))
          scoreMatrix[pos][pred].scores.trend += 3
          const msg = `[${pos + 1}번자리] 최근 3회 추세(${last3.join('→')}) → 예측: ${pred}`
          scoreMatrix[pos][pred].reasons.push(msg)
          if (!reports.trend.some(r => r.startsWith(`[${pos + 1}번자리] 최근 3회`)))
            reports.trend.push(msg)
        }
      }
    }
    if (reports.trend.length === 0)
      reports.trend.push('최근 회차에서 뚜렷한 자리별 흐름 패턴 미감지')
  }

  // ───────────────────────────────────────────────────────────────────────
  // Module 2: 이월·이웃수 — 직전 회차 각 자리 값의 ±1~2 재출현 가중치
  // ───────────────────────────────────────────────────────────────────────
  {
    for (let pos = 0; pos < 6; pos++) {
      const lastDigit = lastNums[pos]
      for (const nb of [lastDigit - 2, lastDigit - 1, lastDigit + 1, lastDigit + 2]) {
        if (nb < 0 || nb > 9) continue
        const freq = freqPos[pos][nb]
        if (freq === 0) continue
        const avgGap = totalRounds / freq
        // 마지막 출현 이후 경과
        let lastSeenIdx = -1
        for (let r = sorted.length - 1; r >= 0; r--) {
          if (getPensionNums(sorted[r])[pos] === nb) { lastSeenIdx = r; break }
        }
        const gap = sorted.length - 1 - lastSeenIdx
        const ratio = gap / avgGap
        if (ratio >= 0.5) {
          const score = Math.min(6, Math.ceil(ratio * 2))
          scoreMatrix[pos][nb].scores.carryover += score
          const msg = `[${pos + 1}번자리] 이웃수(${lastDigit}→${nb}): 평균${avgGap.toFixed(1)}회 주기, 현재 ${gap}회 미출현`
          scoreMatrix[pos][nb].reasons.push(msg)
          reports.carryover.push(msg)
        }
      }
      // 이월수(동일 자리 동일 값 재출현) 가중치
      const freq = freqPos[pos][lastDigit]
      if (freq > 0) {
        const avgGap = totalRounds / freq
        let prevIdx = -1
        for (let r = sorted.length - 2; r >= 0; r--) {
          if (getPensionNums(sorted[r])[pos] === lastDigit) { prevIdx = r; break }
        }
        const gapFromPrev = sorted.length - 2 - prevIdx
        if (gapFromPrev > avgGap * 0.4) {
          scoreMatrix[pos][lastDigit].scores.carryover += 3
          const msg = `[${pos + 1}번자리] 이월수(${lastDigit}): 직전 회차 재출현 타이밍 가중치`
          scoreMatrix[pos][lastDigit].reasons.push(msg)
          if (!reports.carryover.some(r => r === msg)) reports.carryover.push(msg)
        }
      }
    }
    if (reports.carryover.length === 0)
      reports.carryover.push('이월·이웃수 분석: 유효한 재출현 신호 없음')
  }

  // ───────────────────────────────────────────────────────────────────────
  // Module 3: 장기 미출현 — 자리별로 오래 나오지 않은 숫자 가중치
  // ───────────────────────────────────────────────────────────────────────
  {
    for (let pos = 0; pos < 6; pos++) {
      type ColdEntry = { digit: number; gap: number; avgGap: number; ratio: number }
      const coldList: ColdEntry[] = []
      for (let d = 0; d <= 9; d++) {
        const freq = freqPos[pos][d]
        if (freq === 0) continue
        const avgGap = totalRounds / freq
        let lastSeenIdx = -1
        for (let r = sorted.length - 1; r >= 0; r--) {
          if (getPensionNums(sorted[r])[pos] === d) { lastSeenIdx = r; break }
        }
        const gap = lastSeenIdx === -1 ? totalRounds : sorted.length - 1 - lastSeenIdx
        const ratio = gap / avgGap
        if (ratio >= 1.4) coldList.push({ digit: d, gap, avgGap: Math.round(avgGap * 10) / 10, ratio })
      }
      coldList.sort((a, b) => b.ratio - a.ratio).slice(0, 3).forEach(c => {
        const score = Math.round(c.ratio * 3)
        scoreMatrix[pos][c.digit].scores.cold += score
        const msg = `[${pos + 1}번자리] 장기미출현(${c.digit}): ${c.gap}회 미출현 (평균 ${c.avgGap}회의 ${(c.ratio * 100).toFixed(0)}%)`
        scoreMatrix[pos][c.digit].reasons.push(msg)
        reports.cold.push(msg)
      })
    }
    if (reports.cold.length === 0)
      reports.cold.push('장기 미출현 숫자 없음 (모든 자리 정상 주기 내 출현)')
  }

  // ───────────────────────────────────────────────────────────────────────
  // Module 4: 저고 구간 분석 — 자리별 0~4(저) vs 5~9(고) 최근 편중 감지
  // ───────────────────────────────────────────────────────────────────────
  {
    const lookback = Math.min(10, recent.length)
    const recentWindow = recent.slice(-lookback)
    for (let pos = 0; pos < 6; pos++) {
      const vals = recentWindow.map(r => getPensionNums(r)[pos])
      const lowCnt  = vals.filter(v => v <= 4).length
      const highCnt = vals.length - lowCnt
      const lowRatio  = lowCnt  / lookback
      const highRatio = highCnt / lookback
      // 한쪽이 70% 초과 → 반대쪽 가중치
      if (lowRatio >= 0.7) {
        // 고번(5~9) 반등 기대
        for (let d = 5; d <= 9; d++) {
          scoreMatrix[pos][d].scores.section += 4
          scoreMatrix[pos][d].reasons.push(`[${pos + 1}번자리] 저번 편중(${(lowRatio * 100).toFixed(0)}%) → 고번(5~9) 반등 기대`)
        }
        reports.section.push(`[${pos + 1}번자리]: 최근 ${lookback}회 저번(0~4) ${lowCnt}회 편중 → 고번 반등 예상`)
      } else if (highRatio >= 0.7) {
        // 저번(0~4) 반등 기대
        for (let d = 0; d <= 4; d++) {
          scoreMatrix[pos][d].scores.section += 4
          scoreMatrix[pos][d].reasons.push(`[${pos + 1}번자리] 고번 편중(${(highRatio * 100).toFixed(0)}%) → 저번(0~4) 반등 기대`)
        }
        reports.section.push(`[${pos + 1}번자리]: 최근 ${lookback}회 고번(5~9) ${highCnt}회 편중 → 저번 반등 예상`)
      }
    }
    if (reports.section.length === 0)
      reports.section.push('자리별 저고 분포 균형 양호 (편중 없음)')
  }

  // ───────────────────────────────────────────────────────────────────────
  // Module 5: 전체 패턴 — 끝수·연번·홀짝 패턴 분석
  // ───────────────────────────────────────────────────────────────────────
  {
    const lookback = Math.min(10, recent.length)
    const recentWindow = recent.slice(-lookback)

    // 자리별 최근 강세 숫자 (최다 출현 TOP 2) 가중치
    for (let pos = 0; pos < 6; pos++) {
      const cnt = Array(10).fill(0)
      recentWindow.forEach(r => cnt[getPensionNums(r)[pos]]++)
      const ranked = cnt.map((c, d) => ({ digit: d, count: c })).sort((a, b) => b.count - a.count)
      // TOP 2
      ranked.slice(0, 2).forEach(({ digit, count }) => {
        if (count >= 2) {
          scoreMatrix[pos][digit].scores.pattern += Math.min(5, count)
          const msg = `[${pos + 1}번자리] 최근 강세(${digit}): 최근 ${lookback}회 ${count}번 출현`
          scoreMatrix[pos][digit].reasons.push(msg)
          reports.pattern.push(msg)
        }
      })
      // 약세(Bottom 2) 소폭 반등 가중치
      ranked.slice(-2).forEach(({ digit, count }) => {
        if (count === 0 || count <= 1) {
          scoreMatrix[pos][digit].scores.pattern += 1
        }
      })
    }

    // 직전 회차 전체 합산과 전체 평균의 차이 분석
    const recentSums = recentWindow.map(r => getPensionNums(r).reduce((s, v) => s + v, 0))
    const avgSum = recentSums.reduce((s, v) => s + v, 0) / recentSums.length
    const lastSum = recentSums[recentSums.length - 1]
    if (lastSum < avgSum - 5) {
      // 직전 합이 낮음 → 고번 가중치
      for (let pos = 0; pos < 6; pos++)
        for (let d = 5; d <= 9; d++) scoreMatrix[pos][d].scores.pattern += 1
      reports.pattern.push(`직전 총합 ${lastSum} (평균 ${avgSum.toFixed(1)} 대비 낮음) → 고번 소폭 가중`)
    } else if (lastSum > avgSum + 5) {
      // 직전 합이 높음 → 저번 가중치
      for (let pos = 0; pos < 6; pos++)
        for (let d = 0; d <= 4; d++) scoreMatrix[pos][d].scores.pattern += 1
      reports.pattern.push(`직전 총합 ${lastSum} (평균 ${avgSum.toFixed(1)} 대비 높음) → 저번 소폭 가중`)
    }

    if (reports.pattern.length === 0)
      reports.pattern.push('전체 패턴 분석: 특별한 편중 신호 없음')
  }

  // ───────────────────────────────────────────────────────────────────────
  // 각 (pos, digit) 총점 계산
  // ───────────────────────────────────────────────────────────────────────
  const allScores: PensionDigitScore[] = []
  for (let pos = 0; pos < 6; pos++) {
    for (let d = 0; d <= 9; d++) {
      const s = scoreMatrix[pos][d]
      s.total = Math.max(0,
        s.scores.trend + s.scores.carryover + s.scores.cold + s.scores.section + s.scores.pattern
      )
      allScores.push(s)
    }
  }

  const scoreboard = [...allScores].sort((a, b) => b.total - a.total).slice(0, 20)

  // ───────────────────────────────────────────────────────────────────────
  // 예측 세트 생성 — 5세트
  // 각 자리별로 가중치 기반 랜덤 선택, 구조 조건 체크 후 채택
  // ───────────────────────────────────────────────────────────────────────
  const sets: PensionPredictionSet[] = []
  const usedKeys = new Set<string>()

  let attempts = 0
  while (sets.length < 5 && attempts < 10000) {
    attempts++
    const numbers: number[] = []
    for (let pos = 0; pos < 6; pos++) {
      // 해당 자리 가중치 배열 (0~9)
      const posWeights = scoreMatrix[pos].map(s => Math.max(0.5, s.total + 1))
      const totalW = posWeights.reduce((s, w) => s + w, 0)
      let rand = Math.random() * totalW
      let chosen = 0
      for (let d = 0; d <= 9; d++) {
        rand -= posWeights[d]
        if (rand <= 0) { chosen = d; break }
      }
      numbers.push(chosen)
    }

    // 구조 조건 검사 (최적 필터 기준)
    const sum = numbers.reduce((s, v) => s + v, 0)
    if (sum < 10 || sum > 50) continue  // 너무 극단 제외

    const key = numbers.join(',')
    if (usedKeys.has(key)) continue
    usedKeys.add(key)

    // 번호별 근거
    const reasons: string[] = numbers.flatMap((d, pos) => {
      const entry = scoreMatrix[pos][d]
      if (!entry || entry.reasons.length === 0) return [`[${pos + 1}번자리] ${d} (빈도 기반 선택)`]
      return [`[${pos + 1}번자리] ${d}: ${entry.reasons[0]}`]
    })

    sets.push({ numbers, reasons })
  }

  return { sets, moduleReports: reports, scoreboard }
}
