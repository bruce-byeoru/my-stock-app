#!/usr/bin/env python3
"""최종 뉴스 함수 검증 스크립트"""
import sys
sys.path.insert(0, '/workspaces/my-stock-app')
from app3 import get_company_news

for company in ['SK하이닉스', '현대차', '삼성전자']:
    print('\n===', company, '뉴스 테스트 ===')
    news = get_company_news(company, max_news=10)
    if not news:
        print('뉴스 없음')
        continue
    for i, n in enumerate(news,1):
        print(f"[{i}] {n['title']}\n    {n['url']}")
