export async function fetchLottoViaHeadless(drwNo: number) {
  try {
    // 동적 렌더링 및 JS 기반 요청을 우회하기 위해 Puppeteer를 사용
    // 런타임에 puppeteer를 동적으로 import하여 의존성 없을 때에도 파일 로드 가능
    const puppeteer = await import('puppeteer')

    const browser = await puppeteer.launch({
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    })
    const page = await browser.newPage()

    // 페이지 컨텍스트에서 API를 호출하도록 함 (브라우저 환경과 동일)
    const apiUrl = `https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo=${drwNo}`

    let result = null
    try {
      await page.goto('about:blank')
      result = await page.evaluate(async (url) => {
        try {
          const res = await fetch(url, { credentials: 'omit', redirect: 'follow' })
          const txt = await res.text()
          try {
            return JSON.parse(txt)
          } catch (e) {
            return { __raw: txt }
          }
        } catch (err) {
          return { __error: String(err) }
        }
      }, apiUrl)
    } finally {
      await browser.close()
    }

    return result
  } catch (err) {
    console.error('Headless fetch failed:', err)
    return null
  }
}
