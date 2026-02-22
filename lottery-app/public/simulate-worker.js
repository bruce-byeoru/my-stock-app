// Worker for simulate lotto sets using bitmask popcount
self.onmessage = function (ev) {
  const { type, sets, rows } = ev.data
  if (type === 'lotto') {
    // ensure masks
    for (const s of sets) {
      if (s.mask === undefined) {
        let m = 0n
        for (const n of s.numbers) m |= (1n << BigInt(n - 1))
        s.mask = m
      } else {
        // convert numeric string to BigInt if necessary
        if (typeof s.mask === 'string') s.mask = BigInt(s.mask)
      }
      s.stats = { rank1: 0, rank2: 0, rank3: 0, rank4: 0, rank5: 0 }
    }

    function popcount(n) {
      let x = n
      let c = 0
      while (x) { x &= x - 1n; c++ }
      return c
    }

    const total = rows.length
    for (let i = 0; i < total; i++) {
      const draw = rows[i]
      const drawMask = (1n << BigInt(draw.drwtNo1 - 1)) | (1n << BigInt(draw.drwtNo2 - 1)) | (1n << BigInt(draw.drwtNo3 - 1)) |
        (1n << BigInt(draw.drwtNo4 - 1)) | (1n << BigInt(draw.drwtNo5 - 1)) | (1n << BigInt(draw.drwtNo6 - 1))
      const bonusBit = 1n << BigInt(draw.bnusNo - 1)
      for (const s of sets) {
        const common = s.mask & drawMask
        const matches = popcount(common)
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

      // progress report every ~2% of work
      if (i % Math.max(1, Math.floor(total / 50)) === 0) {
        const pct = Math.floor(((i + 1) / total) * 100)
        self.postMessage({ progress: pct })
      }
    }

    // return resulting sets (convert BigInt to string to be transferable in older browsers)
    for (const s of sets) {
      if (typeof s.mask === 'bigint') s.mask = s.mask.toString()
    }

    self.postMessage({ done: true, sets })
  }
}
