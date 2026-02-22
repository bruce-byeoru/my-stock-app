const fs = require('fs')

function generateLottoNumbers() {
  const arr = Array.from({ length: 45 }, (_, i) => i + 1)
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    const tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp
  }
  return arr.slice(0, 6).sort((a, b) => a - b)
}

function generateUniqueLottoSets(count) {
  const sets = []
  const setStrings = new Set()
  let attempts = 0
  while (sets.length < count && attempts < count * 10) {
    attempts++
    const numbers = generateLottoNumbers()
    const key = numbers.join(',')
    if (!setStrings.has(key)) {
      setStrings.add(key)
      // compute bigint mask
      let mask = 0n
      for (const n of numbers) mask |= (1n << BigInt(n - 1))
      sets.push({ id: sets.length + 1, numbers, mask, stats: { rank1:0, rank2:0, rank3:0, rank4:0, rank5:0 } })
    }
  }
  return sets
}

function simulateLotto(numberSets, lottoData) {
  const updatedSets = numberSets.map(s => ({ ...s, stats: { rank1:0, rank2:0, rank3:0, rank4:0, rank5:0 } }))
  function popcountBigInt(n) {
    let x = n
    let c = 0
    while (x) {
      x &= x - 1n
      c++
    }
    return c
  }
  for (const draw of lottoData) {
    const drawMask = (1n << BigInt(draw.drwtNo1 - 1)) | (1n << BigInt(draw.drwtNo2 - 1)) | (1n << BigInt(draw.drwtNo3 - 1)) |
      (1n << BigInt(draw.drwtNo4 - 1)) | (1n << BigInt(draw.drwtNo5 - 1)) | (1n << BigInt(draw.drwtNo6 - 1))
    const bonusBit = 1n << BigInt(draw.bnusNo - 1)
    for (const set of updatedSets) {
      let mask = set.mask
      if (mask === undefined) {
        mask = 0n
        for (const n of set.numbers) mask |= (1n << BigInt(n - 1))
        set.mask = mask
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

async function main() {
  const args = process.argv.slice(2)
  if (args.length < 2) {
    console.log('Usage: node bench-simulate.js <lotto_json_file> <count>')
    process.exit(1)
  }
  const jsonFile = args[0]
  const count = Number(args[1])
  if (!fs.existsSync(jsonFile)) { console.error('File not found:', jsonFile); process.exit(2) }
  const data = JSON.parse(fs.readFileSync(jsonFile, 'utf8'))
  const rows = data.rows || data
  console.log(`Loaded ${rows.length} draws from ${jsonFile}`)
  console.log(`Generating ${count} unique sets (may take a moment)...`)
  const t0 = process.hrtime.bigint()
  const sets = generateUniqueLottoSets(count)
  const t1 = process.hrtime.bigint()
  console.log(`Generated ${sets.length} sets in ${Number(t1-t0)/1e6} ms`)
  console.log('Simulating...')
  const s0 = process.hrtime.bigint()
  simulateLotto(sets, rows)
  const s1 = process.hrtime.bigint()
  console.log(`Simulation time: ${Number(s1-s0)/1e3/1e3} ms`)
}

main().catch(e => { console.error(e); process.exit(1) })
