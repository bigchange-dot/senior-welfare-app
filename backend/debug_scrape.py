"""링크 수집 결과만 빠르게 확인하는 디버그 스크립트 (Gemini/Firestore 호출 없음)"""
from scraping_function import (
    fetch_bokjiro_api,
    scrape_seongdong_jobs,
    scrape_sdsenior,
    scrape_gangbuk_jobs,
    scrape_gangbuk_press,
    scrape_gangbuk_media,
)

scrapers = [
    ("복지로 API",         fetch_bokjiro_api),
    ("성동구청 채용",       scrape_seongdong_jobs),
    ("성동구 어르신일자리", scrape_sdsenior),
    ("강북구청 채용",       scrape_gangbuk_jobs),
    ("강북구청 보도자료",   scrape_gangbuk_press),
    ("강북구청 언론보도",   scrape_gangbuk_media),
]

total = 0
for name, fn in scrapers:
    results = fn()
    print(f"\n[{name}] {len(results)}건")
    for r in results[:3]:
        print(f"  · {r['title'][:40]}")
        print(f"    {r['url'][:80]}")
    total += len(results)

print(f"\n총 수집: {total}건")
