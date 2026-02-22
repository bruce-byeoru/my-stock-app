'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Ticket, Play, BarChart3, Loader2, ChevronDown, ChevronUp,
  Filter, Upload, Sparkles, RefreshCw, List, Trash2, Eye,
  CheckCircle2, XCircle, Clock,
} from 'lucide-react'
import {
  getCurrentLottoRound,
  getCurrentPensionRound,
  generateLottoNumbers,
  generatePensionNumbers,
  simulateLotto,
  simulatePension,
  getTopSets,
} from '@/lib/lottery-utils'
import { runPredictionEngine, PredictionResult, runPensionPredictionEngine, PensionPredictionResult, PensionDigitScore } from '@/lib/prediction-engine'
import { NumberSet, LottoData, PensionLotteryData, SimulationSession } from '@/types/lottery'

type TabType = 'lotto' | 'pension' | 'register'

/** 이 개수를 초과하면 백그라운드(Web Worker) 처리; 버튼이 즉시 해제됨 */
const BG_THRESHOLD = 5000

// ── 공 색상 ──────────────────────────────────────────────────────────────
function ballColor(n: number) {
  if (n <= 10) return 'bg-yellow-400 text-yellow-900'
  if (n <= 20) return 'bg-blue-500 text-white'
  if (n <= 30) return 'bg-red-500 text-white'
  if (n <= 40) return 'bg-gray-600 text-white'
  return 'bg-green-500 text-white'
}
function LottoBall({ n, sm }: { n: number; sm?: boolean }) {
  return (
    <span className={`${sm ? 'w-7 h-7 text-xs' : 'w-9 h-9 text-sm'} ${ballColor(n)} rounded-full flex items-center justify-center font-bold shrink-0`}>
      {n}
    </span>
  )
}
const PENSION_POS_COLORS = [
  'border-gray-300 text-gray-500',        // 0 = 위치 미지정
  'border-red-500 text-red-500',          // 1번째
  'border-orange-400 text-orange-500',    // 2번째
  'border-yellow-400 text-yellow-600',    // 3번째
  'border-cyan-400 text-cyan-600',        // 4번째
  'border-purple-400 text-purple-500',    // 5번째
  'border-gray-400 text-gray-500',        // 6번째
]
function PensionDigit({ n, pos }: { n: number; pos?: number }) {
  const color = PENSION_POS_COLORS[pos ?? 0] ?? PENSION_POS_COLORS[0]
  return (
    <span className={`w-8 h-8 rounded-full border-2 bg-white flex items-center justify-center text-sm font-bold shrink-0 ${color}`}>
      {n}
    </span>
  )
}

// ── 최적 필터 ────────────────────────────────────────────────────────────
function passOptimalFilter(nums: number[]): boolean {
  const s = [...nums].sort((a, b) => a - b)
  let consec = 0
  for (let i = 0; i < s.length - 1; i++) if (s[i + 1] - s[i] === 1) consec++
  if (consec > 1) return false
  const low = s.filter(n => n <= 22).length
  if (low < 2 || low > 4) return false
  const odd = s.filter(n => n % 2 === 1).length
  if (odd < 2 || odd > 4) return false
  const sum = s.reduce((a, b) => a + b, 0)
  return sum >= 100 && sum <= 180
}

function passHighFreqFilter(nums: number[]): boolean {
  if (!Array.isArray(nums) || nums.length !== 6) return false
  const s = [...nums].map(n => Number(n))
  if (s.some(n => isNaN(n) || n < 1 || n > 45)) return false
  if (new Set(s).size !== 6) return false
  s.sort((a, b) => a - b)
  for (let i = 0; i < s.length - 1; i++) if (s[i + 1] - s[i] === 1) return false
  const low = s.filter(n => n <= 22).length
  if (low !== 3) return false
  const odd = s.filter(n => n % 2 === 1).length
  if (odd !== 3) return false
  const sum = s.reduce((a, b) => a + b, 0)
  return sum >= 120 && sum <= 139
}

function getBadgeItems(nums: number[]): { label: string; ok: boolean }[] {
  const s = [...nums].sort((a, b) => a - b)
  let consec = 0
  for (let i = 0; i < s.length - 1; i++) if (s[i + 1] - s[i] === 1) consec++
  const low = s.filter(n => n <= 22).length
  const odd = s.filter(n => n % 2 === 1).length
  const sum = s.reduce((a, b) => a + b, 0)
  return [
    { label: `연번 ${consec}`, ok: consec <= 1 },
    { label: `저${low}:고${6 - low}`, ok: low >= 2 && low <= 4 },
    { label: `홀${odd}:짝${6 - odd}`, ok: odd >= 2 && odd <= 4 },
    { label: `합 ${sum}`, ok: sum >= 100 && sum <= 180 },
  ]
}

// ── 연금복권 필터 ────────────────────────────────────────────────────────
function passPensionOptimalFilter(nums: number[]): boolean {
  // 연번쌍: 인접 자리값 차이 1인 쌍 수 (자리 순서 기준)
  let consec = 0
  for (let i = 0; i < nums.length - 1; i++) if (Math.abs(nums[i + 1] - nums[i]) === 1) consec++
  if (consec > 2) return false
  // 저(0~4):고(5~9) 비율 2:4, 3:3, 4:2만
  const low = nums.filter(n => n <= 4).length
  if (low < 2 || low > 4) return false
  // 홀짝 비율 2:4, 3:3, 4:2만
  const odd = nums.filter(n => n % 2 === 1).length
  if (odd < 2 || odd > 4) return false
  // 총합 20~39
  const sum = nums.reduce((a, b) => a + b, 0)
  return sum >= 20 && sum <= 39
}

function passPensionHighFreqFilter(nums: number[]): boolean {
  // 연번 정확히 1쌍
  let consec = 0
  for (let i = 0; i < nums.length - 1; i++) if (Math.abs(nums[i + 1] - nums[i]) === 1) consec++
  if (consec !== 1) return false
  // 저고번 3:3
  const low = nums.filter(n => n <= 4).length
  if (low !== 3) return false
  // 홀짝 3:3
  const odd = nums.filter(n => n % 2 === 1).length
  if (odd !== 3) return false
  // 총합 20~29
  const sum = nums.reduce((a, b) => a + b, 0)
  return sum >= 20 && sum <= 29
}

function getPensionBadgeItems(nums: number[]): { label: string; ok: boolean }[] {
  let consec = 0
  for (let i = 0; i < nums.length - 1; i++) if (Math.abs(nums[i + 1] - nums[i]) === 1) consec++
  const low = nums.filter(n => n <= 4).length
  const odd = nums.filter(n => n % 2 === 1).length
  const sum = nums.reduce((a, b) => a + b, 0)
  return [
    { label: `연번 ${consec}`, ok: consec <= 2 },
    { label: `저${low}:고${6 - low}`, ok: low >= 2 && low <= 4 },
    { label: `홀${odd}:짝${6 - odd}`, ok: odd >= 2 && odd <= 4 },
    { label: `합 ${sum}`, ok: sum >= 20 && sum <= 39 },
  ]
}

function computeTotalWins(stats: any, lotteryType: 'lotto' | 'pension') {
  if (!stats) return 0
  if (lotteryType === 'lotto') {
    return (Number(stats.rank1) || 0) + (Number(stats.rank2) || 0) + (Number(stats.rank3) || 0) + (Number(stats.rank4) || 0) + (Number(stats.rank5) || 0)
  }
  return (Number(stats.rank1) || 0) + (Number(stats.rank2) || 0) + (Number(stats.rank3) || 0) + (Number(stats.rank4) || 0) + (Number(stats.rank5) || 0) + (Number(stats.rank6) || 0) + (Number(stats.rank7) || 0)
}

// ── 로또 분석 ────────────────────────────────────────────────────────────
function analyzeLotto(rows: LottoData[]) {
  const freq: Record<number, number> = {}
  const lowDist: Record<string, number> = {}
  const oddDist: Record<string, number> = {}
  const consecDist: Record<number, number> = {}
  const sumBins: Record<string, { count: number; start: number }> = {}
  let sumTotal = 0
  for (const r of rows) {
    const nums = [r.drwtNo1, r.drwtNo2, r.drwtNo3, r.drwtNo4, r.drwtNo5, r.drwtNo6]
    nums.forEach(n => { freq[n] = (freq[n] || 0) + 1 })
    const low = nums.filter(n => n <= 22).length
    lowDist[`${low}:${6 - low}`] = (lowDist[`${low}:${6 - low}`] || 0) + 1
    const odd = nums.filter(n => n % 2 === 1).length
    oddDist[`${odd}:${6 - odd}`] = (oddDist[`${odd}:${6 - odd}`] || 0) + 1
    const sorted = [...nums].sort((a, b) => a - b)
    let consec = 0
    for (let i = 0; i < sorted.length - 1; i++) if (sorted[i + 1] - sorted[i] === 1) consec++
    consecDist[consec] = (consecDist[consec] || 0) + 1
    const sum = nums.reduce((a, b) => a + b, 0)
    sumTotal += sum
    const binStart = Math.floor(sum / 20) * 20
    const key = `${binStart}~${binStart + 19}`
    if (!sumBins[key]) sumBins[key] = { count: 0, start: binStart }
    sumBins[key].count++
  }
  const frequent = Object.entries(freq).map(([n, c]) => ({ num: Number(n), count: c })).sort((a, b) => b.count - a.count).slice(0, 15)
  const sortedBins = Object.entries(sumBins).sort((a, b) => a[1].start - b[1].start).map(([label, v]) => ({ label, count: v.count }))
  return {
    frequent,
    lowEntries: Object.entries(lowDist).sort((a, b) => Number(a[0].split(':')[0]) - Number(b[0].split(':')[0])),
    oddEntries: Object.entries(oddDist).sort((a, b) => Number(a[0].split(':')[0]) - Number(b[0].split(':')[0])),
    consecEntries: Object.entries(consecDist).sort((a, b) => Number(a[0]) - Number(b[0])).map(([k, v]) => ({ k: Number(k), v })),
    sortedBins,
    maxBinCount: Math.max(...sortedBins.map(b => b.count)),
    sumAvg: Math.round((sumTotal / rows.length) * 10) / 10,
    total: rows.length,
  }
}

// ── 연금 분석 ────────────────────────────────────────────────────────────
function analyzePension(rows: PensionLotteryData[]) {
  const posFreq: { pos: number; digits: { digit: number; count: number }[] }[] = []
  const total = rows.length

  // 자리별 빈도
  for (let pos = 0; pos < 6; pos++) {
    const cnt: number[] = Array(10).fill(0)
    rows.forEach(r => { const n = [r.num1, r.num2, r.num3, r.num4, r.num5, r.num6][pos]; if (n !== undefined) cnt[n]++ })
    posFreq.push({ pos: pos + 1, digits: cnt.map((c, d) => ({ digit: d, count: c })).sort((a, b) => b.count - a.count) })
  }

  // 전체 빈도, 연번(인접값) 쌍 빈도, 연번 분포 및 합계
  const freqAll: Record<number, number> = {}
  const pairFreq: Record<string, number> = {}
  const oddDist: Record<string, number> = {}
  const consecDist: Record<number, number> = {}
  const sumBins: Record<string, { count: number; start: number }> = {}
  let sumTotal = 0
  // 동일번호 연속 출현: 인접 자리에서 같은 숫자가 연속으로 나온 경우
  const samePairFreq: Record<number, number> = {}
  let drawsWithAnyConsecSame = 0

  for (const r of rows) {
    const nums = [r.num1, r.num2, r.num3, r.num4, r.num5, r.num6]
    nums.forEach(n => { freqAll[n] = (freqAll[n] || 0) + 1 })
    // 동일번호 연속 출현: 인접 자리 값이 같은 경우 (예: 639566 → 5-6번째 자리 모두 6)
    let hasConsecSame = false
    for (let i = 0; i < nums.length - 1; i++) {
      if (nums[i] === nums[i + 1]) {
        hasConsecSame = true
        samePairFreq[nums[i]] = (samePairFreq[nums[i]] || 0) + 1
      }
    }
    if (hasConsecSame) drawsWithAnyConsecSame++
    // 자리 순서(원래 순서) 기준으로 인접 위치의 쌍을 순서쌍으로 집계
    let consec = 0
    for (let i = 0; i < nums.length - 1; i++) {
      const a = nums[i]
      const b = nums[i + 1]
      if (a === undefined || b === undefined) continue
      if (Math.abs(b - a) === 1) {
        consec++
        const key = `${a}-${b}` // 순서쌍으로 기록 (12와 21을 구분)
        pairFreq[key] = (pairFreq[key] || 0) + 1
      }
    }
    consecDist[consec] = (consecDist[consec] || 0) + 1
    const sum = nums.reduce((a, b) => a + b, 0)
    sumTotal += sum
    const odd = nums.filter(n => n % 2 === 1).length
    oddDist[`${odd}:${6 - odd}`] = (oddDist[`${odd}:${6 - odd}`] || 0) + 1
    const binStart = Math.floor(sum / 10) * 10
    const key = `${binStart}~${binStart + 9}`
    if (!sumBins[key]) sumBins[key] = { count: 0, start: binStart }
    sumBins[key].count++
  }

  const frequent = Object.entries(freqAll).map(([n, c]) => ({ num: Number(n), count: c })).sort((a, b) => b.count - a.count).slice(0, 10)
  const pairList = Object.entries(pairFreq).map(([k, v]) => ({ pair: k, count: v })).sort((a, b) => b.count - a.count).slice(0, 20)
  const sortedBins = Object.entries(sumBins).sort((a, b) => a[1].start - b[1].start).map(([label, v]) => ({ label, count: v.count }))

  // 저(0~4) : 고(5~9) 분포
  const lowHighDist: Record<string, number> = {}
  for (const r of rows) {
    const nums = [r.num1, r.num2, r.num3, r.num4, r.num5, r.num6]
    const low = nums.filter(n => n <= 4).length
    lowHighDist[`${low}:${6 - low}`] = (lowHighDist[`${low}:${6 - low}`] || 0) + 1
  }

  return {
    posFreq,
    total,
    frequent,
    consecEntries: Object.entries(consecDist).map(([k, v]) => ({ k: Number(k), v })),
    sortedBins,
    sumAvg: Math.round((sumTotal / rows.length) * 10) / 10,
    lowEntries: Object.entries(lowHighDist).sort((a, b) => Number(a[0].split(':')[0]) - Number(b[0].split(':')[0])),
    pairTop: pairList,
    oddEntries: Object.entries(oddDist).sort((a, b) => Number(a[0].split(':')[0]) - Number(b[0].split(':')[0])),
    samePairTop: Object.entries(samePairFreq)
      .map(([k, v]) => ({ digit: Number(k), count: v }))
      .sort((a, b) => b.count - a.count),
    drawsWithNoConsecSame: total - drawsWithAnyConsecSame,
  }
}

function predictLotto(analysis: ReturnType<typeof analyzeLotto>, filterOpt: boolean): number[][] {
  const { frequent, lowEntries, oddEntries, sumAvg } = analysis
  const pool = frequent.map(f => f.num)
  const bestLow = lowEntries.reduce<[string, number]>((a, b) => b[1] > a[1] ? b as [string, number] : a, ['3:3', 0])
  const targetLow = Number(bestLow[0].split(':')[0])
  const bestOdd = oddEntries.reduce<[string, number]>((a, b) => b[1] > a[1] ? b as [string, number] : a, ['3:3', 0])
  const targetOdd = Number(bestOdd[0].split(':')[0])
  const results: number[][] = []
  let tries = 0
  while (results.length < 5 && tries < 6000) {
    tries++
    const allNums = Array.from({ length: 45 }, (_, i) => i + 1)
    const weighted = [...pool, ...allNums.filter(n => !pool.includes(n)).sort(() => Math.random() - 0.5).slice(0, 20)].sort(() => Math.random() - 0.5)
    const picked = Array.from(new Set(weighted)).slice(0, 6).sort((a, b) => a - b)
    if (picked.length < 6) continue
    const low = picked.filter(n => n <= 22).length
    const odd = picked.filter(n => n % 2 === 1).length
    const sum = picked.reduce((a, b) => a + b, 0)
    if (Math.abs(low - targetLow) > 1) continue
    if (Math.abs(odd - targetOdd) > 1) continue
    if (Math.abs(sum - sumAvg) > 40) continue
    if (filterOpt && !passOptimalFilter(picked)) continue
    if (results.some(r => r.join(',') === picked.join(','))) continue
    results.push(picked)
  }
  return results
}

function predictPension(analysis: ReturnType<typeof analyzePension>): number[][] {
  return Array.from({ length: 5 }, () =>
    analysis.posFreq.map(pf => pf.digits.slice(0, 3)[Math.floor(Math.random() * 3)].digit)
  )
}

function formatElapsed(ms: number) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}

// 리포트 문자열에서 1~45 숫자를 공 모양으로 렌더
function renderReportLine(msg: string) {
  // 숫자 토큰을 찾아서, 정수(1~45)만 로또 공으로 치환합니다.
  // 소수(예: 7.2), 퍼센트(예: 39.0%) 등은 공으로 치환하지 않습니다.
  const parts: React.ReactNode[] = []
  // 음수/양수(+1/-2), 소수, 퍼센트 토큰까지 캡처
  const regex = /([+-]?\d+(?:\.\d+)?%?)/g
  let lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = regex.exec(msg)) !== null) {
    const idx = m.index
    const token = m[0]
    if (idx > lastIndex) parts.push(<span key={lastIndex} className="text-xs text-gray-500">{msg.slice(lastIndex, idx)}</span>)

    // 토큰이 순수 정수(소수점·퍼센트 없음)인지 확인
    if (!token.includes('.') && !token.includes('%') && !token.startsWith('-')) {
      const n = Number(token)
      if (Number.isInteger(n) && n >= 1 && n <= 45) {
        const before = idx > 0 ? msg[idx - 1] : ''
        const afterChar = idx + token.length < msg.length ? msg[idx + token.length] : ''

        // 명시적 공 표현 조건: 대괄호/괄호에 감싸이거나 화살표(→)와 연속된 경우
        const isBracketed = before === '[' || before === '(' || afterChar === ')' || (idx + token.length + 1 < msg.length && msg[idx + token.length] === ']' )
        const isArrowAdjacent = before === '→' || afterChar === '→' || msg.slice(Math.max(0, idx - 1), idx + token.length + 1).includes('→')
        const isPrefixedByKoreanEnd = before === '끝'

        const isExplicitBall = (isBracketed || isArrowAdjacent) && !isPrefixedByKoreanEnd

        if (isExplicitBall) {
          parts.push(<LottoBall key={idx} n={n} sm />)
        } else {
          parts.push(<span key={idx} className="text-xs text-gray-500">{token}</span>)
        }
      } else {
        parts.push(<span key={idx} className="text-xs text-gray-500">{token}</span>)
      }
    } else {
      parts.push(<span key={idx} className="text-xs text-gray-500">{token}</span>)
    }

    lastIndex = idx + token.length
  }
  if (lastIndex < msg.length) parts.push(<span key={lastIndex} className="text-xs text-gray-500">{msg.slice(lastIndex)}</span>)

  return <span className="inline-flex items-center gap-1">{parts}</span>
}

// ═══════════════════════════════════════════════════════════════════════════
export default function LotterySimulator() {
  const [tab, setTab] = useState<TabType>('lotto')
  const [lotteryType, setLotteryType] = useState<'lotto' | 'pension'>('lotto')
  const [startRound, setStartRound] = useState('1')
  const [endRound, setEndRound] = useState('')
  const [randomCount, setRandomCount] = useState('100')
  const [topCount, setTopCount] = useState('10')
  const [manualNumbers, setManualNumbers] = useState('')
  const [useOptimalFilter, setUseOptimalFilter] = useState(false)
  const [useHighFreqFilter, setUseHighFreqFilter] = useState(false)
  const [showHighPrizeOnly, setShowHighPrizeOnly] = useState(false)
  const [isSimulating, setIsSimulating] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isPredicting, setIsPredicting] = useState(false)
  const [analysisData, setAnalysisData] = useState<any>(null)
  const [predictions, setPredictions] = useState<PredictionResult | null>(null)
  const [pensionPredictions, setPensionPredictions] = useState<PensionPredictionResult | null>(null)
  const [showSettings, setShowSettings] = useState(true)
  const [showTryList, setShowTryList] = useState(false)
  const [dataRows, setDataRows] = useState<any[]>([])
  const [maxRound, setMaxRound] = useState(0)

  // ── Try 세션 목록 ──────────────────────────────────────────────────
  const [sessions, setSessions] = useState<SimulationSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)

  // 번호 등록
  const [registerType, setRegisterType] = useState<'lotto' | 'pension'>('lotto')
  const [registerStatus, setRegisterStatus] = useState<{ ok?: boolean; msg: string } | null>(null)
  const [isRegistering, setIsRegistering] = useState(false)
  const [registerRound, setRegisterRound] = useState('')
  const [registerNums, setRegisterNums] = useState<string[]>(Array(6).fill(''))
  const [registerBonus, setRegisterBonus] = useState('')
  const [pendingRows, setPendingRows] = useState<any[]>([])

  const currentMax = lotteryType === 'lotto' ? getCurrentLottoRound() : getCurrentPensionRound()

  // ── 활성 세션 & 표시 결과 (필터는 저장 결과에 즉시 적용) ──────────
  const activeSession = useMemo(
    () => sessions.find(s => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId]
  )

  const displayResults = useMemo(() => {
    if (!activeSession || activeSession.status !== 'done') return []
    const t = activeSession.lotteryType
    let res = activeSession.allResults
    if (t === 'lotto' && useOptimalFilter) res = res.filter(s => passOptimalFilter(s.numbers))
    if (t === 'lotto' && useHighFreqFilter) res = res.filter(s => passHighFreqFilter(s.numbers))
    if (t === 'pension' && useOptimalFilter) res = res.filter(s => passPensionOptimalFilter(s.numbers))
    if (t === 'pension' && useHighFreqFilter) res = res.filter(s => passPensionHighFreqFilter(s.numbers))
    if (showHighPrizeOnly) res = res.filter(s => (s.stats.rank1 || 0) + (s.stats.rank2 || 0) + (s.stats.rank3 || 0) > 0)
    const topN = parseInt(topCount) || 10
    return getTopSets(res, topN).map((s, idx) => ({ ...s, originalRank: idx + 1 }))
  }, [activeSession, useOptimalFilter, useHighFreqFilter, showHighPrizeOnly, topCount])

  // 탭/종류 전환 시 데이터 로드
  useEffect(() => {
    if (tab === 'register') return
    setDataRows([])
    setMaxRound(0)
    setEndRound('')
    setAnalysisData(null)
    setPredictions(null)
    let cancelled = false
    async function load() {
      try {
        const r = await fetch(`/api/data/${lotteryType}`)
        if (!r.ok || cancelled) return
        const j = await r.json()
        const rows: any[] = j.rows || []
        if (cancelled) return
        setDataRows(rows)
        const max = rows.reduce((m: number, row: any) => {
          const rn = lotteryType === 'lotto' ? Number(row.drwNo) : Number(row.round)
          return Math.max(m, isNaN(rn) ? 0 : rn)
        }, 0)
        setMaxRound(max)
        if (max > 0) setEndRound(String(max))
      } catch { /* ignore */ }
    }
    load()
    return () => { cancelled = true }
  }, [tab, lotteryType])

  const getFilteredRows = useCallback(async () => {
    const start = parseInt(startRound) || 1
    const end = parseInt(endRound) || maxRound || currentMax
    const rows = dataRows.length > 0 ? dataRows : await fetch(`/api/data/${lotteryType}`).then(r => r.json()).then(j => j.rows || [])
    return rows.filter((row: any) => {
      const rn = lotteryType === 'lotto' ? Number(row.drwNo) : Number(row.round)
      return rn >= start && rn <= end
    })
  }, [lotteryType, startRound, endRound, dataRows, maxRound, currentMax])

  // ── 시뮬레이션 — 전체 결과를 세션으로 저장 ─────────────────────────
  const handleSimulation = useCallback(async () => {
    const startR = parseInt(startRound) || 1
    const endR = parseInt(endRound) || maxRound || currentMax
    const cnt = Math.max(1, parseInt(randomCount) || 100)
    const isManual = !!manualNumbers.trim()
    const isBackground = !isManual && cnt > BG_THRESHOLD

    const sessionId = `s-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const sessionLabel = `${lotteryType === 'lotto' ? '🎱 로또' : '🎫 연금'} ${startR}~${endR}회 | ${isManual ? '수동' : cnt.toLocaleString() + '개'}`

    const newSession: SimulationSession = {
      id: sessionId, label: sessionLabel, lotteryType,
      startRound: startR, endRound: endR,
      totalRequested: isManual ? 0 : cnt, totalSimulated: 0,
      isBackground, status: 'running', progress: 0, createdAt: Date.now(), allResults: [],
    }

    setSessions(prev => [newSession, ...prev])
    setActiveSessionId(sessionId)
    setShowTryList(true)

    const updateSession = (patch: Partial<SimulationSession>) =>
      setSessions(prev => prev.map(s => s.id === sessionId ? { ...s, ...patch } : s))

    if (!isBackground) setIsSimulating(true)

    const runSimulation = async () => {
      try {
        const simStart = Date.now()
        const rows = await getFilteredRows()
        if (rows.length === 0) throw new Error('선택한 회차 범위에 데이터가 없습니다.')

        // ── 번호 세트 생성 ────────────────────────────────────────
        let numberSets: NumberSet[]
        if (isManual) {
          numberSets = manualNumbers.trim().split('\n').filter(l => l.trim()).map((line, i) => {
            const nums = line.split(/[\s,]+/).map(Number).filter(n => !isNaN(n))
            return {
              id: i + 1, numbers: nums,
              stats: lotteryType === 'lotto'
                ? { rank1: 0, rank2: 0, rank3: 0, rank4: 0, rank5: 0 }
                : { rank1: 0, rank2: 0, rank3: 0, rank4: 0, rank5: 0, rank6: 0, rank7: 0 },
            }
          })
          if (lotteryType === 'lotto') {
            const invalid = numberSets.some(s => s.numbers.length !== 6 || s.numbers.some((n: number) => n < 1 || n > 45))
            if (invalid) throw new Error('수동 입력: 로또 번호는 한 줄에 6개, 1~45이어야 합니다.')
          }
        } else {
          // 완전 랜덤 생성 — 필터는 결과 조회 시 적용
          numberSets = []
          const setStrings = new Set<string>()
          while (numberSets.length < cnt) {
            const numbers = lotteryType === 'lotto' ? generateLottoNumbers(6) : generatePensionNumbers(6)
            const sstr = numbers.join(',')
            if (setStrings.has(sstr)) continue
            setStrings.add(sstr)
            let mask: bigint | undefined
            if (lotteryType === 'lotto') { mask = BigInt(0); for (const n of numbers) mask |= (BigInt(1) << BigInt(n - 1)) }
            const stats = lotteryType === 'lotto'
              ? { rank1: 0, rank2: 0, rank3: 0, rank4: 0, rank5: 0 }
              : { rank1: 0, rank2: 0, rank3: 0, rank4: 0, rank5: 0, rank6: 0, rank7: 0 }
            numberSets.push({ id: numberSets.length + 1, numbers, stats, mask })
            if (numberSets.length % 20000 === 0) {
              updateSession({ progress: Math.round((numberSets.length / cnt) * 40) })
              await new Promise(r => setTimeout(r, 0))
            }
          }
        }

        updateSession({ progress: 45, totalSimulated: numberSets.length })

        // ── 시뮬레이션 실행 ───────────────────────────────────────
        let simulated: NumberSet[]
        if (lotteryType === 'lotto' && numberSets.length > 2000 && typeof window !== 'undefined' && window.Worker) {
          const hw = navigator.hardwareConcurrency || 4
          const workerCount = Math.min(hw, 8)
          const chunkSize = Math.ceil(numberSets.length / workerCount)
          const progressArr: number[] = Array(workerCount).fill(0)
          const promises: Promise<NumberSet[]>[] = []
          for (let w = 0; w < workerCount; w++) {
            const chunk = numberSets.slice(w * chunkSize, (w + 1) * chunkSize)
            if (!chunk.length) continue
            promises.push(new Promise(resolve => {
              const worker = new Worker('/simulate-worker.js')
              const serial = chunk.map(s => ({ ...s, mask: (s as any).mask ? String((s as any).mask) : undefined }))
              worker.postMessage({ type: 'lotto', sets: serial, rows })
              worker.onmessage = ev => {
                const d = ev.data
                if (d?.progress != null) {
                  progressArr[w] = Number(d.progress)
                  updateSession({ progress: 45 + Math.round(progressArr.reduce((a, b) => a + b, 0) / workerCount * 0.55) })
                  return
                }
                const result = d?.done ? d.sets : d
                resolve(result); worker.terminate()
              }
              worker.onerror = () => { worker.terminate(); resolve([]) }
            }))
          }
          const parts = await Promise.all(promises)
          simulated = ([] as NumberSet[]).concat(...parts).filter(Boolean)
        } else {
          simulated = lotteryType === 'lotto' ? simulateLotto(numberSets, rows) : simulatePension(numberSets, rows)
        }

        // ── 전체 결과 저장 (정렬·필터 없이 ALL) ──────────────────
        const simElapsed = Date.now() - simStart
        const debugInfo = `requested:${newSession.totalRequested || 0}, generated:${numberSets.length}, simulated:${simulated.length}, time:${simElapsed}ms`
        console.log('[Simulation Debug]', { sessionId, requested: newSession.totalRequested, generated: numberSets.length, simulated: simulated.length, elapsedMs: simElapsed })
        updateSession({ status: 'done', progress: 100, allResults: simulated, totalSimulated: simulated.length, completedAt: Date.now(), debugInfo })
      } catch (e) {
        updateSession({ status: 'error', errorMsg: String(e) })
        alert('오류: ' + String(e))
      } finally {
        if (!isBackground) setIsSimulating(false)
      }
    }

    if (isBackground) {
      runSimulation() // fire-and-forget
    } else {
      await runSimulation()
    }
  }, [lotteryType, randomCount, manualNumbers, startRound, endRound, dataRows, maxRound, currentMax, getFilteredRows])

  // ── 분석 ──────────────────────────────────────────────────────────
  const handleAnalysis = useCallback(async () => {
    setIsAnalyzing(true); setAnalysisData(null); setPredictions(null)
    try {
      const rows = await getFilteredRows()
      if (!rows.length) { alert('분석할 데이터가 없습니다.'); return }
      setAnalysisData(lotteryType === 'lotto' ? { kind: 'lotto', ...analyzeLotto(rows) } : { kind: 'pension', ...analyzePension(rows) })
    } catch (e) { alert('분석 오류: ' + String(e)) }
    finally { setIsAnalyzing(false) }
  }, [lotteryType, getFilteredRows])

  // 화면 초기화: 백그라운드(실행중) 세션만 남기고 나머지 상태 초기화
  const handleResetAll = useCallback(() => {
    setAnalysisData(null)
    setPredictions(null)
    setPensionPredictions(null)
    setActiveSessionId(null)
    setUseOptimalFilter(false)
    setUseHighFreqFilter(false)
    setShowHighPrizeOnly(false)
    setManualNumbers('')
    setRandomCount('100')
    setTopCount('10')
    setStartRound('1')
    setEndRound(maxRound > 0 ? String(maxRound) : '')
    setShowSettings(true)
    // 세션은 'running' 상태(백그라운드 실행)만 유지
    setSessions(prev => prev.filter(s => s.status === 'running'))
  }, [maxRound])

  const handlePredict = useCallback(async () => {
    setIsPredicting(true); setPredictions(null); setPensionPredictions(null); setAnalysisData(null)
    try {
      const rows = await getFilteredRows()
      if (!rows.length) { alert('예측을 위한 데이터가 없습니다.'); return }
      if (lotteryType === 'lotto') {
        const result = runPredictionEngine(rows as LottoData[], 10)
        setPredictions(result)
      } else {
        const result = runPensionPredictionEngine(rows as PensionLotteryData[], 15)
        setPensionPredictions(result)
      }
    } catch (e) { alert('예측 오류: ' + String(e)) }
    finally { setIsPredicting(false) }
  }, [lotteryType, getFilteredRows])

  // ── 번호 등록 ─────────────────────────────────────────────────────
  const handleAddRow = useCallback(() => {
    const round = parseInt(registerRound)
    if (!round || round <= 0) { alert('올바른 회차를 입력하세요.'); return }
    if (registerType === 'lotto') {
      const nums = registerNums.map(n => parseInt(n))
      const bonus = parseInt(registerBonus)
      if (nums.some(n => isNaN(n) || n < 1 || n > 45)) { alert('로또 번호는 1~45 사이여야 합니다.'); return }
      if (isNaN(bonus) || bonus < 1 || bonus > 45) { alert('보너스 번호는 1~45 사이여야 합니다.'); return }
      if (new Set(nums).size !== 6) { alert('번호 6개는 모두 달라야 합니다.'); return }
      setPendingRows(prev => [...prev, { drwNo: round, drwtNo1: nums[0], drwtNo2: nums[1], drwtNo3: nums[2], drwtNo4: nums[3], drwtNo5: nums[4], drwtNo6: nums[5], bnusNo: bonus }])
    } else {
      const nums = registerNums.map(n => parseInt(n))
      if (nums.some(n => isNaN(n) || n < 0 || n > 9)) { alert('연금복권 번호는 0~9 사이여야 합니다.'); return }
      setPendingRows(prev => [...prev, { round, num1: nums[0], num2: nums[1], num3: nums[2], num4: nums[3], num5: nums[4], num6: nums[5] }])
    }
    setRegisterRound(''); setRegisterNums(Array(6).fill('')); setRegisterBonus('')
  }, [registerType, registerRound, registerNums, registerBonus])

  const handleRegister = useCallback(async () => {
    if (!pendingRows.length) { alert('등록할 데이터가 없습니다.'); return }
    setIsRegistering(true); setRegisterStatus(null)
    try {
      const resp = await fetch('/api/data/upload', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: registerType, rows: pendingRows }) })
      const j = await resp.json()
      if (!resp.ok) setRegisterStatus({ ok: false, msg: `실패: ${j.error || '알 수 없는 오류'}` })
      else { setRegisterStatus({ ok: true, msg: `✅ ${j.saved}건 저장 완료 (전체 ${j.total}건)` }); setPendingRows([]) }
    } catch (e) { setRegisterStatus({ ok: false, msg: String(e) }) }
    finally { setIsRegistering(false) }
  }, [registerType, pendingRows])

  // ═══ RENDER ════════════════════════════════════════════════════════
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-5xl mx-auto py-8 px-4 space-y-4">

        {/* 헤더 */}
        <div className="flex items-center gap-3">
          <Ticket className="w-8 h-8 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-800">로또 / 연금복권 시뮬레이터</h1>
        </div>

        {/* 탭 */}
        <div className="flex gap-2 flex-wrap">
          {[
            { id: 'lotto', label: '🎱 로또 6/45' },
            { id: 'pension', label: '🎫 연금복권' },
            { id: 'register', label: '📥 번호 등록' },
          ].map(t => (
            <button key={t.id}
              onClick={() => { setTab(t.id as TabType); if (t.id !== 'register') setLotteryType(t.id as 'lotto' | 'pension') }}
              className={`px-5 py-2 rounded-full font-semibold text-sm transition-colors ${tab === t.id ? 'bg-indigo-600 text-white shadow' : 'bg-white text-gray-600 border hover:bg-indigo-50'}`}
            >{t.label}</button>
          ))}
        </div>

        {/* ══ 번호 등록 탭 ══════════════════════════════════════════════ */}
        {tab === 'register' && (
          <div className="bg-white rounded-xl shadow border border-gray-100 p-5 space-y-5">
            <h2 className="font-bold text-gray-800 flex items-center gap-2"><Upload className="w-4 h-4" /> 당첨 번호 데이터 등록</h2>
            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-1">종류</label>
              <select value={registerType}
                onChange={e => { setRegisterType(e.target.value as 'lotto' | 'pension'); setPendingRows([]); setRegisterNums(Array(6).fill('')); setRegisterRound(''); setRegisterBonus('') }}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm w-48 focus:ring-2 focus:ring-indigo-300 focus:outline-none">
                <option value="lotto">로또 6/45</option>
                <option value="pension">연금복권</option>
              </select>
            </div>
            <div className="bg-gray-50 rounded-xl p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-500 uppercase">새 행 입력</p>
              <div className="flex flex-wrap gap-2 items-end">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-gray-500">회차</label>
                  <input type="number" value={registerRound} onChange={e => setRegisterRound(e.target.value)} placeholder="회차"
                    className="w-20 px-2 py-1.5 border border-gray-300 rounded-lg text-sm text-center focus:ring-2 focus:ring-indigo-300 focus:outline-none" />
                </div>
                {registerNums.map((v, i) => (
                  <div key={i} className="flex flex-col gap-1">
                    <label className="text-xs text-gray-500">{i + 1}번</label>
                    <input type="number" value={v}
                      onChange={e => setRegisterNums(prev => { const a = [...prev]; a[i] = e.target.value; return a })}
                      placeholder={registerType === 'lotto' ? '1~45' : '0~9'}
                      min={registerType === 'lotto' ? 1 : 0} max={registerType === 'lotto' ? 45 : 9}
                      className="w-16 px-2 py-1.5 border border-gray-300 rounded-lg text-sm text-center focus:ring-2 focus:ring-indigo-300 focus:outline-none" />
                  </div>
                ))}
                {registerType === 'lotto' && (
                  <div className="flex flex-col gap-1">
                    <label className="text-xs text-amber-600 font-semibold">보너스</label>
                    <input type="number" value={registerBonus} onChange={e => setRegisterBonus(e.target.value)} placeholder="1~45" min={1} max={45}
                      className="w-16 px-2 py-1.5 border border-amber-300 rounded-lg text-sm text-center focus:ring-2 focus:ring-amber-300 focus:outline-none bg-amber-50" />
                  </div>
                )}
                <button onClick={handleAddRow} className="flex items-center gap-1 px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold self-end">+ 추가</button>
              </div>
            </div>
            {pendingRows.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase mb-2">저장 대기 목록 ({pendingRows.length}건)</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border border-gray-100 rounded-lg overflow-hidden">
                    <thead>
                      <tr className="bg-gray-50 text-xs text-gray-500">
                        <th className="px-3 py-2 text-left">회차</th>
                        {[1,2,3,4,5,6].map(i => <th key={i} className="px-2 py-2 text-center">{i}번</th>)}
                        {registerType === 'lotto' && <th className="px-2 py-2 text-center text-amber-600">보너스</th>}
                        <th className="px-2 py-2"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {pendingRows.map((row, idx) => (
                        <tr key={idx} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-semibold">{registerType === 'lotto' ? row.drwNo : row.round}</td>
                          {registerType === 'lotto'
                            ? [row.drwtNo1,row.drwtNo2,row.drwtNo3,row.drwtNo4,row.drwtNo5,row.drwtNo6].map((n, i) => (
                                <td key={i} className="px-2 py-2 text-center"><span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${ballColor(n)}`}>{n}</span></td>
                              ))
                            : [row.num1,row.num2,row.num3,row.num4,row.num5,row.num6].map((n, i) => (
                                <td key={i} className="px-2 py-2 text-center"><span className="inline-flex items-center justify-center w-7 h-7 rounded bg-purple-600 text-white text-xs font-bold">{n}</span></td>
                              ))
                          }
                          {registerType === 'lotto' && (
                            <td className="px-2 py-2 text-center"><span className="inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold bg-amber-200 text-amber-800">{row.bnusNo}</span></td>
                          )}
                          <td className="px-2 py-2"><button onClick={() => setPendingRows(prev => prev.filter((_, i) => i !== idx))} className="text-red-400 hover:text-red-600 text-xs">✕</button></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            <div className="flex gap-3 items-center">
              <button onClick={handleRegister} disabled={isRegistering || !pendingRows.length}
                className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-200 disabled:text-gray-400 text-white rounded-lg font-semibold text-sm">
                {isRegistering ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {pendingRows.length > 0 ? `${pendingRows.length}건 저장` : '저장'}
              </button>
              {pendingRows.length > 0 && <button onClick={() => setPendingRows([])} className="text-xs text-gray-400 hover:text-gray-600 underline">목록 초기화</button>}
            </div>
            {registerStatus && (
              <div className={`text-sm px-4 py-3 rounded-lg ${registerStatus.ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>{registerStatus.msg}</div>
            )}
          </div>
        )}

        {/* ══ 시뮬레이터 / 분석 탭 ════════════════════════════════════ */}
        {tab !== 'register' && (
          <>
            {/* ── 설정 패널 ──────────────────────────────────────────── */}
            <div className="bg-white rounded-xl shadow border border-gray-100">
              <button className="w-full flex items-center justify-between px-5 py-4" onClick={() => setShowSettings(v => !v)}>
                <span className="font-semibold text-gray-700 flex items-center gap-2">
                  <Filter className="w-4 h-4" /> 설정
                  {maxRound > 0 && <span className="text-xs text-gray-400 font-normal">데이터 {maxRound}회차까지 보유</span>}
                </span>
                {showSettings ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
              </button>

              {showSettings && (
                <div className="px-5 pb-5 space-y-4 border-t border-gray-100">
                  {/* 회차 범위 */}
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase mb-2">회차 범위</label>
                    <div className="flex gap-3 items-center flex-wrap">
                      <input type="number" placeholder="시작 회차" value={startRound} onChange={e => setStartRound(e.target.value)}
                        className="w-32 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300 focus:outline-none" />
                      <span className="text-gray-400">~</span>
                      <input type="number" placeholder="종료 회차" value={endRound} onChange={e => setEndRound(e.target.value)}
                        className="w-32 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300 focus:outline-none" />
                      {maxRound > 0 && (
                        <button onClick={() => { setStartRound('1'); setEndRound(String(maxRound)) }} className="text-xs text-indigo-500 hover:text-indigo-700 underline">전체 선택</button>
                      )}
                    </div>
                  </div>

                  {/* 수 설정 */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-gray-500 uppercase mb-1">
                        랜덤 생성 개수
                        {parseInt(randomCount) > BG_THRESHOLD && (
                          <span className="ml-1 text-blue-500 font-normal normal-case">→ 백그라운드</span>
                        )}
                      </label>
                      <input type="number" value={randomCount} onChange={e => setRandomCount(e.target.value)} min={1}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300 focus:outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-gray-500 uppercase mb-1">상위 결과 수</label>
                      <input type="number" value={topCount} onChange={e => setTopCount(e.target.value)} min={1} max={500}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-300 focus:outline-none" />
                    </div>
                  </div>

                  {/* 수동 입력 */}
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase mb-1">
                      수동 번호 입력 <span className="text-gray-300 font-normal normal-case">(한 줄에 6개, 비우면 랜덤)</span>
                    </label>
                    <textarea value={manualNumbers} onChange={e => setManualNumbers(e.target.value)}
                      placeholder={lotteryType === 'lotto' ? '예) 1 7 14 23 38 42' : '예) 3 7 2 8 4 1'}
                      rows={3}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-300 focus:outline-none" />
                  </div>

                  {/* 결과 필터 (재시뮬레이션 없이 저장된 결과에서 즉시 적용) */}
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
                      결과 필터 <span className="font-normal text-gray-400 normal-case">(저장된 결과에서 즉시 적용 · 재시뮬레이션 없음)</span>
                    </p>
                    <div className="flex flex-col gap-2">
                      {lotteryType === 'lotto' && (
                        <>
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input type="checkbox" checked={useOptimalFilter} onChange={e => { const v = e.target.checked; setUseOptimalFilter(v); if (v) setUseHighFreqFilter(false) }} className="w-4 h-4 accent-indigo-600 shrink-0" />
                            <span className="text-sm text-gray-700 font-medium">최적 필터</span>
                            <span className="text-xs text-gray-400">(연번≤1, 저:고 2~4, 홀:짝 2~4, 합 100~180)</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input type="checkbox" checked={useHighFreqFilter} onChange={e => { const v = e.target.checked; setUseHighFreqFilter(v); if (v) setUseOptimalFilter(false) }} className="w-4 h-4 accent-indigo-600 shrink-0" />
                            <span className="text-sm text-gray-700 font-medium">고빈도 필터</span>
                            <span className="text-xs text-gray-400">(연번0, 저:고 3:3, 홀:짝 3:3, 합 120~139)</span>
                          </label>
                        </>
                      )}
                      {lotteryType === 'pension' && (
                        <>
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input type="checkbox" checked={useOptimalFilter} onChange={e => { const v = e.target.checked; setUseOptimalFilter(v); if (v) setUseHighFreqFilter(false) }} className="w-4 h-4 accent-purple-600 shrink-0" />
                            <span className="text-sm text-gray-700 font-medium">최적 필터</span>
                            <span className="text-xs text-gray-400">(연번≤2, 저:고 2~4, 홀:짝 2~4, 합 20~39)</span>
                          </label>
                          <label className="flex items-center gap-2 cursor-pointer select-none">
                            <input type="checkbox" checked={useHighFreqFilter} onChange={e => { const v = e.target.checked; setUseHighFreqFilter(v); if (v) setUseOptimalFilter(false) }} className="w-4 h-4 accent-purple-600 shrink-0" />
                            <span className="text-sm text-gray-700 font-medium">고빈도 필터</span>
                            <span className="text-xs text-gray-400">(연번1, 저:고 3:3, 홀:짝 3:3, 합 20~29)</span>
                          </label>
                        </>
                      )}
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input type="checkbox" checked={showHighPrizeOnly} onChange={e => setShowHighPrizeOnly(e.target.checked)} className="w-4 h-4 accent-indigo-600 shrink-0" />
                        <span className="text-sm text-gray-700 font-medium">고액당첨만 보기</span>
                        <span className="text-xs text-gray-400">(1~3등 이력)</span>
                      </label>
                    </div>
                    {activeSession?.status === 'done' && (useOptimalFilter || useHighFreqFilter || showHighPrizeOnly) && (
                      <p className="text-xs text-indigo-600 mt-1.5">
                        {activeSession.totalSimulated.toLocaleString()}개 중 필터 조건 → <strong>{displayResults.length}개</strong> 표시
                      </p>
                    )}
                  </div>

                  {/* 버튼 */}
                  <div className="flex gap-3 flex-wrap pt-1">
                    <button onClick={handleSimulation} disabled={isSimulating}
                      className="flex items-center gap-2 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white rounded-lg font-semibold text-sm">
                      {isSimulating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                      {parseInt(randomCount) > BG_THRESHOLD ? '시뮬레이션 (백그라운드 실행)' : '시뮬레이션'}
                    </button>
                    <button onClick={handleAnalysis} disabled={isAnalyzing}
                      className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-300 text-white rounded-lg font-semibold text-sm">
                      {isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
                      분석
                    </button>
                    <button onClick={handlePredict} disabled={isPredicting}
                      className="flex items-center gap-2 px-6 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-300 text-white rounded-lg font-semibold text-sm">
                      {isPredicting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                      다음 차수 예측
                    </button>
                    <button onClick={handleResetAll}
                      className="flex items-center gap-2 px-4 py-2.5 bg-white hover:bg-gray-50 border border-gray-200 text-gray-700 rounded-lg text-sm">
                      <RefreshCw className="w-4 h-4" /> 초기화
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* ══ Try 리스트 ════════════════════════════════════════════ */}
            {sessions.length > 0 && (
              <div className="bg-white rounded-xl shadow border border-gray-100">
                <button className="w-full flex items-center justify-between px-5 py-4" onClick={() => setShowTryList(v => !v)}>
                  <span className="font-semibold text-gray-700 flex items-center gap-2">
                    <List className="w-4 h-4" /> Try 리스트
                    <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full">{sessions.length}개</span>
                    {sessions.some(s => s.status === 'running') && (
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full animate-pulse">
                        {sessions.filter(s => s.status === 'running').length}개 실행 중
                      </span>
                    )}
                  </span>
                  {showTryList ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
                </button>

                {showTryList && (
                  <div className="border-t border-gray-100 divide-y divide-gray-50">
                    {sessions.map(session => (
                      <div key={session.id}
                        className={`flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors ${activeSessionId === session.id ? 'bg-indigo-50 border-l-4 border-l-indigo-500' : ''}`}
                      >
                        <div className="w-6 h-6 shrink-0 flex items-center justify-center">
                          {session.status === 'running' && <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />}
                          {session.status === 'done' && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                          {session.status === 'error' && <XCircle className="w-4 h-4 text-red-500" />}
                        </div>

                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-800 truncate">{session.label}</p>
                          <div className="flex items-center gap-3 mt-0.5 flex-wrap">
                            {session.status === 'running' && (
                              <div className="flex items-center gap-1.5">
                                <div className="w-28 h-1.5 bg-gray-200 rounded overflow-hidden">
                                  <div className="h-1.5 bg-blue-500 rounded transition-all duration-300" style={{ width: `${session.progress}%` }} />
                                </div>
                                <span className="text-xs text-blue-600">{session.progress}%</span>
                              </div>
                            )}
                            {session.status === 'done' && (
                              <div className="text-xs text-gray-400">
                                <div>{session.totalSimulated.toLocaleString()}개 완료{session.completedAt && (<> · <Clock className="inline w-3 h-3 mx-0.5" />{formatElapsed(session.completedAt - session.createdAt)}</>)}</div>
                                {session.debugInfo && <div className="text-xs text-gray-400/70 mt-0.5">{session.debugInfo}</div>}
                              </div>
                            )}
                            {session.status === 'error' && <span className="text-xs text-red-500 truncate">{session.errorMsg}</span>}
                            <span className="text-xs text-gray-300">{new Date(session.createdAt).toLocaleTimeString()}</span>
                          </div>
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                          {session.status === 'done' && (
                            <button
                              onClick={() => { setActiveSessionId(session.id); setUseOptimalFilter(false); setUseHighFreqFilter(false); setShowHighPrizeOnly(false) }}
                              className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold ${activeSessionId === session.id ? 'bg-indigo-600 text-white' : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100'}`}
                            >
                              <Eye className="w-3 h-3" /> 보기
                            </button>
                          )}
                          <button
                            onClick={() => { setSessions(prev => prev.filter(s => s.id !== session.id)); if (activeSessionId === session.id) setActiveSessionId(null) }}
                            className="p-1.5 text-gray-300 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors" title="삭제"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* ── 예측 결과 ─────────────────────────────────────────────── */}
            {predictions !== null && predictions.sets.length > 0 && (
              <div className="space-y-4">
                {/* 헤더 */}
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
                  <h2 className="font-bold text-amber-800 flex items-center gap-2 mb-1">
                    <Sparkles className="w-4 h-4" /> 다음 차수 예측 (5모듈 엔진)
                    <span className="text-xs font-normal text-amber-600">· 데이터 기반 확률 선택 · 참고용</span>
                  </h2>

                  {/* ── 예측 세트 목록 ─────────────────────────── */}
                  <div className="mt-4 space-y-4">
                    {predictions.sets.map((set, i) => (
                      <div key={i} className="bg-white rounded-xl border border-amber-100 p-4 space-y-3">
                        {/* 번호 + 구조 배지 */}
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="w-7 h-7 rounded-full bg-amber-400 text-white text-sm font-bold flex items-center justify-center shrink-0">{i + 1}</span>
                          <div className="flex gap-1.5 flex-wrap">
                            {set.numbers.map((n, j) =>
                              lotteryType === 'lotto' ? <LottoBall key={j} n={n} sm /> : <PensionDigit key={j} n={n} pos={j + 1} />
                            )}
                          </div>
                          {lotteryType === 'lotto' && (
                            <div className="flex gap-1 flex-wrap">
                              {getBadgeItems(set.numbers).map(b => (
                                <span key={b.label} className={`text-xs px-1.5 py-0.5 rounded font-medium ${b.ok ? 'bg-green-100 text-green-700 ring-1 ring-green-300' : 'bg-amber-100 text-amber-600'}`}>{b.label}</span>
                              ))}
                              <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 font-medium">합 {set.structureInfo.sum}</span>
                              <span className="text-xs px-1.5 py-0.5 rounded bg-gray-50 text-gray-500 font-medium">저{set.structureInfo.low}:고{set.structureInfo.high}</span>
                              <span className="text-xs px-1.5 py-0.5 rounded bg-gray-50 text-gray-500 font-medium">홀{set.structureInfo.odd}:짝{set.structureInfo.even}</span>
                              <span className="text-xs px-1.5 py-0.5 rounded bg-gray-50 text-gray-500 font-medium">연번 {set.structureInfo.consecutivePairs}쌍</span>
                            </div>
                          )}
                        </div>
                        {/* 번호별 선택 근거 */}
                        {set.reasons.length > 0 && (
                          <div className="space-y-1 pl-10">
                            {set.reasons.map((r, ri) => (
                              <p key={ri} className="text-xs text-gray-500 leading-relaxed">
                                <span className="text-amber-600 font-semibold">›</span> {renderReportLine(r)}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* ── 모듈별 분석 리포트 ────────────────────── */}
                {lotteryType === 'lotto' && (
                  <div className="bg-white rounded-xl border border-gray-100 shadow">
                    <div className="px-5 py-4 border-b border-gray-100">
                      <h3 className="font-bold text-gray-700 text-sm">5모듈 분석 리포트</h3>
                    </div>
                    <div className="divide-y divide-gray-50">
                      {([
                        { key: 'staircase', label: '모듈1 계단/사선 흐름', color: 'text-blue-600 bg-blue-50' },
                        { key: 'carryover', label: '모듈2 이월·이웃수',    color: 'text-green-600 bg-green-50' },
                        { key: 'cold',      label: '모듈3 장기 미출현 회귀', color: 'text-purple-600 bg-purple-50' },
                        { key: 'section',   label: '모듈4 구간 멸실/채움',  color: 'text-orange-600 bg-orange-50' },
                        { key: 'endDigit',  label: '모듈5 끝수·연번',       color: 'text-pink-600 bg-pink-50' },
                      ] as { key: keyof typeof predictions.moduleReports; label: string; color: string }[]).map(({ key, label, color }) => (
                        <div key={key} className="px-5 py-3">
                          <p className={`text-xs font-bold mb-2 inline-block px-2 py-0.5 rounded ${color}`}>{label}</p>
                          <ul className="space-y-1">
                            {predictions.moduleReports[key].slice(0, 6).map((msg, mi) => (
                              <li key={mi} className="text-xs text-gray-500">• {renderReportLine(msg)}</li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* ── 출현 기대치 스코어보드 (TOP 20) ─────── */}
                {lotteryType === 'lotto' && predictions.scoreboard.length > 0 && (
                  <div className="bg-white rounded-xl border border-gray-100 shadow">
                    <div className="px-5 py-4 border-b border-gray-100">
                      <h3 className="font-bold text-gray-700 text-sm">출현 기대치 스코어보드 <span className="text-xs font-normal text-gray-400">(상위 20번호)</span></h3>
                    </div>
                    <div className="px-5 py-4 overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-gray-400 uppercase">
                            <th className="pb-2 text-left">번호</th>
                            <th className="pb-2 text-center">총점</th>
                            <th className="pb-2 text-center">계단</th>
                            <th className="pb-2 text-center">이월</th>
                            <th className="pb-2 text-center">미출현</th>
                            <th className="pb-2 text-center">구간</th>
                            <th className="pb-2 text-center">끝수</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                          {predictions.scoreboard.slice(0, 20).map((s, i) => (
                            <tr key={s.num} className={i < 6 ? 'bg-amber-50/50' : ''}>
                              <td className="py-1.5"><LottoBall n={s.num} sm /></td>
                              <td className="py-1.5 text-center font-bold text-indigo-600">{s.total}</td>
                              <td className="py-1.5 text-center text-blue-600">{s.scores.staircase || '-'}</td>
                              <td className="py-1.5 text-center text-green-600">{s.scores.carryover || '-'}</td>
                              <td className="py-1.5 text-center text-purple-600">{s.scores.cold || '-'}</td>
                              <td className="py-1.5 text-center text-orange-600">{s.scores.section !== 0 ? s.scores.section : '-'}</td>
                              <td className="py-1.5 text-center text-pink-600">{s.scores.endDigit || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── 연금복권 예측 결과 ──────────────────────────────────────── */}
            {pensionPredictions !== null && pensionPredictions.sets.length > 0 && (
              <div className="space-y-4">
                {/* 예측 세트 */}
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
                  <h2 className="font-bold text-amber-800 flex items-center gap-2 mb-1">
                    <Sparkles className="w-4 h-4" /> 연금복권 다음 차수 예측 (5모듈 엔진)
                    <span className="text-xs font-normal text-amber-600">· 자리별 데이터 기반 · 참고용</span>
                  </h2>
                  <div className="mt-4 space-y-4">
                    {pensionPredictions.sets.map((set, i) => (
                      <div key={i} className="bg-white rounded-xl border border-amber-100 p-4 space-y-3">
                        <div className="flex items-center gap-3 flex-wrap">
                          <span className="w-7 h-7 rounded-full bg-amber-400 text-white text-sm font-bold flex items-center justify-center shrink-0">{i + 1}</span>
                          <div className="flex gap-1.5 flex-wrap">
                            {set.numbers.map((n, j) => <PensionDigit key={j} n={n} pos={j + 1} />)}
                          </div>
                          {/* 구조 배지 */}
                          {(() => {
                            const sum = set.numbers.reduce((s, v) => s + v, 0)
                            const low = set.numbers.filter(v => v <= 4).length
                            const odd = set.numbers.filter(v => v % 2 === 1).length
                            let consec = 0
                            for (let k = 0; k < set.numbers.length - 1; k++) if (Math.abs(set.numbers[k + 1] - set.numbers[k]) === 1) consec++
                            return (
                              <div className="flex gap-1 flex-wrap">
                                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${consec <= 2 ? 'bg-green-100 text-green-700 ring-1 ring-green-300' : 'bg-amber-100 text-amber-600'}`}>연번 {consec}</span>
                                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${low >= 2 && low <= 4 ? 'bg-green-100 text-green-700 ring-1 ring-green-300' : 'bg-amber-100 text-amber-600'}`}>저{low}:고{6 - low}</span>
                                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${odd >= 2 && odd <= 4 ? 'bg-green-100 text-green-700 ring-1 ring-green-300' : 'bg-amber-100 text-amber-600'}`}>홀{odd}:짝{6 - odd}</span>
                                <span className={`text-xs px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 font-medium`}>합 {sum}</span>
                              </div>
                            )
                          })()}
                        </div>
                        {set.reasons.length > 0 && (
                          <div className="space-y-1 pl-10">
                            {set.reasons.map((r, ri) => (
                              <p key={ri} className="text-xs text-gray-500 leading-relaxed">
                                <span className="text-amber-600 font-semibold">›</span> {r}
                              </p>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* 5모듈 분석 리포트 */}
                <div className="bg-white rounded-xl border border-gray-100 shadow">
                  <div className="px-5 py-4 border-b border-gray-100">
                    <h3 className="font-bold text-gray-700 text-sm">5모듈 분석 리포트</h3>
                  </div>
                  <div className="divide-y divide-gray-50">
                    {([
                      { key: 'trend',     label: '모듈1 자리별 흐름(계단/추세)', color: 'text-blue-600 bg-blue-50' },
                      { key: 'carryover', label: '모듈2 이월·이웃수',           color: 'text-green-600 bg-green-50' },
                      { key: 'cold',      label: '모듈3 장기 미출현 회귀',       color: 'text-purple-600 bg-purple-50' },
                      { key: 'section',   label: '모듈4 저고 구간 편중 분석',    color: 'text-orange-600 bg-orange-50' },
                      { key: 'pattern',   label: '모듈5 전체 패턴·연번·끝수',    color: 'text-pink-600 bg-pink-50' },
                    ] as { key: keyof typeof pensionPredictions.moduleReports; label: string; color: string }[]).map(({ key, label, color }) => (
                      <div key={key} className="px-5 py-3">
                        <p className={`text-xs font-bold mb-2 inline-block px-2 py-0.5 rounded ${color}`}>{label}</p>
                        <ul className="space-y-1">
                          {pensionPredictions.moduleReports[key].slice(0, 8).map((msg, mi) => (
                            <li key={mi} className="text-xs text-gray-500">• {msg}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 자리별 스코어보드 TOP 20 */}
                {pensionPredictions.scoreboard.length > 0 && (
                  <div className="bg-white rounded-xl border border-gray-100 shadow">
                    <div className="px-5 py-4 border-b border-gray-100">
                      <h3 className="font-bold text-gray-700 text-sm">자리별 출현 기대치 스코어보드 <span className="text-xs font-normal text-gray-400">(상위 20)</span></h3>
                    </div>
                    <div className="px-5 py-4 overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-gray-400 uppercase">
                            <th className="pb-2 text-left">자리</th>
                            <th className="pb-2 text-left">숫자</th>
                            <th className="pb-2 text-center">총점</th>
                            <th className="pb-2 text-center">흐름</th>
                            <th className="pb-2 text-center">이월</th>
                            <th className="pb-2 text-center">미출현</th>
                            <th className="pb-2 text-center">구간</th>
                            <th className="pb-2 text-center">패턴</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                          {pensionPredictions.scoreboard.map((s: PensionDigitScore, i: number) => (
                            <tr key={`${s.pos}-${s.digit}`} className={i < 6 ? 'bg-amber-50/50' : ''}>
                              <td className="py-1.5 text-purple-600 font-semibold">{s.pos}번째</td>
                              <td className="py-1.5"><PensionDigit n={s.digit} pos={s.pos} /></td>
                              <td className="py-1.5 text-center font-bold text-indigo-600">{s.total}</td>
                              <td className="py-1.5 text-center text-blue-600">{s.scores.trend || '-'}</td>
                              <td className="py-1.5 text-center text-green-600">{s.scores.carryover || '-'}</td>
                              <td className="py-1.5 text-center text-purple-600">{s.scores.cold || '-'}</td>
                              <td className="py-1.5 text-center text-orange-600">{s.scores.section !== 0 ? s.scores.section : '-'}</td>
                              <td className="py-1.5 text-center text-pink-600">{s.scores.pattern || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* ── 시뮬레이션 결과 ───────────────────────────────────────── */}
            {activeSession?.status === 'done' && (
              <div className="bg-white rounded-xl shadow border border-gray-100">
                <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <h2 className="font-bold text-gray-800">시뮬레이션 결과</h2>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {activeSession.label} · 전체 {activeSession.totalSimulated.toLocaleString()}개 →&nbsp;
                      {(useOptimalFilter || useHighFreqFilter || showHighPrizeOnly)
                        ? `필터 후 상위 ${displayResults.length}개`
                        : `상위 ${displayResults.length}개`} 표시
                    </p>
                  </div>
                  <span className="text-xs text-gray-400">{activeSession.startRound} ~ {activeSession.endRound}회 기준</span>
                </div>

                {displayResults.length === 0
                  ? <p className="px-5 py-6 text-gray-400 text-sm">조건에 맞는 결과가 없습니다. 필터를 해제하거나 상위 결과 수를 늘려보세요.</p>
                  : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-gray-50 text-gray-500 text-xs uppercase">
                            <th className="px-4 py-3 text-left">순위</th>
                            <th className="px-4 py-3 text-left">번호</th>
                            <th className="px-4 py-3 text-left">특성</th>
                            <th className="px-4 py-3 text-center">총당첨</th>
                            <th className="px-4 py-3 text-center">1등</th>
                            <th className="px-4 py-3 text-center">2등</th>
                            <th className="px-4 py-3 text-center">3등</th>
                            <th className="px-4 py-3 text-center">4등</th>
                            <th className="px-4 py-3 text-center">5등</th>
                            {activeSession.lotteryType === 'pension' && <>
                              <th className="px-4 py-3 text-center">6등</th>
                              <th className="px-4 py-3 text-center">7등</th>
                            </>}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                          {displayResults.map(set => (
                            <tr key={set.id} className="hover:bg-gray-50/60">
                              <td className="px-4 py-3">
                                <span className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs flex items-center justify-center">{set.originalRank}</span>
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex gap-1">
                                  {set.numbers.map((n, i) =>
                                    activeSession.lotteryType === 'lotto' ? <LottoBall key={i} n={n} sm /> : <PensionDigit key={i} n={n} pos={i + 1} />
                                  )}
                                </div>
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex flex-wrap gap-1">
                                  {(activeSession.lotteryType === 'lotto' ? getBadgeItems(set.numbers) : getPensionBadgeItems(set.numbers)).map(b => (
                                    <span key={b.label} className={`text-xs px-1.5 py-0.5 rounded font-medium ${b.ok ? 'bg-green-100 text-green-700 ring-1 ring-green-300' : 'bg-gray-100 text-gray-400'}`}>{b.label}</span>
                                  ))}
                                </div>
                              </td>
                              <td className="px-4 py-3 text-center font-semibold">{computeTotalWins(set.stats, activeSession.lotteryType)}</td>
                              {[1, 2, 3, 4, 5].map(rank => (
                                <td key={rank} className="px-4 py-3 text-center">
                                  <span className={
                                    Number((set.stats as any)[`rank${rank}`]) > 0
                                      ? rank === 1 ? 'font-bold text-red-600' : rank === 2 ? 'font-bold text-orange-500' : rank === 3 ? 'font-semibold text-yellow-600' : 'text-gray-600'
                                      : 'text-gray-300'
                                  }>
                                    {(set.stats as any)[`rank${rank}`] ?? 0}
                                  </span>
                                </td>
                              ))}
                              {activeSession.lotteryType === 'pension' && [6, 7].map(rank => (
                                <td key={rank} className="px-4 py-3 text-center text-gray-400">{(set.stats as any)[`rank${rank}`] ?? 0}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                }
              </div>
            )}

            {/* ══ 분석 결과: 로또 ══════════════════════════════════════ */}
            {analysisData?.kind === 'lotto' && (
              <div className="bg-white rounded-xl shadow border border-gray-100">
                <div className="px-5 py-4 border-b border-gray-100">
                  <h2 className="font-bold text-gray-800">1등 번호 분석 <span className="ml-2 text-xs font-normal text-gray-400">보너스 제외 · {analysisData.total}회차 ({startRound||1}~{endRound||maxRound}회)</span></h2>
                </div>
                <div className="px-5 py-4 border-b border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-3">출현 빈도 TOP 15</p>
                  <div className="flex flex-wrap gap-2">
                    {analysisData.frequent.map((f: { num: number; count: number }, i: number) => (
                      <div key={f.num} className="flex flex-col items-center gap-0.5">
                        <LottoBall n={f.num} />
                        <span className="text-xs text-gray-500">{f.count}회</span>
                        {i < 3 && <span className="text-xs text-amber-500 font-bold">TOP{i+1}</span>}
                      </div>
                    ))}
                  </div>
                </div>
                <div className="px-5 py-4 border-b border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-3">연번 쌍 분포</p>
                  <div className="flex gap-4 items-end flex-wrap">
                    {analysisData.consecEntries.map(({ k, v }: { k: number; v: number }) => {
                      const pct = Math.round((v / analysisData.total) * 100)
                      const hl = k <= 1
                      return (
                        <div key={k} className="flex flex-col items-center gap-1">
                          <span className="text-xs text-gray-500">{pct}%</span>
                          <div className={`w-12 rounded-t ${hl ? 'bg-violet-500' : 'bg-gray-200'}`} style={{ height: `${Math.max(6, pct * 1.6)}px` }} />
                          <span className={`text-xs font-semibold ${hl ? 'text-violet-600' : 'text-gray-400'}`}>{k}쌍</span>
                          <span className="text-xs text-gray-400">{v}회</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
                <div className="px-5 py-4 border-b border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-3">저번(1~22) : 고번(23~45) 분포</p>
                  <div className="flex gap-3 items-end flex-wrap">
                    {analysisData.lowEntries.map(([label, cnt]: [string, number]) => {
                      const pct = Math.round((cnt / analysisData.total) * 100)
                      const hl = Number(label.split(':')[0]) >= 2 && Number(label.split(':')[0]) <= 4
                      return (
                        <div key={label} className="flex flex-col items-center gap-1">
                          <span className="text-xs text-gray-500">{pct}%</span>
                          <div className={`w-12 rounded-t ${hl ? 'bg-indigo-500' : 'bg-gray-200'}`} style={{ height: `${Math.max(6, pct * 1.6)}px` }} />
                          <span className={`text-xs font-semibold ${hl ? 'text-indigo-600' : 'text-gray-400'}`}>{label}</span>
                          <span className="text-xs text-gray-400">{cnt}회</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
                <div className="px-5 py-4 border-b border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-3">홀수 : 짝수 분포</p>
                  <div className="flex gap-3 items-end flex-wrap">
                    {analysisData.oddEntries.map(([label, cnt]: [string, number]) => {
                      const pct = Math.round((cnt / analysisData.total) * 100)
                      const hl = Number(label.split(':')[0]) >= 2 && Number(label.split(':')[0]) <= 4
                      return (
                        <div key={label} className="flex flex-col items-center gap-1">
                          <span className="text-xs text-gray-500">{pct}%</span>
                          <div className={`w-12 rounded-t ${hl ? 'bg-emerald-500' : 'bg-gray-200'}`} style={{ height: `${Math.max(6, pct * 1.6)}px` }} />
                          <span className={`text-xs font-semibold ${hl ? 'text-emerald-600' : 'text-gray-400'}`}>{label}</span>
                          <span className="text-xs text-gray-400">{cnt}회</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
                <div className="px-5 py-4">
                  <p className="text-xs font-semibold text-gray-500 uppercase mb-3">번호 총합 구간 <span className="ml-1 text-gray-400 font-normal">(평균 {analysisData.sumAvg})</span></p>
                  <div className="flex flex-wrap gap-2">
                    {analysisData.sortedBins.map((bin: { label: string; count: number }) => {
                      const pct = Math.round((bin.count / analysisData.total) * 100)
                      const isMax = bin.count === analysisData.maxBinCount
                      return (
                        <div key={bin.label} className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-lg border text-center min-w-[68px] ${isMax ? 'border-amber-400 bg-amber-50' : 'border-gray-100 bg-gray-50'}`}>
                          <span className={`text-xs font-bold ${isMax ? 'text-amber-600' : 'text-gray-600'}`}>{bin.label}</span>
                          <span className="text-xs text-gray-500">{bin.count}회</span>
                          <span className={`text-xs ${isMax ? 'text-amber-500 font-bold' : 'text-gray-400'}`}>{pct}%</span>
                          {isMax && <span className="text-xs text-amber-500 font-bold">▲최다</span>}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* ══ 분석 결과: 연금 ══════════════════════════════════════ */}
            {analysisData?.kind === 'pension' && (
              <div className="bg-white rounded-xl shadow border border-gray-100">
                <div className="px-5 py-4 border-b border-gray-100">
                  <h2 className="font-bold text-gray-800">연금복권 번호 분석 <span className="ml-2 text-xs font-normal text-gray-400">{analysisData.total}회차</span></h2>
                </div>
                <div className="px-5 py-4 space-y-4">
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">자리별 숫자 빈도 (TOP 5)</p>
                    <div className="overflow-x-auto">
                      <table className="text-sm w-full">
                        <thead>
                          <tr className="bg-gray-50 text-xs text-gray-500">
                            <th className="px-3 py-2 text-left">자리</th>
                            {[1,2,3,4,5].map(i => <th key={i} className="px-3 py-2 text-center">#{i}</th>)}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50">
                          {analysisData.posFreq.map((pf: { pos: number; digits: { digit: number; count: number }[] }) => (
                            <tr key={pf.pos} className="hover:bg-gray-50/60">
                              <td className="px-3 py-2 font-semibold text-purple-600">{pf.pos}번째</td>
                              {pf.digits.slice(0, 5).map((d, i) => (
                                <td key={i} className="px-3 py-2 text-center">
                                  <span className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold ${i === 0 ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-700'}`}>{d.digit}</span>
                                  <span className="block text-xs text-gray-400 mt-0.5">{d.count}회</span>
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">전체 빈도 TOP 10</p>
                    <div className="flex flex-wrap gap-2">
                      {analysisData.frequent.map((f: { num: number; count: number }, i: number) => (
                        <div key={f.num} className="flex flex-col items-center gap-0.5">
                          <LottoBall n={f.num} />
                          <span className="text-xs text-gray-500">{f.count}회</span>
                          {i < 3 && <span className="text-xs text-amber-500 font-bold">TOP{i+1}</span>}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">상위 연속 쌍 (TOP 20)</p>
                    <div className="flex gap-2 flex-wrap">
                      {analysisData.pairTop && analysisData.pairTop.length > 0 ? (
                        analysisData.pairTop.map((p: { pair: string; count: number }, i: number) => {
                          const [a, b] = p.pair.split('-').map((x: string) => Number(x))
                          return (
                            <div key={p.pair} className="flex items-center gap-3 px-3 py-2 bg-gray-50 rounded-lg border border-gray-100">
                              <div className="flex gap-1 items-center">
                                <PensionDigit n={a} />
                                <PensionDigit n={b} />
                              </div>
                              <div className="flex flex-col">
                                <span className="text-sm font-semibold text-gray-700">{i + 1}위</span>
                                <span className="text-xs text-gray-500">{p.count}회</span>
                              </div>
                            </div>
                          )
                        })
                      ) : (
                        <div className="text-xs text-gray-400">연속 쌍 데이터가 없습니다.</div>
                      )}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">동일번호 연속 출현</p>
                    <div className="flex gap-2 flex-wrap">
                      {analysisData.samePairTop && analysisData.samePairTop.length > 0 ? (
                        analysisData.samePairTop.map((s: { digit: number; count: number }, i: number) => (
                          <div key={s.digit} className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg border border-gray-100">
                            <PensionDigit n={s.digit} />
                            <span className="text-xs font-bold text-gray-400">+</span>
                            <PensionDigit n={s.digit} />
                            <div className="flex flex-col">
                              <span className="text-sm font-semibold text-gray-700">{i + 1}위</span>
                              <span className="text-xs text-gray-500">{s.count}회</span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-gray-400">동일번호 연속 출현 없음</div>
                      )}
                    </div>
                    <div className="mt-2 text-xs text-gray-500">
                      동일번호 연속 없는 회차: <span className="font-semibold text-gray-700">{analysisData.drawsWithNoConsecSame}회</span>
                      <span className="ml-2 text-gray-400">({analysisData.total > 0 ? Math.round(analysisData.drawsWithNoConsecSame / analysisData.total * 100) : 0}%)</span>
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">홀수 : 짝수 분포</p>
                    <div className="flex gap-4 items-end flex-wrap">
                      {(() => {
                        const entries: [string, number][] = analysisData.oddEntries
                        const maxV = entries.length ? Math.max(...entries.map(e => e[1])) : 0
                        return entries.map(([label, cnt]) => {
                          const pct = Math.round((cnt / analysisData.total) * 100)
                          const hl = cnt === maxV && maxV > 0
                          return (
                            <div key={label} className="flex flex-col items-center gap-1">
                              <span className="text-xs text-gray-500">{pct}%</span>
                              <div className={`w-12 rounded-t ${hl ? 'bg-emerald-500' : 'bg-gray-200'}`} style={{ height: `${Math.max(6, pct * 1.6)}px` }} />
                              <span className={`text-xs font-semibold ${hl ? 'text-emerald-600' : 'text-gray-400'}`}>{label}</span>
                              <span className="text-xs text-gray-400">{cnt}회</span>
                            </div>
                          )
                        })
                      })()}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">연번 쌍 분포</p>
                    <div className="flex gap-4 items-end flex-wrap">
                      {(() => {
                        const entries: { k: number; v: number }[] = analysisData.consecEntries
                        const maxV = entries.length ? Math.max(...entries.map(e => e.v)) : 0
                        return entries.map(({ k, v }: { k: number; v: number }) => {
                          const pct = Math.round((v / analysisData.total) * 100)
                          const hl = v === maxV && maxV > 0
                          return (
                            <div key={k} className="flex flex-col items-center gap-1">
                              <span className="text-xs text-gray-500">{pct}%</span>
                              <div className={`w-12 rounded-t ${hl ? 'bg-violet-500' : 'bg-gray-200'}`} style={{ height: `${Math.max(6, pct * 1.6)}px` }} />
                              <span className={`text-xs font-semibold ${hl ? 'text-violet-600' : 'text-gray-400'}`}>{k}쌍</span>
                              <span className="text-xs text-gray-400">{v}회</span>
                            </div>
                          )
                        })
                      })()}
                    </div>
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">저번(0~4) : 고번(5~9) 분포</p>
                    <div className="flex gap-4 items-end flex-wrap">
                      {(() => {
                        const entries: [string, number][] = analysisData.lowEntries
                        const maxV = entries.length ? Math.max(...entries.map(e => e[1])) : 0
                        return entries.map(([label, cnt]) => {
                          const pct = Math.round((cnt / analysisData.total) * 100)
                          const hl = cnt === maxV && maxV > 0
                          return (
                            <div key={label} className="flex flex-col items-center gap-1">
                              <span className="text-xs text-gray-500">{pct}%</span>
                              <div className={`w-12 rounded-t ${hl ? 'bg-indigo-500' : 'bg-gray-200'}`} style={{ height: `${Math.max(6, pct * 1.6)}px` }} />
                              <span className={`text-xs font-semibold ${hl ? 'text-indigo-600' : 'text-gray-400'}`}>{label}</span>
                              <span className="text-xs text-gray-400">{cnt}회</span>
                            </div>
                          )
                        })
                      })()}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-3">번호 총합 구간 <span className="ml-1 text-gray-400 font-normal">(평균 {analysisData.sumAvg})</span></p>
                    <div className="flex gap-4 items-end flex-wrap">
                      {(() => {
                        const entries: { label: string; count: number }[] = analysisData.sortedBins
                        const maxV = entries.length ? Math.max(...entries.map(e => e.count)) : 0
                        return entries.map((bin) => {
                          const pct = Math.round((bin.count / analysisData.total) * 100)
                          const hl = bin.count === maxV && maxV > 0
                          return (
                            <div key={bin.label} className="flex flex-col items-center gap-1">
                              <span className="text-xs text-gray-500">{pct}%</span>
                              <div className={`w-14 rounded-t ${hl ? 'bg-amber-400' : 'bg-gray-200'}`} style={{ height: `${Math.max(6, pct * 1.6)}px` }} />
                              <span className={`text-xs font-semibold ${hl ? 'text-amber-600' : 'text-gray-400'}`}>{bin.label}</span>
                              <span className="text-xs text-gray-400">{bin.count}회</span>
                              {hl && <span className="text-xs text-amber-500 font-bold">▲최다</span>}
                            </div>
                          )
                        })
                      })()}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
