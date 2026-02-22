import { NextResponse } from 'next/server'
import path from 'path'

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const { type, rows } = body
    if (!type || !Array.isArray(rows)) {
      return NextResponse.json({ error: 'Invalid payload: missing type or rows array' }, { status: 400 })
    }

    // basic validation & helpful errors
    const problems: string[] = []
    const invalidIndexes: number[] = []
    rows.forEach((r: any, idx: number) => {
      const hasRound = r.drwNo != null || r.round != null || r.round_no != null || r.no != null
      const hasNumbers = Array.isArray(r.numbers) ? r.numbers.length >= 6 : (
        r.drwtNo1 != null && r.drwtNo2 != null && r.drwtNo3 != null && r.drwtNo4 != null && r.drwtNo5 != null && r.drwtNo6 != null
      ) || (
        r.num1 != null && r.num2 != null && r.num3 != null && r.num4 != null && r.num5 != null && r.num6 != null
      )
      if (!hasRound || !hasNumbers) {
        invalidIndexes.push(idx)
        problems.push(`row ${idx}: missing round or numbers`) 
      }
    })
    if (invalidIndexes.length) {
      console.error('Upload validation failed', { type, invalidIndexes, problems: problems.slice(0,5) })
      return NextResponse.json({ error: 'Validation failed', details: { invalidCount: invalidIndexes.length, examples: problems.slice(0,5) } }, { status: 400 })
    }

    // dynamic import commonjs util
    const ds = await import('../../../../lib/data-store.js')
    const { load, save, merge } = ds

    const existing = await load(type)
    const key = type === 'lotto' ? 'drwNo' : 'round'

    // normalize rows to match storage shape
    const normalized = rows.map((r: any) => {
      if (type === 'lotto') {
        const drwNo = Number(r.drwNo ?? r.round ?? r.round_no ?? r.no)
        const nums = r.numbers || [r.drwtNo1, r.drwtNo2, r.drwtNo3, r.drwtNo4, r.drwtNo5, r.drwtNo6].filter(n=>n!=null)
        const obj: any = { drwNo }
        nums.forEach((n: any, i: number) => obj[`drwtNo${i+1}`] = Number(n))
        if (r.bnusNo != null) obj.bnusNo = Number(r.bnusNo)
        return obj
      }
      // pension
      const round = Number(r.round ?? r.drwNo ?? r.no)
      const nums = r.numbers || [r.num1, r.num2, r.num3, r.num4, r.num5, r.num6].filter(n=>n!=null)
      const obj: any = { round }
      nums.forEach((n: any, i: number) => obj[`num${i+1}`] = Number(n))
      if (r.group != null) obj.group = Number(r.group)
      return obj
    })

    const merged = merge(existing, normalized, key)
    await save(type, merged)

    return NextResponse.json({ saved: normalized.length, total: merged.length })
  } catch (err) {
    console.error('upload error', err)
    return NextResponse.json({ error: String(err) }, { status: 500 })
  }
}
