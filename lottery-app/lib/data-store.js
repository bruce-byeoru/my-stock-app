const fs = require('fs-extra')
const path = require('path')

const DATA_DIR = path.resolve(process.cwd(), 'data')

// Supabase optional integration: when SUPABASE_URL and SUPABASE_KEY are set,
// use Supabase table storage for persistent data.
let supabase = null
if (process.env.SUPABASE_URL && process.env.SUPABASE_KEY) {
  try {
    const { createClient } = require('@supabase/supabase-js')
    supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_KEY)
  } catch (e) {
    console.warn('Supabase client not available:', e && e.message)
    supabase = null
  }
}

function filePath(type) {
  return path.join(DATA_DIR, `${type}.json`)
}

// Postgres folds unquoted identifiers to lowercase.
// Convert row keys to lowercase before upsert.
function toLower(row) {
  const out = {}
  for (const k of Object.keys(row)) out[k.toLowerCase()] = row[k]
  return out
}

// Restore lotto row keys from DB lowercase back to camelCase expected by the app.
// pension keys (round, num1-6, group) are already lowercase – no mapping needed.
function fromLottoRow(row) {
  return {
    drwNo:  row.drwno  ?? row.drwNo,
    drwtNo1: row.drwtno1 ?? row.drwtNo1,
    drwtNo2: row.drwtno2 ?? row.drwtNo2,
    drwtNo3: row.drwtno3 ?? row.drwtNo3,
    drwtNo4: row.drwtno4 ?? row.drwtNo4,
    drwtNo5: row.drwtno5 ?? row.drwtNo5,
    drwtNo6: row.drwtno6 ?? row.drwtNo6,
    bnusNo:  row.bnusno  ?? row.bnusNo,
  }
}

async function load(type) {
  // If supabase configured, read from table
  if (supabase) {
    try {
      const table = type === 'lotto' ? 'lotto' : 'pension'
      const orderCol = type === 'lotto' ? 'drwno' : 'round'
      const { data, error } = await supabase.from(table).select('*').order(orderCol, { ascending: true })
      if (error) throw error
      if (!Array.isArray(data)) return []
      // Remap lotto rows from DB lowercase to camelCase; pension rows are fine as-is.
      return type === 'lotto' ? data.map(fromLottoRow) : data
    } catch (e) {
      console.error('Supabase load error', e)
      // fallback to filesystem
    }
  }

  try {
    await fs.ensureDir(DATA_DIR)
    const p = filePath(type)
    const exists = await fs.pathExists(p)
    if (!exists) return []
    const data = await fs.readJson(p)
    return Array.isArray(data) ? data : []
  } catch (e) {
    return []
  }
}

async function save(type, arr) {
  // Prefer supabase when available
  if (supabase) {
    try {
      const table = type === 'lotto' ? 'lotto' : 'pension'
      // Postgres lowercase: convert keys before upsert
      const conflictKey = type === 'lotto' ? 'drwno' : 'round'
      const toUpsert = arr.map(toLower)
      const { error } = await supabase.from(table).upsert(toUpsert, { onConflict: [conflictKey] })
      if (error) throw error
      return
    } catch (e) {
      console.error('Supabase save error', e)
      // fallback to filesystem
    }
  }

  await fs.ensureDir(DATA_DIR)
  await fs.writeJson(filePath(type), arr, { spaces: 2 })
}

function merge(existing, incoming, key = 'drwNo') {
  const map = new Map(existing.map(x => [Number(x[key]), x]))
  for (const it of incoming) {
    if (it && it[key] != null) {
      map.set(Number(it[key]), it)
    }
  }
  return Array.from(map.values()).sort((a, b) => Number(a[key]) - Number(b[key]))
}

module.exports = { load, save, merge }
