import { LottoData, PensionLotteryData } from '@/types/lottery'

/**
 * 특정 회차의 로또 데이터를 가져옵니다
 */
export async function fetchLottoData(drwNo: number): Promise<LottoData | null> {
  try {
    const response = await fetch(`/api/lotto?drwNo=${drwNo}`)
    
    if (!response.ok) {
      return null
    }
    
    const data = await response.json()
    
    // API가 실패한 경우
    if (data.returnValue === 'fail') {
      return null
    }
    
    return data as LottoData
  } catch (error) {
    console.error('Failed to fetch lotto data:', error)
    return null
  }
}

/**
 * 여러 회차의 로또 데이터를 배치로 가져옵니다
 */
export async function fetchLottoDataRange(
  startRound: number,
  endRound: number,
  onProgress?: (current: number, total: number) => void
): Promise<LottoData[]> {
  const results: LottoData[] = []
  const total = endRound - startRound + 1
  
  // 병렬 요청으로 성능 향상 (한 번에 10개씩)
  const batchSize = 10
  
  for (let i = startRound; i <= endRound; i += batchSize) {
    const batchEnd = Math.min(i + batchSize - 1, endRound)
    const promises = []
    
    for (let round = i; round <= batchEnd; round++) {
      promises.push(fetchLottoData(round))
    }
    
    const batchResults = await Promise.all(promises)
    
    for (const data of batchResults) {
      if (data) {
        results.push(data)
      }
    }
    
    if (onProgress) {
      onProgress(results.length, total)
    }
  }
  
  return results
}

/**
 * 특정 회차의 연금복권 데이터를 가져옵니다
 */
export async function fetchPensionData(round: number): Promise<PensionLotteryData | null> {
  try {
    const response = await fetch(`/api/pension?round=${round}`)
    
    if (!response.ok) {
      return null
    }
    
    const data = await response.json()
    return data as PensionLotteryData
  } catch (error) {
    console.error('Failed to fetch pension data:', error)
    return null
  }
}

/**
 * 여러 회차의 연금복권 데이터를 배치로 가져옵니다
 */
export async function fetchPensionDataRange(
  startRound: number,
  endRound: number,
  onProgress?: (current: number, total: number) => void
): Promise<PensionLotteryData[]> {
  const results: PensionLotteryData[] = []
  const total = endRound - startRound + 1
  
  const batchSize = 5
  
  for (let i = startRound; i <= endRound; i += batchSize) {
    const batchEnd = Math.min(i + batchSize - 1, endRound)
    const promises = []
    
    for (let round = i; round <= batchEnd; round++) {
      promises.push(fetchPensionData(round))
    }
    
    const batchResults = await Promise.all(promises)
    
    for (const data of batchResults) {
      if (data) {
        results.push(data)
      }
    }
    
    if (onProgress) {
      onProgress(results.length, total)
    }
  }
  
  return results
}

/**
 * 가상의 로또 데이터를 생성합니다 (API 실패 시 대비)
 */
export function generateMockLottoData(startRound: number, endRound: number): LottoData[] {
  const results: LottoData[] = []
  
  for (let round = startRound; round <= endRound; round++) {
    const numbers = Array.from({ length: 45 }, (_, i) => i + 1)
      .sort(() => Math.random() - 0.5)
      .slice(0, 7)
      .sort((a, b) => a - b)
    
    results.push({
      drwNo: round,
      drwNoDate: '2024-01-01',
      drwtNo1: numbers[0],
      drwtNo2: numbers[1],
      drwtNo3: numbers[2],
      drwtNo4: numbers[3],
      drwtNo5: numbers[4],
      drwtNo6: numbers[5],
      bnusNo: numbers[6],
      firstWinamnt: 2000000000,
      firstPrzwnerCo: 10,
    })
  }
  
  return results
}

/**
 * 가상의 연금복권 데이터를 생성합니다
 */
export function generateMockPensionData(startRound: number, endRound: number): PensionLotteryData[] {
  const results: PensionLotteryData[] = []
  
  for (let round = startRound; round <= endRound; round++) {
    results.push({
      round,
      drawDate: '2024-01-01',
      group: Math.floor(Math.random() * 5) + 1,
      num1: Math.floor(Math.random() * 10),
      num2: Math.floor(Math.random() * 10),
      num3: Math.floor(Math.random() * 10),
      num4: Math.floor(Math.random() * 10),
      num5: Math.floor(Math.random() * 10),
      num6: Math.floor(Math.random() * 10),
    })
  }
  
  return results
}
