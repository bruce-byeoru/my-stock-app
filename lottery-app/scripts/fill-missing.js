#!/usr/bin/env node
const fetch = (...args) => import('node-fetch').then(m => m.default(...args))
const { load, save, merge } = require('../lib/data-store')
const { getCurrentLottoRound, getCurrentPensionRound } = require('../lib/lottery-utils')

async function fetchFromApi(type, round) {
  try {
    if (type === 'lotto') {
      const res = await fetch(`http://localhost:3000/api/lotto?drwNo=${round}`)
      return await res.json()
    } else {
      const res = await fetch(`http://localhost:3000/api/pension?round=${round}`)
      return await res.json()
    }
  } catch (e) {
    return null
  }
}

async function main() {
  const [,, type] = process.argv
  if (!type || (type !== 'lotto' && type !== 'pension')) {
    console.error('Usage: node fill-missing.js <lotto|pension>')
    process.exit(1)
  }

  const existing = await load(type)
  const key = type === 'lotto' ? 'drwNo' : 'round'
  const present = new Set(existing.map(e => Number(e[key])))
  const current = type === 'lotto' ? getCurrentLottoRound() : getCurrentPensionRound()
  const missing = []
  for (let r = 1; r <= current; r++) if (!present.has(r)) missing.push(r)

  console.log(`[fill-missing] type=${type} missingCount=${missing.length}`)
  const fetched = []
  for (const r of missing) {
    const data = await fetchFromApi(type, r)
    if (data && data[key] != null) {
      fetched.push(data)
      console.log('  fetched', r)
    } else {
      console.log('  skip', r)
    }
    await new Promise(s => setTimeout(s, 200))
  }

  if (fetched.length) {
    const merged = merge(existing, fetched, key)
    await save(type, merged)
    console.log(`[fill-missing] saved ${fetched.length} new rows, total ${merged.length}`)
  } else {
    console.log('[fill-missing] no data fetched')
  }
}

main().catch(e => { console.error(e); process.exit(1) })
