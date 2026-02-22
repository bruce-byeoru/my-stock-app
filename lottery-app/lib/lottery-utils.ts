import { LottoData, PensionLotteryData, NumberSet } from '@/types/lottery'

/**
 * 최신 로또 회차를 계산합니다
 * 첫 회차: 2002년 12월 7일 (토요일)
 */
export function getCurrentLottoRound(): number {
  const firstDrawDate = new Date('2002-12-07')
  const today = new Date()
  
  const diffTime = today.getTime() - firstDrawDate.getTime()
  const diffWeeks = Math.floor(diffTime / (1000 * 60 * 60 * 24 * 7))
  
  return diffWeeks + 1
}

/**
 * 최신 연금복권 회차를 계산합니다
 * 첫 회차: 2020년 02월 (월별 추첨)
 */
export function getCurrentPensionRound(): number {
  const firstDrawDate = new Date('2020-02-01')
  const today = new Date()
  
  const yearDiff = today.getFullYear() - firstDrawDate.getFullYear()
  const monthDiff = today.getMonth() - firstDrawDate.getMonth()
  
  return (yearDiff * 12) + monthDiff + 1
}

/**
 * 1~45 범위의 랜덤 로또 번호 6개를 생성합니다 (중복 없음, 정렬됨)
 */
export function generateLottoNumbers(size: number = 6): number[] {
  const numbers: number[] = []

  while (numbers.length < size) {
    const num = Math.floor(Math.random() * 45) + 1
    if (!numbers.includes(num)) {
      numbers.push(num)
    }
  }

  return numbers.sort((a, b) => a - b)
}

/**
 * 0~9 범위의 랜덤 연금복권 번호 6개를 생성합니다 (중복 허용)
 */
export function generatePensionNumbers(size: number = 6): number[] {
  const numbers: number[] = []

  for (let i = 0; i < size; i++) {
    numbers.push(Math.floor(Math.random() * 10))
  }

  return numbers
}

/**
 * 여러 개의 고유한 로또 번호 세트를 생성합니다 (세트 간 중복 방지)
 */
export function generateUniqueLottoSets(count: number, size: number = 6): NumberSet[] {
  const sets: NumberSet[] = []
  const setStrings = new Set<string>()
  
  while (sets.length < count) {
    const numbers = generateLottoNumbers(size)
    const setString = numbers.join(',')
    
    if (!setStrings.has(setString)) {
      setStrings.add(setString)
      // compute bitmask (bit 0 -> number 1)
      let mask = 0n
      for (const n of numbers) {
        mask |= (1n << BigInt(n - 1))
      }
      sets.push({
        id: sets.length + 1,
        numbers,
        stats: {
          rank1: 0,
          rank2: 0,
          rank3: 0,
          rank4: 0,
          rank5: 0,
        },
        mask,
      })
    }
  }
  
  return sets
}

/**
 * 요구 조건(predicate)에 맞는 고유한 로또 세트를 생성합니다.
 * predicate가 주어지면 해당 조건을 만족하는 세트만 카운트에 포함시킵니다.
 * 너무 엄격한 predicate로 무한 루프가 도는 것을 방지하기 위해 시도 횟수 제한을 둡니다.
 */
export function generateFilteredUniqueLottoSets(
  count: number,
  size: number = 6,
  predicate?: (nums: number[]) => boolean
): NumberSet[] {
  const sets: NumberSet[] = []
  const setStrings = new Set<string>()
  // NOTE: no artificial cap here — will keep generating until `count` sets matching
  // the predicate are found. Caller must be aware this can take a long time for
  // very strict predicates and large `count` values.
  while (sets.length < count) {
    const numbers = generateLottoNumbers(size)
    const setString = numbers.join(',')
    if (setStrings.has(setString)) continue
    if (predicate && !predicate(numbers)) continue

    setStrings.add(setString)
    // compute bitmask
    let mask = 0n
    for (const n of numbers) mask |= (1n << BigInt(n - 1))
    sets.push({
      id: sets.length + 1,
      numbers,
      stats: { rank1: 0, rank2: 0, rank3: 0, rank4: 0, rank5: 0 },
      mask,
    })
  }

  return sets
}

function popcountBigInt(n: bigint) {
  // Kernighan's bit counting
  let x = n < 0n ? ~n : n
  let c = 0
  while (x) {
    x &= x - 1n
    c++
  }
  return c
}

/**
 * 여러 개의 고유한 연금복권 번호 세트를 생성합니다
 */
export function generateUniquePensionSets(count: number, size: number = 6): NumberSet[] {
  const sets: NumberSet[] = []
  const setStrings = new Set<string>()
  
  while (sets.length < count) {
    const numbers = generatePensionNumbers(size)
    const setString = numbers.join(',')
    
    if (!setStrings.has(setString)) {
      setStrings.add(setString)
      sets.push({
        id: sets.length + 1,
        numbers,
        stats: {
          rank1: 0,
          rank2: 0,
          rank3: 0,
          rank4: 0,
          rank5: 0,
          rank6: 0,
          rank7: 0,
        },
      })
    }
  }
  
  return sets
}

/**
 * 로또 당첨 등수를 확인합니다
 * @returns 등수 (1~5) 또는 0 (미당첨)
 */
export function checkLottoRank(
  userNumbers: number[],
  winningNumbers: number[],
  bonusNumber: number
): number {
  const matches = userNumbers.filter(num => winningNumbers.includes(num)).length
  const hasBonus = userNumbers.includes(bonusNumber)
  
  if (matches === 6) return 1 // 1등: 6개 일치
  if (matches === 5 && hasBonus) return 2 // 2등: 5개 일치 + 보너스
  if (matches === 5) return 3 // 3등: 5개 일치
  if (matches === 4) return 4 // 4등: 4개 일치
  if (matches === 3) return 5 // 5등: 3개 일치
  
  return 0 // 미당첨
}

/**
 * 연금복권 당첨 등수를 확인합니다 (조 번호 제외, 숫자만 비교)
 * @returns 등수 (2~7) 또는 0 (미당첨)
 */
export function checkPensionRank(
  userNumbers: number[],
  winningNumbers: number[]
): number {
  // 앞에서부터 순서대로 일치해야 함
  let matches = 0
  
  for (let i = 0; i < 6; i++) {
    if (userNumbers[i] === winningNumbers[i]) {
      matches++
    } else {
      break // 순서가 틀리면 중단
    }
  }
  
  if (matches === 6) return 2 // 2등: 6자리 일치
  if (matches === 5) return 3 // 3등: 5자리 일치
  if (matches === 4) return 4 // 4등: 4자리 일치
  if (matches === 3) return 5 // 5등: 3자리 일치
  if (matches === 2) return 6 // 6등: 2자리 일치
  if (matches === 1) return 7 // 7등: 1자리 일치
  
  return 0 // 미당첨
}

/**
 * 로또 데이터로 시뮬레이션을 실행합니다
 */
export function simulateLotto(
  numberSets: NumberSet[],
  lottoData: LottoData[]
): NumberSet[] {
  // 각 세트의 통계 초기화
  const updatedSets = numberSets.map(set => ({
    ...set,
    stats: {
      rank1: 0,
      rank2: 0,
      rank3: 0,
      rank4: 0,
      rank5: 0,
    },
  }))
  // 비트마스크 기반 매칭 (set.mask, drawMask 사용)
  for (const draw of lottoData) {
    const drawMask = (1n << BigInt(draw.drwtNo1 - 1)) | (1n << BigInt(draw.drwtNo2 - 1)) | (1n << BigInt(draw.drwtNo3 - 1)) |
      (1n << BigInt(draw.drwtNo4 - 1)) | (1n << BigInt(draw.drwtNo5 - 1)) | (1n << BigInt(draw.drwtNo6 - 1))
    const bonusBit = 1n << BigInt(draw.bnusNo - 1)

    for (const set of updatedSets) {
      let mask = (set as any).mask as bigint | undefined
      if (mask === undefined) {
        mask = 0n
        for (const n of set.numbers) mask |= (1n << BigInt(n - 1))
        ;(set as any).mask = mask
      }

      const common = mask & drawMask
      const matches = popcountBigInt(common)
      const hasBonus = (mask & bonusBit) !== 0n

      let rank = 0
      if (matches === 6) rank = 1
      else if (matches === 5 && hasBonus) rank = 2
      else if (matches === 5) rank = 3
      else if (matches === 4) rank = 4
      else if (matches === 3) rank = 5

      if (rank === 1) set.stats.rank1++
      else if (rank === 2) set.stats.rank2++
      else if (rank === 3) set.stats.rank3++
      else if (rank === 4) set.stats.rank4++
      else if (rank === 5) set.stats.rank5++
    }
  }
  
  return updatedSets
}

/**
 * 연금복권 데이터로 시뮬레이션을 실행합니다
 */
export function simulatePension(
  numberSets: NumberSet[],
  pensionData: PensionLotteryData[]
): NumberSet[] {
  // 각 세트의 통계 초기화
  const updatedSets = numberSets.map(set => ({
    ...set,
    stats: {
      rank1: 0,
      rank2: 0,
      rank3: 0,
      rank4: 0,
      rank5: 0,
      rank6: 0,
      rank7: 0,
    },
  }))
  
  // 각 회차의 당첨 번호와 비교
  for (const draw of pensionData) {
    const winningNumbers = [
      draw.num1,
      draw.num2,
      draw.num3,
      draw.num4,
      draw.num5,
      draw.num6,
    ]
    
    for (const set of updatedSets) {
      const rank = checkPensionRank(set.numbers, winningNumbers)
      
      if (rank === 2) set.stats.rank2++
      else if (rank === 3) set.stats.rank3++
      else if (rank === 4) set.stats.rank4++
      else if (rank === 5) set.stats.rank5++
      else if (rank === 6) set.stats.rank6!++
      else if (rank === 7) set.stats.rank7!++
    }
  }
  
  return updatedSets
}

/**
 * 당첨 통계를 기반으로 번호 세트를 정렬합니다 (높은 등수 우선)
 */
export function sortByWinningStats(sets: NumberSet[]): NumberSet[] {
  // Sort by total wins across all ranks (sum of stats), descending.
  // Tie-breaker: prefer higher counts in higher ranks (rank1, rank2, ...).
  return [...sets].sort((a, b) => {
    const sumA = Object.values(a.stats || {}).reduce((s, v) => s + (Number(v) || 0), 0)
    const sumB = Object.values(b.stats || {}).reduce((s, v) => s + (Number(v) || 0), 0)
    if (sumA !== sumB) return sumB - sumA

    // tie-breaker by individual ranks (rank1, rank2, ...)
    for (let i = 1; i <= 7; i++) {
      const key = (`rank${i}` as keyof typeof a.stats)
      const va = Number(a.stats[key] || 0)
      const vb = Number(b.stats[key] || 0)
      if (va !== vb) return vb - va
    }
    return 0
  })
}

/**
 * 상위 N개의 번호 세트를 반환합니다
 */
export function getTopSets(sets: NumberSet[], count: number = 10): NumberSet[] {
  const sorted = sortByWinningStats(sets)
  return sorted.slice(0, count)
}
