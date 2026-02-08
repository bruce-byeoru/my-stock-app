import requests
from bs4 import BeautifulSoup

def crawl_naver_news(keyword):
    # 1. 네이버 뉴스 검색 URL (query 부분에 검색어 삽입)
    url = f"https://search.naver.com/search.naver?where=news&query={keyword}"
    
    # 2. HTTP 요청 (네이버에서 차단하지 않도록 headers 추가)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        # 3. HTML 파싱
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 4. 뉴스 기사 요소 선택: 여러 후보 선택자를 시도
        selectors = ["a._sp_each_title", ".news_tit", ".api_txt_lines .api_txt_lines", "a._sp_each_title"]
        articles = []
        sel_used = None
        for sel in selectors:
            found = soup.select(sel)
            if found:
                articles = found
                sel_used = sel
                break

        # 최종 fallback: 모든 링크를 검사
        if not articles:
            articles = soup.select("a")
            sel_used = "a (fallback)"

        print(f"--- '{keyword}' 검색 결과 (선택자: {sel_used}) ---")

        # 뉴스 도메인 필터: 외부 뉴스 기사 링크만 수집
        news_domains = [
            'n.news.naver.com', 'news.naver.com', '.co.kr/', 'chosun.com', 'joongang.co.kr',
            'donga.com', 'hankyung.com', 'mk.co.kr', 'etnews.com', 'newsis.com', 'yonhapnews.co.kr',
            'mt.co.kr', 'sedaily.com', 'news1.kr', 'yna.co.kr', 'etoday.co.kr', 'edaily.co.kr',
            'money.mt.co.kr', 'news.tf.co.kr', 'fnnews.com'
        ]

        filtered = []
        for article in articles:
            if not article:
                continue
            href = article.get('href', '') or ''
            # anchor가 아닌 요소일 경우 내부 a 태그 탐색
            if not href:
                a = article.find('a')
                href = a.get('href', '') if a else ''

            if href and any(d in href for d in news_domains):
                filtered.append((article, href))

        # 추가 시도: 명시적 기사 앵커 선택자 검색
        if not filtered:
            anchors = soup.select('a._sp_each_title')
            for a in anchors:
                href = a.get('href', '')
                if href and any(d in href for d in news_domains):
                    filtered.append((a, href))

        # 최종 fallback: n.news 또는 news.naver 포함 링크만 허용
        if not filtered:
            for article in articles:
                href = article.get('href', '') or ''
                if 'n.news.naver.com' in href or 'news.naver.com' in href:
                    filtered.append((article, href))

        if not filtered:
            print('뉴스 기사 링크를 찾지 못했습니다. 전체 앵커 일부를 제목 위주로 출력합니다 (디버그용):')
            for i, article in enumerate(articles[:30], 1):
                title = article.get_text(strip=True) if article else ''
                print(f"{i}. {title}")
            return

        # 필터된 기사 출력 (최대 15건)
        for i, (article, link) in enumerate(filtered[:15], 1):
            title = article.get_text(strip=True) if article else ''
            print(f"{i}. {title}")
    else:
        print(f"접속 실패: {response.status_code}")

# 실행부: "삼성전자" 검색
if __name__ == "__main__":
    search_query = "삼성전자"
    crawl_naver_news(search_query)