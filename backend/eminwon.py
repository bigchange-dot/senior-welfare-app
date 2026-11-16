"""
새올행정시스템(eminwon) 고시공고 공통 파서 (2026-11-16)

행정안전부 표준 새올 시스템을 쓰는 시·군·구는 목록·상세 주소 형식이 같아서 파서 하나 + 도메인 목록으로 수집한다.
시·군 설정: docs/gyeonggi/gyeonggi_sources.yaml (eminwon_base, tls, sub_districts). 점검: docs/gyeonggi/probe_eminwon.py

⚠️ 아직 파이프라인(scraping_function._run_pipeline)에 연결하지 않았다. 경기 공고를 저장하면 앱의 'all' 구독자(서울)에게
   알림이 가므로, 앱에 경기 지역·필터·FCM 토픽을 먼저 넣은 뒤 연결한다. 지금은 아래 dry-run으로 양만 잰다.

    cd backend && venv/bin/python eminwon.py ../docs/gyeonggi/gyeonggi_sources.yaml

목록 페이지 구조 (2026-11-16, 경기 30개 시·군 확인)
- 모든 행에 searchDetail('공고관리번호')가 있다 (a href / a onclick / td onclick 중 한 곳)
- tbody 유무·칸 수(5~11개)가 시·군마다 달라 칸은 머리글(th) 이름으로 찾는다
- 상세는 폼 POST지만 같은 값을 GET으로 보내도 열린다 → DETAIL_PATH를 저장 URL(문서 ID)과 앱 링크로 쓴다
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

import tls_compat

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

LIST_PATH = (
    "/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
    "?jndinm=OfrNotAncmtEJB&context=NTIS&method=selectListOfrNotAncmt"
    "&methodnm=selectListOfrNotAncmtHomepage&homepage_pbs_yn=Y&subCheck=Y"
    "&ofr_pageSize={size}&not_ancmt_se_code={codes}&initValue=Y&countYn=Y&epcCheck=Y"
)
DETAIL_PATH = (
    "/emwp/gov/mogaha/ntis/web/ofr/action/OfrAction.do"
    "?jndinm=OfrNotAncmtEJB&context=NTIS&method=selectOfrNotAncmt&methodnm=selectOfrNotAncmtRegst"
    "&not_ancmt_mgt_no={id}&homepage_pbs_yn=Y&subCheck=Y"
)

DETAIL_RE    = re.compile(r"searchDetail\(\s*'(\d+)'")
NOTICE_NO_RE = re.compile(r"(?:공고|고시)\s*제\s*\d{4}\s*-\s*\d+\s*호")
DATE_RE      = re.compile(r"\d{4}-\d{2}-\d{2}")


def base_url(city: dict, defaults: dict) -> str:
    return city.get("eminwon_base") or defaults["eminwon_base"].format(domain=city["domain"])


def make_session(city: dict, base: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    if city.get("tls") == "legacy":
        session.mount(base, tls_compat.LegacyTLSAdapter())
    return session


def _header_names(table) -> list[str]:
    """표의 머리글 이름 목록 (첫 th 행). 없으면 빈 목록."""
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if ths:
            return [re.sub(r"\s+", "", th.get_text(strip=True)) for th in ths]
    return []


def _pick(cells: dict[str, str], *names: str) -> str:
    for key, value in cells.items():
        if any(n in key for n in names):
            return value
    return ""


def parse_list(html: str) -> list[dict]:
    """목록 HTML → [{id, title, notice_no, dept, date}]. 칸은 머리글 이름으로, 안 맞으면 내용 모양으로 찾는다."""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for tr in soup.find_all("tr"):
        if tr.find("tr"):
            continue
        m = DETAIL_RE.search(str(tr))
        if not m:
            continue
        tds = tr.find_all("td")
        texts = [td.get_text(" ", strip=True) for td in tds]
        table = tr.find_parent("table")
        header = _header_names(table) if table else []

        if header and len(header) == len(texts):
            cells = dict(zip(header, texts))
            title     = _pick(cells, "제목")
            notice_no = _pick(cells, "고시공고번호", "공고번호")
            dept      = _pick(cells, "담당부서", "부서")
            date      = _pick(cells, "등록일", "게시일", "작성일")
        else:
            title = notice_no = dept = date = ""
        # 머리글이 안 맞거나 비면 내용 모양으로 보완
        if not title:
            link_cell = next((td for td in tds if DETAIL_RE.search(str(td))), None)
            title = link_cell.get_text(" ", strip=True) if link_cell else max(texts, key=len, default="")
        if not notice_no:
            notice_no = next((t for t in texts if NOTICE_NO_RE.search(t) and t != title), "")
        if not date:
            date = next((DATE_RE.search(t).group(0) for t in texts if DATE_RE.search(t)), "")
        title = NOTICE_NO_RE.split(title)[-1].strip() if NOTICE_NO_RE.search(title) else title
        rows.append({"id": m.group(1), "title": re.sub(r"\s+", " ", title).strip(),
                     "notice_no": notice_no, "dept": dept, "date": date[:10]})
    return rows


def sub_district(notice_no: str, city: dict) -> str:
    """'수원시 팔달구 공고 제2026-1호' → '팔달구'. 없으면 빈 문자열."""
    return next((sd for sd in city.get("sub_districts", []) if sd in notice_no), "")


def fetch_city(city: dict, defaults: dict, page_size: int | None = None) -> list[dict]:
    """시·군 1곳의 새올 목록 → 파이프라인 기사 형식 [{title, url, source, content, ...}]. 실패하면 예외."""
    base = base_url(city, defaults)
    codes = "%2C".join(defaults.get("se_codes", ["04", "05"]))
    url = base + LIST_PATH.format(size=page_size or defaults.get("page_size", 30), codes=codes)
    session = make_session(city, base)
    for attempt in range(2):   # 화성처럼 가끔 400이 한 번 나는 곳이 있어 1회 재시도
        res = session.get(url, timeout=15)
        if res.status_code == 200:
            break
        time.sleep(2)
    res.raise_for_status()
    res.encoding = res.apparent_encoding or "utf-8"   # 새올은 EUC-KR 페이지가 섞여 있음
    articles = []
    for row in parse_list(res.text):
        articles.append({
            "title":        row["title"],
            "url":          base + DETAIL_PATH.format(id=row["id"]),
            "source":       city["name"],
            "content":      "",
            "sub_district": sub_district(row["notice_no"], city),
            "dept":         row["dept"],
            "date":         row["date"],
        })
    return articles


_TRUNCATED_RE = re.compile(r"(\.\.\.|…)\s*$")


def is_truncated(title: str) -> bool:
    return bool(_TRUNCATED_RE.search(title))


def fetch_full_title(session: requests.Session, detail_url: str) -> str:
    """목록에서 '…'로 잘린 제목을 상세 페이지에서 가져온다. 못 찾으면 빈 문자열.

    목록 제목이 잘리면 끝의 "채용" 같은 단어가 빠져 규칙 필터를 비껴간다 (경기 실측 2026-11-16).
    키워드 필터를 통과한 후보에만 부르므로 요청 수는 거의 늘지 않는다.
    """
    res = session.get(detail_url, timeout=15)
    res.raise_for_status()
    res.encoding = res.apparent_encoding or "utf-8"
    soup = BeautifulSoup(res.text, "lxml")
    for label in soup.find_all(["th", "td", "dt", "span", "strong", "label"]):
        if re.sub(r"[\s:：]+", "", label.get_text()) == "제목":
            value = label.find_next_sibling(["td", "dd", "span", "div"])
            if value and value.get_text(strip=True):
                return re.sub(r"\s+", " ", value.get_text(" ", strip=True))
    return ""


def load_config(path: str) -> dict:
    import yaml  # 설정을 읽을 때만 필요
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
# dry-run: 시·군별로 받아 규칙·키워드 필터 뒤 AI까지 가는 양을 잰다 (저장·AI 호출 없음)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    from collections import Counter

    import llm_judge

    tls_compat.install_ca_bundle()
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "../docs/gyeonggi/gyeonggi_sources.yaml")
    total = Counter()
    candidates = []
    for city in cfg["cities"]:
        if city.get("eminwon") == "none":
            print(f"{city['name']:<6} (새올 없음 — 홈페이지 목록 폴백 대상)")
            continue
        try:
            arts = fetch_city(city, cfg["defaults"])
        except Exception as e:
            print(f"{city['name']:<6} 실패: {type(e).__name__}: {str(e)[:80]}")
            continue
        c = Counter()
        session = make_session(city, base_url(city, cfg["defaults"]))
        for a in arts:
            # 잘린 제목은 키워드 후보일 때만 상세에서 전체 제목을 받아 다시 판정
            if is_truncated(a["title"]) and llm_judge.has_senior_keyword(a["title"]):
                full = fetch_full_title(session, a["url"])
                c["제목보완"] += bool(full)
                a["title"] = full or a["title"]
                time.sleep(0.5)
            if llm_judge.rule_skip_reason(a["title"]):
                c["규칙"] += 1
            elif not llm_judge.has_senior_keyword(a["title"]):
                c["키워드없음"] += 1
            else:
                c["AI로"] += 1
                candidates.append((city["name"], a["sub_district"], a["date"], a["title"]))
        total.update(c)
        total["수집"] += len(arts)
        dates = sorted(a["date"] for a in arts if a["date"])
        span = f"{dates[0]}~{dates[-1]}" if dates else "-"
        print(f"{city['name']:<6} {len(arts):>2}건 ({span}) 규칙 {c['규칙']:>2} · 키워드없음 {c['키워드없음']:>2} · AI로 {c['AI로']:>2}")
        time.sleep(1)
    print(f"\n합계: {dict(total)}")
    print("\nAI까지 가는 공고:")
    for name, sd, date, title in candidates:
        print(f"  {name} {sd:<4} {date} | {title[:60]}")
