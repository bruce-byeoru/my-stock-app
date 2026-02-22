const fs = require('fs')
const { Worker } = require('worker_threads')

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
      let mask = 0n
      for (const n of numbers) mask |= (1n << BigInt(n - 1))
      sets.push({ id: sets.length + 1, numbers, mask, stats: { rank1:0, rank2:0, rank3:0, rank4:0, rank5:0 } })
    }
  }
  return sets
}

async function main() {
  const args = process.argv.slice(2)
  if (args.length < 2) { console.log('Usage: node bench-parallel.js <lotto_json_file> <count>'); process.exit(1) }
  const rowsFile = args[0]
  const count = Number(args[1])
  const data = JSON.parse(fs.readFileSync(rowsFile, 'utf8'))
  const rows = data.rows || data
  console.log(`Loaded ${rows.length} draws`)
  console.log(`Generating ${count} sets...`)
  const t0 = process.hrtime.bigint()
  const sets = generateUniqueLottoSets(count)
  const t1 = process.hrtime.bigint()
  console.log(`Generated ${sets.length} sets in ${Number(t1-t0)/1e6} ms`)

  const hw = require('os').cpus().length
  const workers = Math.min(hw, 8)
  const chunkSize = Math.ceil(sets.length / workers)
  console.log(`Spawning ${workers} workers (chunk ${chunkSize})`)

  const s0 = process.hrtime.bigint()
  const promises = []
  for (let i = 0; i < workers; i++) {
    const chunk = sets.slice(i * chunkSize, (i + 1) * chunkSize)
    if (chunk.length === 0) continue
    promises.push(new Promise((resolve, reject) => {
      const w = new Worker(__dirname + '/worker-simulate-thread.js')
      w.on('message', (res) => { resolve(res); w.terminate() })
      w.on('error', reject)
      w.postMessage({ sets: chunk, rows })
    }))
  }
  const parts = await Promise.all(promises)
  const s1 = process.hrtime.bigint()
  console.log(`Parallel simulation time: ${Number(s1-s0)/1e6} ms`)
}

main().catch(e => { console.error(e); process.exit(1) })
