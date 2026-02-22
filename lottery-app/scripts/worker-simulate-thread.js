const { parentPort } = require('worker_threads')

function popcountBigInt(n) {
  let x = n
  let c = 0
  while (x) { x &= x - 1n; c++ }
  return c
}

parentPort.on('message', ({ sets, rows }) => {
  // ensure masks
  for (const s of sets) {
    if (s.mask === undefined) {
      let m = 0n
      for (const n of s.numbers) m |= (1n << BigInt(n - 1))
      s.mask = m
    } else if (typeof s.mask === 'string') {
      s.mask = BigInt(s.mask)
    }
    s.stats = { rank1: 0, rank2: 0, rank3: 0, rank4: 0, rank5: 0 }
  }

  for (const draw of rows) {
    const drawMask = (1n << BigInt(draw.drwtNo1 - 1)) | (1n << BigInt(draw.drwtNo2 - 1)) | (1n << BigInt(draw.drwtNo3 - 1)) |
      (1n << BigInt(draw.drwtNo4 - 1)) | (1n << BigInt(draw.drwtNo5 - 1)) | (1n << BigInt(draw.drwtNo6 - 1))
    const bonusBit = 1n << BigInt(draw.bnusNo - 1)
    for (const s of sets) {
      const common = s.mask & drawMask
      const matches = popcountBigInt(common)
      const hasBonus = (s.mask & bonusBit) !== 0n
      let rank = 0
      if (matches === 6) rank = 1
      else if (matches === 5 && hasBonus) rank = 2
      else if (matches === 5) rank = 3
      else if (matches === 4) rank = 4
      else if (matches === 3) rank = 5
      if (rank === 1) s.stats.rank1++
      else if (rank === 2) s.stats.rank2++
      else if (rank === 3) s.stats.rank3++
      else if (rank === 4) s.stats.rank4++
      else if (rank === 5) s.stats.rank5++
    }
  }

  parentPort.postMessage(sets.map(s => ({ id: s.id, stats: s.stats })))
})
