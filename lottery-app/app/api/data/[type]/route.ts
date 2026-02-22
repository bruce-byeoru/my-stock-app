import { NextResponse } from 'next/server'

export async function GET(request: Request, { params }: { params: { type: string } }) {
  try {
    const type = params.type
    if (!type || (type !== 'lotto' && type !== 'pension')) {
      return NextResponse.json({ error: 'Invalid type' }, { status: 400 })
    }

    const ds = await import('../../../../lib/data-store.js')
    const { load } = ds
    const data = await load(type)
    return NextResponse.json({ total: data.length, rows: data })
  } catch (err) {
    console.error('data GET error', err)
    return NextResponse.json({ error: String(err) }, { status: 500 })
  }
}
