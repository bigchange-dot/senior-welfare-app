"""강북구청 언론보도 페이지의 실제 링크 구조 확인 (세션 우회 사용)"""
import sys
sys.path.insert(0, '.')
from scraping_function import _get_gangbuk_session
from bs4 import BeautifulSoup

urls = {
    "언론보도": "https://www.gangbuk.go.kr/portal/bbs/B0000260/list.do?menuNo=200638",
    "보도자료": "https://www.gangbuk.go.kr/portal/bbs/B0000142/list.do?menuNo=200625",
    "채용":    "https://www.gangbuk.go.kr/portal/bbs/B0000154/list.do?menuNo=200510",
}

for name, url in urls.items():
    print(f"\n=== {name} ===")
    try:
        session = _get_gangbuk_session(url)
        res     = session.get(url, timeout=15)
        soup    = BeautifulSoup(res.text, "lxml")

        rows = soup.select("table tbody tr")
        print(f"행 수: {len(rows)}")
        for row in rows[:3]:
            links = row.find_all("a")
            for a in links:
                href = a.get("href", "")
                text = a.get_text(strip=True)[:30]
                print(f"  href={href[:80]!r}  text={text!r}")
    except Exception as e:
        print(f"  오류: {e}")
