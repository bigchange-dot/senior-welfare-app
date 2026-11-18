"""범용 게시판 목록 파서 (v1.5, 2026-11-18) — 복지관·시니어클럽 게시판용.

목록 페이지에서 '날짜가 가까이 붙은 링크'를 글로 읽는다. 그누보드, /bbs/?bid= 형식, 사이트별 자체 구조를
사이트마다 스크래퍼를 짜지 않고 한 파서로 처리한다. 2026-11-18 경기 99곳 점검에 쓴 방법을 다듬은 것
(docs/경기-복지관-조사-2026-11-18.md). 출처 목록은 board_sources.py.

글 행 판정: 링크 글자가 한글 2자 이상이고, 링크에서 위로 4단계 안의 작은 영역(400자 이하, 글 링크 2개 이하)에
날짜가 있으면 글. 메뉴·바로가기 링크는 가까이에 날짜가 없어서 빠진다.

실행(점검용, 저장 안 함): venv/bin/python board_parser.py [이름 일부]
"""

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_AGE_DAYS = 45      # 이보다 오래된 글은 넘김 (고정 공지·지난 글을 매번 AI에 묻지 않게)
DEFAULT_LIMIT = 15

_FULL_DATE = re.compile(
    r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
    r"|(?<![\d.])(\d{2})[.\-](\d{2})[.\-](\d{2})(?![\d.])"
)
_MONTH_DAY = re.compile(r"(?<![\d.:\-])(\d{2})[.\-](\d{2})(?![\d:\-.])")
_HANGUL = re.compile(r"[가-힣]")
# 링크 글자에 섞여 들어오는 목록 표시 (번호·공지 표시·작성자·조회수·새 글 표시)
_LEAD_NOISE = re.compile(r"^(?:\[?공지\]?|NO\.\s*\d+|\d{1,6}|N|NEW|new|새글)\s+")
_TAIL_NOISE = re.compile(r"\s*(?:\|\s*)?(?:HIT|조회수?)\s*:?\s*\d+.*$|\s+(?:최고관리자|관리자|운영자|admin|새글|N|NEW)\s*$")
_IGNORE_TITLES = ("삭제된 게시물", "오시는길", "오시는 길", "1:1문의")

# 옛 암호화 방식만 받는 사이트 (DH 키가 짧아 기본 설정으로는 handshake 실패) → tls_compat.LegacyTLSAdapter. 2026-11-18
LEGACY_TLS_HOSTS = {"www.swsc.co.kr"}   # 수원시니어클럽

# 글 링크가 자바스크립트인 게시판: 사이트 → (href·onclick에서 글 번호를 뽑는 식, 상세 주소 틀). 2026-11-18 확인
JS_LINKS: dict[str, tuple[re.Pattern, str]] = {
    # 광주시노인복지관: javascript:fView('8494') → 폼 제출이지만 같은 주소에 GET도 열림
    "www.gjswc.kr": (re.compile(r"fView\('(\d+)'\)"), "/gjnoin/sub3_1_view.do?board_idx={0}"),
    # 부천시 노인복지기관 포털: onclick="opView('2', '1005', '20261118152519256')"
    "senior.bucheon4u.kr": (re.compile(r"opView\('(\d+)',\s*'(\d+)',\s*'(\d+)'\)"),
                            "BD_selectBbs.do?q_domnCode={0}&q_bbsCode={1}&q_bbscttSn={2}"),
}


def parse_dates(text: str, today: datetime) -> list[datetime]:
    """글자 속 날짜들. 연도 없는 '11-17'은 올해로 보되 미래가 되면 작년으로"""
    found = []
    for m in _FULL_DATE.finditer(text):
        try:
            if m.group(1):
                found.append(datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            else:
                found.append(datetime(2000 + int(m.group(4)), int(m.group(5)), int(m.group(6))))
        except ValueError:
            pass
    if not found:
        for m in _MONTH_DAY.finditer(text):
            try:
                d = datetime(today.year, int(m.group(1)), int(m.group(2)))
            except ValueError:
                continue
            found.append(d if d <= today + timedelta(days=1) else d.replace(year=today.year - 1))
    return [d for d in found if datetime(2015, 1, 1) <= d <= today + timedelta(days=1)]


def clean_title(text: str) -> str:
    """링크 글자 → 제목. 행 전체가 링크인 게시판은 번호·날짜·작성자까지 붙어 온다"""
    t = re.sub(r"\s+", " ", text).strip()
    m = _FULL_DATE.search(t)
    if m and m.start() > 4:
        t = t[:m.start()].strip()
    for _ in range(3):
        t2 = _TAIL_NOISE.sub("", _LEAD_NOISE.sub("", t)).strip()
        if t2 == t:
            break
        t = t2
    return t


def _is_title(text: str) -> bool:
    """글 제목으로 볼 만한 링크 글자인지 — 한글 2자 미만(작성자 'admin' 등)·5자 미만('공지' 표시만 있는 링크)·메뉴 글자는 아님"""
    return len(_HANGUL.findall(text)) >= 2 and len(text) >= 5 and not any(w in text for w in _IGNORE_TITLES)


def _row_links(node) -> int:
    """영역 안의 글 링크 주소 수 — 2개를 넘으면 글 한 줄이 아니라 목록 전체(또는 메뉴)다"""
    return len({a["href"] for a in node.find_all("a", href=True) if _is_title(clean_title(a.get_text(" ", strip=True)))})


def parse_list(html: str, base_url: str, today: datetime,
               limit: int = DEFAULT_LIMIT, max_age_days: int = MAX_AGE_DAYS) -> list[tuple[str, str, datetime]]:
    """목록 HTML → [(제목, 글 주소, 날짜)] 최신순. 같은 주소는 한 번만"""
    soup = BeautifulSoup(html, "lxml")
    js_rule = JS_LINKS.get(urlparse(base_url).netloc)
    items: dict[str, tuple[str, datetime]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if js_rule and (not href or href.startswith(("#", "javascript"))):
            m = js_rule[0].search(f"{href} {a.get('onclick', '')}")
            href = js_rule[1].format(*m.groups()) if m else ""
        if not href or href.startswith(("#", "javascript", "mailto", "tel:")):
            continue
        title = clean_title(a.get_text(" ", strip=True))
        if not _is_title(title):
            continue
        node, when = a, None
        for _ in range(4):
            node = node.parent
            if node is None:
                break
            txt = node.get_text(" ", strip=True)
            if len(txt) > 400 or _row_links(node) > 2:
                break
            dates = parse_dates(txt, today)
            if dates:
                when = max(dates)
                break
        if when is None:
            continue
        url = urljoin(base_url, href)
        if url not in items or len(title) > len(items[url][0]):
            items[url] = (title, when)
    cutoff = today - timedelta(days=max_age_days)
    rows = sorted(((t, u, d) for u, (t, d) in items.items() if d >= cutoff), key=lambda x: x[2], reverse=True)
    return rows[:limit]


def _get(url: str, headers: dict) -> requests.Response:
    """목록 요청. 옛 암호화 사이트만 그 도메인에 LegacyTLSAdapter를 붙인 세션으로 (인증서 검증은 그대로)"""
    host = urlparse(url).netloc
    if host in LEGACY_TLS_HOSTS:
        import tls_compat
        with requests.Session() as session:
            session.mount(f"https://{host}", tls_compat.LegacyTLSAdapter())
            return session.get(url, headers=headers, timeout=15)
    return requests.get(url, headers=headers, timeout=15)


def scrape_board(list_urls, source: str, headers: dict, limit: int = DEFAULT_LIMIT,
                 today: datetime | None = None, labels: dict[str, str] | None = None) -> list[dict]:
    """출처 하나(목록 주소 1~2개) → 파이프라인 기사 목록. 실패하면 빈 목록 (파이프라인 전체는 계속)

    labels: 여러 기관이 한 게시판을 쓰는 곳(부천 포털)의 '제목 앞 기관 표시 → 출처 이름'. 표시가 없는 글은 넘긴다"""
    today = today or datetime.now()
    if isinstance(list_urls, str):
        list_urls = [list_urls]
    articles, seen = [], set()
    for list_url in list_urls:
        try:
            res = _get(list_url, headers)
            res.raise_for_status()
            if "charset" not in res.headers.get("content-type", "").lower():
                res.encoding = res.apparent_encoding or "utf-8"
            rows = parse_list(res.text, res.url, today, limit=limit)
        except Exception as e:
            logger.error(f"❌ {source} 목록 오류 ({list_url[:50]}): {e}")
            continue
        for title, url, _ in rows:
            if url in seen:
                continue
            seen.add(url)
            src = source
            if labels:
                label = next((k for k in sorted(labels, key=len, reverse=True) if title.startswith(k + " ")), None)
                if label is None:
                    continue
                src, title = labels[label], title[len(label):].strip()
            articles.append({"title": title, "url": url, "content": "", "source": src})
    logger.info(f"{source}: {len(articles)}건 (최근 {MAX_AGE_DAYS}일)")
    return articles


def scrape_json_board(cfg: dict, source: str, headers: dict, limit: int = DEFAULT_LIMIT,
                      today: datetime | None = None) -> list[dict]:
    """목록을 JSON으로 주는 게시판 (화성 동탄노인복지관). 본문도 함께 와서 상세 페이지를 따로 받지 않는다.

    cfg: api(주소), params, view(상세 주소 틀, {필드} 치환), title·date·body(JSON 필드 이름)"""
    today = today or datetime.now()
    cutoff = today - timedelta(days=MAX_AGE_DAYS)
    try:
        res = requests.get(cfg["api"], params=cfg.get("params"), timeout=15, headers={
            **headers, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest",
            "Referer": cfg.get("referer", cfg["api"]),
        })
        res.raise_for_status()
        items = res.json().get("items") or []
    except Exception as e:
        logger.error(f"❌ {source} JSON 목록 오류: {e}")
        return []
    articles = []
    for x in items:
        try:
            when = datetime.strptime(str(x[cfg["date"]])[:10], "%Y-%m-%d")
        except (KeyError, ValueError):
            continue
        title = str(x.get(cfg["title"]) or "").strip()
        if when < cutoff or not _is_title(title):
            continue
        body = BeautifulSoup(str(x.get(cfg["body"]) or ""), "lxml").get_text(" ", strip=True)
        articles.append({"title": title, "url": cfg["view"].format(**x), "content": body[:800],
                         "source": source, "_date": when})
    articles.sort(key=lambda a: a.pop("_date"), reverse=True)
    logger.info(f"{source}: {len(articles[:limit])}건 (최근 {MAX_AGE_DAYS}일, JSON)")
    return articles[:limit]


if __name__ == "__main__":
    # 점검용: 등록된 게시판을 한 번씩 읽어 글 수와 제목 표본을 보인다 (저장·AI 판정 없음, 요청 사이 1초)
    import sys
    import time

    import board_sources
    import tls_compat

    tls_compat.install_ca_bundle()
    logging.basicConfig(level=logging.WARNING)
    key = sys.argv[1] if len(sys.argv) > 1 else ""
    hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
    for name, region, urls in board_sources.ALL_BOARDS:
        if key not in name:
            continue
        got = scrape_board(urls, name, hdr, labels=board_sources.BOARD_LABELS.get(name))
        srcs = sorted({g["source"] for g in got}) if board_sources.BOARD_LABELS.get(name) else []
        print(f"{region:<16} {name:<20} {len(got):>2}건 | {got[0]['title'][:40] if got else '-'} {srcs or ''}", flush=True)
        time.sleep(1)
    for name, region, cfg in board_sources.JSON_BOARDS:
        if key not in name:
            continue
        got = scrape_json_board(cfg, name, hdr)
        print(f"{region:<16} {name:<20} {len(got):>2}건 | {got[0]['title'][:40] if got else '-'} (본문 {len(got[0]['content']) if got else 0}자)", flush=True)
