import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const drwNo = searchParams.get('drwNo')
  
  if (!drwNo) {
    return NextResponse.json({ error: 'drwNo parameter is required' }, { status: 400 })
  }

  try {
    // Add common browser-like headers to improve chance of successful response
    const response = await fetch(
      `https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo=${drwNo}`,
      {
        headers: {
          'Accept': 'application/json, text/javascript, */*; q=0.01',
          'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Referer': 'https://www.dhlottery.co.kr/',
          'X-Requested-With': 'XMLHttpRequest',
        },
      }
    )

    if (!response.ok) {
      console.error('Lotto API non-ok response:', response.status, response.statusText)
      throw new Error('Failed to fetch lottery data')
    }

    // Read as text first to detect HTML error pages
    const text = await response.text()
    try {
      const data = JSON.parse(text)
      return NextResponse.json(data)
    } catch (parseErr) {
      console.error('Lotto API Error: response not JSON (likely HTML)', parseErr)

      // 폴백: headless 브라우저로 시도 (동적 JS 실행 환경에서 API 호출)
      try {
        const { fetchLottoViaHeadless } = await import('@/lib/puppeteer-fetch')
        const headlessResult = await fetchLottoViaHeadless(Number(drwNo))

        if (headlessResult && !headlessResult.__error) {
          // If headless returned raw text wrapper, try parse
          if (headlessResult.__raw) {
            try {
              const parsed = JSON.parse(headlessResult.__raw)
              return NextResponse.json(parsed)
            } catch (e) {
              return NextResponse.json({ error: 'Headless returned non-JSON', raw: String(headlessResult.__raw).slice(0, 1000) }, { status: 502 })
            }
          }

          return NextResponse.json(headlessResult)
        }
      } catch (headlessErr) {
        console.error('Headless fallback failed:', headlessErr)
      }

      return NextResponse.json(
        { error: 'Lotto API returned non-JSON response', raw: text.slice(0, 1000) },
        { status: 502 }
      )
    }
  } catch (error) {
    console.error('Lotto API Error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch lottery data' },
      { status: 500 }
    )
  }
}
