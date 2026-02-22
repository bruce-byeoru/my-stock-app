#!/usr/bin/env node
const xlsx = require('xlsx')
const fs = require('fs-extra')
const path = require('path')
const { load, save, merge } = require('../lib/data-store')

function parseCSV(filePath) {
  const txt = fs.readFileSync(filePath, 'utf8')
  const lines = txt.split(/\r?\n/).filter(Boolean)
  const [header, ...rows] = lines
  const cols = header.split(',').map(s => s.trim())
  return rows.map(r => {
    const values = r.split(',').map(s => s.trim())
    const obj = {}
    cols.forEach((c, i) => (obj[c] = values[i]))
    return obj
  })
}

function normalize(rows, type) {
  if (type === 'lotto') {
    return rows.map(r => ({
      drwNo: Number(r.drwNo || r.drw_no || r.round),
      drwNoDate: r.drwNoDate || r.drwNoDate || r.date || r.drwNo_Date || r.drwNoDate,
      drwtNo1: Number(r.drwtNo1 || r.drwt_no1 || r.no1),
      drwtNo2: Number(r.drwtNo2 || r.drwt_no2 || r.no2),
      drwtNo3: Number(r.drwtNo3 || r.drwt_no3 || r.no3),
      drwtNo4: Number(r.drwtNo4 || r.drwt_no4 || r.no4),
      drwtNo5: Number(r.drwtNo5 || r.drwt_no5 || r.no5),
      drwtNo6: Number(r.drwtNo6 || r.drwt_no6 || r.no6),
      bnusNo: Number(r.bnusNo || r.bonus || r.bnus_no || r.bonus_no),
    }))
  }

  // pension
  return rows.map(r => ({
    round: Number(r.round || r.drwNo || r.drw_no),
    drawDate: r.drawDate || r.date || r.draw_date,
    group: r.group != null ? Number(r.group) : undefined,
    num1: Number(r.num1 || r.no1),
    num2: Number(r.num2 || r.no2),
    num3: Number(r.num3 || r.no3),
    num4: Number(r.num4 || r.no4),
    num5: Number(r.num5 || r.no5),
    num6: Number(r.num6 || r.no6),
  }))
}

function readWorkbook(filePath) {
  const ext = path.extname(filePath).toLowerCase()
  if (ext === '.csv') return parseCSV(filePath)
  const wb = xlsx.readFile(filePath)
  const sheet = wb.Sheets[wb.SheetNames[0]]
  return xlsx.utils.sheet_to_json(sheet, { defval: null })
}

async function main() {
  const [,, type, file] = process.argv
  if (!type || !file) {
    console.error('Usage: node import-data.js <lotto|pension> <file.csv|file.xlsx>')
    process.exit(1)
  }
  const raw = readWorkbook(file)
  const normalized = normalize(raw, type)
  const existing = await load(type)
  const key = type === 'lotto' ? 'drwNo' : 'round'
  const merged = merge(existing, normalized, key)
  await save(type, merged)
  console.log(`[import-data] imported ${normalized.length} rows into '${type}', total ${merged.length}`)
}

main().catch(e => { console.error(e); process.exit(1) })
