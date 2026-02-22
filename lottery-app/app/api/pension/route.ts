import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const round = searchParams.get('round')
  
  if (!round) {
    return NextResponse.json({ error: 'round parameter is required' }, { status: 400 })
  }

  try {
    // 연금복권 API 엔드포인트 (실제 API에 맞게 조정 필요)
    const response = await fetch(
      `https://www.dhlottery.co.kr/common.do?method=get720Number&round=${round}`,
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
      console.error('Pension API non-ok response:', response.status, response.statusText)
      throw new Error('Failed to fetch pension lottery data')
    }

    const text = await response.text()
    try {
      const data = JSON.parse(text)
      return NextResponse.json(data)
    } catch (parseErr) {
      console.error('Pension API Error: response not JSON (likely HTML)', parseErr)
      return NextResponse.json(
        { error: 'Pension API returned non-JSON response', raw: text.slice(0, 1000) },
        { status: 502 }
      )
    }
  } catch (error) {
    console.error('Pension Lottery API Error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch pension lottery data' },
      { status: 500 }
    )
  }
}
