const fs = require('fs-extra')
const path = require('path')

const DATA_DIR = path.resolve(process.cwd(), 'data')

function filePath(type) {
  return path.join(DATA_DIR, `${type}.json`)
}

async function load(type) {
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
