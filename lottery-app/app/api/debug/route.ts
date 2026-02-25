import { NextResponse } from 'next/server'

export async function GET() {
  const hasUrl = !!process.env.SUPABASE_URL
  const hasKey = !!process.env.SUPABASE_KEY
  let supabaseRows: number | string = 'not_tried'

  if (hasUrl && hasKey) {
    try {
      const { createClient } = await import('@supabase/supabase-js')
      const sb = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_KEY!)
      const { data, error } = await sb.from('lotto').select('drwno', { count: 'exact' }).limit(1)
      if (error) supabaseRows = `error: ${error.message}`
      else supabaseRows = (data as any[])?.length ?? 0
    } catch (e: any) {
      supabaseRows = `exception: ${e?.message}`
    }
  }

  return NextResponse.json({
    SUPABASE_URL: hasUrl ? process.env.SUPABASE_URL : 'NOT SET',
    SUPABASE_KEY_SET: hasKey,
    supabase_lotto_test: supabaseRows,
    node_version: process.version,
  })
}
