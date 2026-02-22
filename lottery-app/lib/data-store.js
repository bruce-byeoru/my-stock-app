const fs = require('fs-extra')
const path = require('path')

const DATA_DIR = path.resolve(process.cwd(), 'data')

// Supabase optional integration: when SUPABASE_URL and SUPABASE_KEY are set,
// use Supabase table storage for persistent data. Table name will be `lotto`
// and `pension`, with a JSON `payload` column and `id`/`round` or `drwNo` as key.
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

async function load(type) {
  // If supabase configured, read from table
  if (supabase) {
    try {
      const table = type === 'lotto' ? 'lotto' : 'pension'
      const { data, error } = await supabase.from(table).select('*').order(type === 'lotto' ? 'drwNo' : 'round', { ascending: true })
      if (error) throw error
      // Expect stored rows to match shape already
      return Array.isArray(data) ? data.map(d => ({ ...d })) : []
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
      // Upsert rows by key. For lotto use drwNo, for pension use round
      const key = type === 'lotto' ? 'drwNo' : 'round'
      // Ensure rows include the key column
      const toUpsert = arr.map(r => ({ ...r }))
      const { error } = await supabase.from(table).upsert(toUpsert, { onConflict: [key] })
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
