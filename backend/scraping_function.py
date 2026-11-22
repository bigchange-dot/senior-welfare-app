"""
Track A: 데이터 수집 및 AI 가공 (ARCHITECTURE.md 3.2)
- 복지로 공공데이터 API
- 서울 구청 게시판 13곳 + 성동구청 채용, 노인복지관 7곳 스크래핑
- AI 판정·요약 (llm_judge.py — 규칙 필터, Ollama/Gemini)
- Firestore 저장 (중복 방지) + 실행 기록 (monitoring.py)
- 실행: 맥 launchd가 이 파일을 직접 실행 (`__main__`), Cloud Functions HTTP 트리거는 비공개·일시정지
"""

import os
import time
import hashlib
import logging
import concurrent.futures
from datetime import datetime, timezone

import re
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import firestore
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# 설정 & 초기화
# ─────────────────────────────────────────────
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

DATA_GO_KR_KEY      = os.getenv("DATA_GO_KR_KEY", "").strip()
FIREBASE_COLLECTION = "welfare_notices"
SKIPPED_COLLECTION  = "skipped_notices"   # AI가 SKIP 판정한 URL 캐시 (재호출 방지)
BOKJIRO_MAX_NEW_PER_RUN = 2               # 복지로 신규 저장 상한 (알림 폭주 방지)
# 1이면 알림 없이 저장 (is_notified=True로 저장 → notification_function이 건너뜀).
# 장애 뒤 밀린 공고를 한꺼번에 처리할 때 알림 폭주를 막는 용도
SILENT_SAVE = os.getenv("SILENT_SAVE", "") == "1"
# 경기 출처 수집 (v1.5). 앱 v1.5 출시 전에 켜면 지역을 못 고르는 v1.4 사용자에게 경기 공고 알림이 간다
GYEONGGI = os.getenv("GYEONGGI", "") == "1"

from log_config import configure_logging
from monitoring import ErrorCollector, record_pipeline_run
import board_parser
import board_sources
import llm_judge
import sources
import tls_compat
configure_logging()
tls_compat.install_ca_bundle()   # 중간 인증서 누락 사이트(중구청·성동구청 등) 검증용 번들
logger = logging.getLogger(__name__)

# Firebase Admin 초기화 (이미 초기화된 경우 재사용)
if not firebase_admin._apps:
    firebase_admin.initialize_app()

# 공통 HTTP 헤더 (봇 탐지 최소화)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# ─────────────────────────────────────────────
# 지연 초기화 (Lazy Init) — 배포 타임아웃 방지
# Firestore 클라이언트는 첫 호출 시 생성 (Gemini 클라이언트는 llm_judge.py)
# ─────────────────────────────────────────────
_db = None


def _get_db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db


# Firestore 호출 재시도 (2026-11-22)
# 경기 첫 수집(11-21 18시)이 AI 판정으로 길어진 사이 맥이 잠들었다 깨면서 연결이 끊겨, 쓰기 한 번이
# 504 Deadline Exceeded로 실패하고 회차 전체가 중단됐다. 잠깐 쉬었다 다시 하면 되는 오류라 몇 번 더 해 본다.
_FIRESTORE_RETRY_WAITS = (5, 20, 60)   # 초


def _firestore_retry(call, what: str):
    """call()을 실행하고, Google API 오류면 기다렸다 다시 한다. 끝까지 안 되면 마지막 오류를 그대로 올린다."""
    from google.api_core import exceptions as gexc
    for wait in _FIRESTORE_RETRY_WAITS:
        try:
            return call()
        except (gexc.GoogleAPICallError, gexc.RetryError) as e:
            logger.warning(f"⚠️ Firestore {what} 실패 — {wait}초 뒤 재시도: {type(e).__name__}")
            time.sleep(wait)
    return call()


# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────
def make_doc_id(url: str) -> str:
    """URL의 SHA-256 해시를 Document ID로 사용 (중복 방지)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def is_duplicate(url: str) -> bool:
    """Firestore에 해당 URL 문서가 이미 존재하는지 확인."""
    doc_id = make_doc_id(url)
    doc = _firestore_retry(lambda: _get_db().collection(FIREBASE_COLLECTION).document(doc_id).get(), "중복 확인")
    return doc.exists


def is_skipped(url: str) -> bool:
    """이전 실행에서 Gemini가 SKIP 판정한 URL인지 확인 (재호출 방지)."""
    doc = _firestore_retry(lambda: _get_db().collection(SKIPPED_COLLECTION).document(make_doc_id(url)).get(), "SKIP 확인")
    return doc.exists


def mark_skipped(title: str, source: str, url: str) -> None:
    """SKIP 판정 URL을 캐시에 기록. 매 실행마다 같은 공고를 Gemini에 다시 보내지 않도록."""
    data = {
        "title":     title,
        "source":    source,
        "url":       url,
        "timestamp": datetime.now(timezone.utc),
    }
    _firestore_retry(lambda: _get_db().collection(SKIPPED_COLLECTION).document(make_doc_id(url)).set(data), "SKIP 기록")


def save_to_firestore(title: str, ai_summary: str, source: str, url: str, silent: bool = False) -> str:
    """유효한 공고를 Firestore에 저장하고 Document ID를 반환.

    region·province(v1.5): 앱은 출처 이름 목록 대신 이 지역 코드로 공고를 찾는다 (sources.py)."""
    doc_id  = make_doc_id(url)
    doc_ref = _get_db().collection(FIREBASE_COLLECTION).document(doc_id)
    region  = sources.region_of(source)
    if region is None:
        logger.warning(f"⚠️ 등록표에 없는 출처 — 지역 없이 저장: {source} (sources.py에 추가할 것)")
    _firestore_retry(lambda: doc_ref.set({
        "title":       title,
        "ai_summary":  ai_summary,
        "source":      source,
        "region":      region or "",
        "province":    sources.province_of(region) or "",
        "url":         url,
        "timestamp":   datetime.now(timezone.utc),
        "is_notified": SILENT_SAVE or silent,   # True면 알림 함수가 발송을 건너뜀
    }), "공고 저장")
    logger.info(f"✅ 저장 완료{'(알림 없음)' if SILENT_SAVE or silent else ''}: [{source}] {ai_summary}")
    return doc_id


# ─────────────────────────────────────────────
# 상세 페이지 본문 추출 (AI 판정 입력)
# ─────────────────────────────────────────────
# 게시판 전용 본문 영역 — 찾으면 그대로 신뢰
_BOARD_BODY_SELECTORS = [
    "div.view_content", "div.bbs_content", "div.board_view",
    "div.cont_area", "div.view_txt", "td.view_con", "div.detail_content",
    "div.xe_content",   # XE/라이믹스 게시판 (도봉노인복지관 등)
]
# 범용 영역 — 다른 글 목록·메뉴가 섞일 수 있어 제목과 겹치는 단어가 있을 때만 사용
_GENERIC_BODY_SELECTORS = ["div#articleBody", "div.article_body", "div#article_body", "article", "div#content"]
# 본문 판단 전에 지우는 메뉴·머리말·꼬리말 영역
_NOISE_SELECTORS = (
    "script, style, noscript, nav, header, footer, aside, "   # form은 페이지 전체를 감싸는 사이트가 있어 제외
    "#header, #footer, .header, .footer, .gnb, .lnb, .snb, .location, .breadcrumb, .quick, .sidebar"
)
_TITLE_STOPWORDS = {"공고", "안내", "모집", "알림", "참여자", "신청", "개최", "운영", "실시", "2026년", "2027년"}


def _title_tokens(title: str) -> list[str]:
    words = re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
    return [w for w in words if w not in _TITLE_STOPWORDS]


def _overlaps_title(text: str, title: str) -> bool:
    tokens = _title_tokens(title)
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in text)
    return hits >= min(2, len(tokens))


def fetch_detail_content(url: str, source: str, title: str = "") -> str:
    """상세 페이지에서 본문 텍스트를 최대 llm_judge.CONTENT_CHARS자 추출. 확실하지 않으면 빈 문자열.

    2026-11-16 수정: 강북구청 언론보도처럼 외부 신문사로 연결되는 글에서 마지막 단계(<p> 합산)가
    그 페이지의 다른 기사 제목들을 긁어 와 엉뚱한 요약이 저장된 사례가 있었다
    ("강북구 신청사 기공식" → "구로구, 11개 의료기관과 퇴원환자 돌봄").
    범용 추출은 제목과 겹치는 단어가 있을 때만 쓰고, 아니면 본문 없이(제목만으로) 판정한다.
    """
    limit = llm_judge.CONTENT_CHARS
    try:
        if requests.utils.urlparse(url).netloc in board_parser.LEGACY_TLS_HOSTS:
            # 옛 암호화 사이트(수원시니어클럽)는 본문도 목록과 같은 방식으로 — 2026-11-22 첫 수집에서 본문만 실패했음
            res = board_parser._get(url, HEADERS)
        else:
            res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        # 응답 헤더에 charset이 없으면 requests가 ISO-8859-1로 읽어 한글이 깨짐 (은평노인복지관 등)
        if "charset" not in res.headers.get("content-type", "").lower():
            res.encoding = res.apparent_encoding or "utf-8"
        soup = BeautifulSoup(res.text, "lxml")
        for el in soup.select(_NOISE_SELECTORS):
            el.decompose()

        for selector in _BOARD_BODY_SELECTORS:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    return text[:limit]

        for selector in _GENERIC_BODY_SELECTORS:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 50 and _overlaps_title(text, title):
                    return text[:limit]

        paragraphs = " ".join(p.get_text(strip=True) for p in soup.select("p") if p.get_text(strip=True))
        if len(paragraphs) > 50 and _overlaps_title(paragraphs, title):
            return paragraphs[:limit]
        return ""
    except Exception as e:
        logger.warning(f"⚠️ 본문 fetch 실패 ({url[:40]}): {e}")
        return ""


# 복지관 출처 목록은 sources.py 등록표로 옮김 (v1.5, sources.is_center)


# ─────────────────────────────────────────────
# Track A-1: 복지로 공공데이터 API (중앙부처복지서비스)
# 엔드포인트: NationalWelfarelistV001
# 응답 필드: servNm(제목), servDtlLink(URL), servDgst(요약), lifeArray(생애주기)
# ─────────────────────────────────────────────
def fetch_bokjiro_api() -> list[dict]:
    endpoint = "https://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001"
    articles = []

    try:
        params = {
            "serviceKey": DATA_GO_KR_KEY,
            "callTp":     "L",
            "pageNo":     "1",
            "numOfRows":  "100",   # 노인 카테고리 전체(총 34건)를 한 번에 수신
            "srchKeyCode": "003",
            "searchWrd":  "노인",
        }
        res = requests.get(endpoint, params=params, headers=HEADERS, timeout=15)
        res.raise_for_status()

        soup  = BeautifulSoup(res.text, "lxml-xml")
        items = soup.find_all("servList")
        logger.info(f"📡 복지로 API: {len(items)}개 항목 수신")

        for item in items:
            def tag_text(tag_name: str) -> str:
                tag = item.find(tag_name)
                return tag.get_text(strip=True) if tag else ""

            title      = tag_text("servNm")
            detail_url = tag_text("servDtlLink")
            content    = tag_text("servDgst")

            if not title or not detail_url:
                continue

            articles.append({
                "title":   title,
                "url":     detail_url,
                "content": content,
                "source":  "복지로",
            })

    except Exception as e:
        # 예외 메시지에 요청 URL(serviceKey 포함)이 들어가므로 키를 마스킹
        err = str(e).replace(DATA_GO_KR_KEY, "***") if DATA_GO_KR_KEY else str(e)
        logger.error(f"❌ 복지로 API 오류: {err}")

    return articles


# ─────────────────────────────────────────────
# Track A-2: 성동구청 채용공고
# ─────────────────────────────────────────────
def scrape_seongdong_jobs() -> list[dict]:
    url      = "https://www.sd.go.kr/main/selectBbsNttList.do?bbsNo=185&key=1474&"
    articles = []

    try:
        res  = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        rows = soup.select("table.board_list tbody tr, ul.bbs_list li, div.bbs_list dl")
        if not rows:
            rows = soup.select("table tbody tr")

        logger.info(f"🏢 성동구청 채용: {len(rows)}개 행 발견")

        for row in rows[:15]:
            try:
                link_tag = row.select_one("td.subject a, td a.nttInfoBtn, a[href*='nttNo']")
                if not link_tag:
                    link_tag = row.select_one("a")
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")

                if href.startswith("/"):
                    detail_url = "https://www.sd.go.kr" + href
                elif href.startswith("./"):
                    detail_url = "https://www.sd.go.kr/main/" + href[2:]
                elif href.startswith("?"):
                    detail_url = "https://www.sd.go.kr/main/selectBbsNttList.do" + href
                elif href.startswith("http"):
                    detail_url = href
                elif not href or href.startswith("javascript:"):
                    continue
                else:
                    continue

                if title:
                    articles.append({"title": title, "url": detail_url, "content": "", "source": "성동구청"})
            except Exception as e:
                logger.warning(f"⚠️ 성동구청 행 파싱 오류: {e}")

    except Exception as e:
        logger.error(f"❌ 성동구청 채용 스크래핑 오류: {e}")

    return articles


# ─────────────────────────────────────────────
# 서울 구청 공통 스크래퍼 (SAB 없는 일반 구청)
# ─────────────────────────────────────────────
def _scrape_seoul_board(url: str, label: str, base_domain: str, limit: int = 15) -> list[dict]:
    """서울 구청 표준 게시판 공통 스크래핑 (봇 감지 없는 일반 사이트용)."""
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        # 일반적인 한국 구청 게시판 셀렉터 패턴
        rows = soup.select(
            "table.board_list tbody tr, table.bbs_list tbody tr, "
            "table.list_type tbody tr, table tbody tr"
        )
        logger.info(f"{label}: {len(rows)}개 행 발견")

        for row in rows[:limit]:
            try:
                link_tag = row.select_one("td.subject a, td.title a, td.tit a, td a")
                if not link_tag:
                    continue
                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")
                if not title or href.startswith("javascript:"):
                    continue
                if href.startswith("/"):
                    detail_url = base_domain + href
                elif href.startswith("http"):
                    detail_url = href
                elif href.startswith("?"):
                    detail_url = url.split("?")[0] + href
                elif href.startswith("./"):
                    # 상대경로: ./foo.do → 현재 경로 기준으로 변환
                    base_path = url.rsplit("/", 1)[0]
                    detail_url = base_path + "/" + href[2:]
                else:
                    continue
                articles.append({"title": title, "url": detail_url, "content": "", "source": label.split()[-1]})
            except Exception as e:
                logger.warning(f"⚠️ {label} 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ {label} 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# G5 BBS 공통 스크래퍼 (노인복지관 사이트용)
# 그누보드5(G5) 기반 게시판 표준 구조 처리
# ─────────────────────────────────────────────
def _scrape_g5_board(url: str, label: str, base_domain: str, limit: int = 15, verify_ssl: bool = True) -> list[dict]:
    """G5 BBS 표준 게시판 스크래핑 (노인복지관 사이트 공통).

    verify_ssl=False: 대상 서버 인증서 만료 등으로 검증 불가한 경우 사용
    (예: 종로노인복지관 — 2026-04 기준 SSL 인증서 만료 상태)."""
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15, verify=verify_ssl)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        rows = soup.select("table tbody tr")
        logger.info(f"{label}: {len(rows)}개 행 발견")

        for row in rows[:limit]:
            try:
                # 게시글 링크 선택 — G5 보드는 td.td_subject 내부에 카테고리 링크(a.bo_cate_link)와
                # 실제 글 링크가 공존하므로 wr_id 포함 링크를 우선 선택해야 함.
                # 콤마 셀렉터는 문서 순서로 첫 매치를 반환해 카테고리 링크가 잡히는 문제가 있음.
                link_tag = (
                    row.select_one('a[href*="wr_id="]')
                    or row.select_one('a.bo_tit')
                    or row.select_one('td.td_subject a:not(.bo_cate_link)')
                    or row.select_one('td.subject a')
                    or row.select_one('td a')
                )
                if not link_tag:
                    continue
                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")
                if not title or href.startswith("javascript:"):
                    continue
                if href.startswith("/"):
                    detail_url = base_domain + href
                elif href.startswith("http"):
                    detail_url = href
                elif href.startswith("?"):
                    detail_url = url.split("?")[0] + href
                else:
                    continue
                articles.append({"title": title, "url": detail_url, "content": "", "source": label})
            except Exception as e:
                logger.warning(f"⚠️ {label} 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ {label} 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# Track A-7: 노원구청 채용 공고 + 공지사항
# 도메인: nowon.kr (nowon.go.kr 아님 — SSL 불일치)
# 링크 형식: javascript:opView('ID') → 상세 URL 직접 생성
# 확인: 2026-05-06 — q_bbsCode=1003(채용)은 어르신 매치 0/10 → 1001(공지) 추가
# ─────────────────────────────────────────────
def _scrape_nowon_board(bbs_code: str, label: str) -> list[dict]:
    """노원구청 게시판 공통 스크래핑.
    1003(채용)은 javascript:opView('id') 형식, 1001(공지)은 직접 href 형식.
    """
    url      = f"https://www.nowon.kr/www/user/bbs/BD_selectBbsList.do?q_bbsCode={bbs_code}"
    articles = []
    base     = "https://www.nowon.kr/www/user/bbs/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")
        rows = soup.select("table tbody tr")
        logger.info(f"{label}: {len(rows)}개 행 발견")
        for row in rows[:15]:
            try:
                link_tag = row.select_one("td a")
                if not link_tag:
                    continue
                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")
                if not title:
                    continue
                # 1) javascript:opView('id') 패턴
                m = re.search(r"opView\('([^']+)'", href)
                if m:
                    detail_url = f"https://www.nowon.kr/www/user/bbs/BD_selectBbsDetail.do?q_bbsCode={bbs_code}&q_bbscttSn={m.group(1)}"
                # 2) 직접 BD_selectBbs.do?... 상대경로 (공지사항)
                elif href.startswith("BD_selectBbs"):
                    detail_url = base + href
                elif href.startswith("/"):
                    detail_url = "https://www.nowon.kr" + href
                else:
                    continue
                articles.append({"title": title, "url": detail_url, "content": "", "source": "노원구청"})
            except Exception as e:
                logger.warning(f"⚠️ {label} 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ {label} 스크래핑 오류: {e}")
    return articles


def scrape_nowon() -> list[dict]:
    # 1003=채용공고, 1001=공지사항 (어르신 관련 공고 다양)
    return _scrape_nowon_board("1003", "🏢 노원구청 채용") + \
           _scrape_nowon_board("1001", "🏢 노원구청 공지")


# ─────────────────────────────────────────────
# Track A-8: 도봉구청 공지사항 + 행사/모집 (어르신 전용 게시판 없음)
# code=10008769 공지사항, code=10008770 행사/모집
# 링크 형식: ./bbs.asp?bmode=D&... (상대경로, 직접 URL)
# 확인: 2026-05-06 — 공지사항만으론 어르신 키워드 매치 1/10 → 두 게시판 통합
# ─────────────────────────────────────────────
def scrape_dobong() -> list[dict]:
    articles = _scrape_seoul_board(
        "https://www.dobong.go.kr/bbs.asp?code=10008769",
        "🏢 도봉구청 공지", "https://www.dobong.go.kr", limit=15
    )
    articles += _scrape_seoul_board(
        "https://www.dobong.go.kr/bbs.asp?code=10008770",
        "🏢 도봉구청 행사모집", "https://www.dobong.go.kr", limit=15
    )
    # source 통일 (label.split()[-1] 결과를 덮어씀)
    for a in articles:
        a["source"] = "도봉구청"
    return articles


# ─────────────────────────────────────────────
# Track A-9: 중랑구청 채용 공고
# 확인: 2026-03-12 ⚠️ WebFetch 파싱 오류 — Python requests는 정상 작동 가능
# ─────────────────────────────────────────────
def scrape_jungnang() -> list[dict]:
    return _scrape_seoul_board(
        "https://www.jungnang.go.kr/portal/bbs/list/B0000118.do?menuNo=200476",
        "🏢 중랑구청", "https://www.jungnang.go.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-10: 마포구청 채용 공고
# 확인: 2026-03-12 ✅ 게시판 정상 (채용공고 다수 확인)
# ─────────────────────────────────────────────
def scrape_mapo() -> list[dict]:
    return _scrape_seoul_board(
        "https://www.mapo.go.kr/site/main/nPortalr/lists",
        "🏢 마포구청", "https://www.mapo.go.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-11: 은평구청 공지사항 + 보도자료
# 도메인: ep.go.kr (http:// — https:// 타임아웃 발생)
# 링크 형식: ./selectBbsNttView.do?... (상대경로, 직접 URL)
# 확인: 2026-05-06 — 채용 게시판(bbsNo=46)은 직원 채용만 올라와 Gemini 100% SKIP
#       → 공지사항(bbsNo=42) + 보도자료(bbsNo=48) 통합
# ─────────────────────────────────────────────
def scrape_eunpyeong() -> list[dict]:
    articles = _scrape_seoul_board(
        "http://www.ep.go.kr/www/selectBbsNttList.do?bbsNo=42&key=744",
        "🏢 은평구청 공지", "http://www.ep.go.kr", limit=15
    )
    articles += _scrape_seoul_board(
        "http://www.ep.go.kr/www/selectBbsNttList.do?bbsNo=48&key=762",
        "🏢 은평구청 보도", "http://www.ep.go.kr", limit=15
    )
    for a in articles:
        a["source"] = "은평구청"
    return articles


# ─────────────────────────────────────────────
# Track A-11b: 종로구청 채용공고
# 도메인: www.jongno.go.kr
# 특이사항: 링크가 `javascript:viewMove('nttId')` 형식 →
#   상세 URL을 /portal/bbs/selectBoardArticle.do?bbsId=...&menuNo=...&menuId=...&nttId=... 로 조합
# 확인: 2026-04-09 ✅ 10행 수집
# ─────────────────────────────────────────────
def scrape_jongno() -> list[dict]:
    import re as _re
    BBS_ID = "BBSMSTR_000000000026"
    MENU_NO = "400510"
    list_url = f"https://www.jongno.go.kr/portal/bbs/selectBoardList.do?bbsId={BBS_ID}&menuId={MENU_NO}&menuNo={MENU_NO}"
    label = "🏢 종로구청"
    articles = []
    try:
        res = requests.get(list_url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")
        rows = soup.select("table tbody tr")
        logger.info(f"{label}: {len(rows)}개 행 발견")
        for row in rows[:15]:
            try:
                link_tag = row.select_one("td.subject a, td.title a, td a")
                if not link_tag:
                    continue
                title = link_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                # viewMove('253705') → nttId 추출
                m = _re.search(r"viewMove\(\s*'(\d+)'\s*\)", href)
                if not (title and m):
                    continue
                ntt_id = m.group(1)
                detail_url = (
                    f"https://www.jongno.go.kr/portal/bbs/selectBoardArticle.do?"
                    f"bbsId={BBS_ID}&menuNo={MENU_NO}&menuId={MENU_NO}&nttId={ntt_id}"
                )
                articles.append({"title": title, "url": detail_url, "content": "", "source": "종로구청"})
            except Exception as e:
                logger.warning(f"⚠️ {label} 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ {label} 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# Track A-11c: 중구청 모집공고
# URL: https://www.junggu.seoul.kr/content.do?cmsid=15450
# 링크 형식: /content.do?cmsid=15450&mode=view&cid=... (상대경로)
# 확인: 2026-04-09 ✅ 11행 수집
# ─────────────────────────────────────────────
def scrape_junggu() -> list[dict]:
    return _scrape_seoul_board(
        "https://www.junggu.seoul.kr/content.do?cmsid=15450",
        "🏢 중구청", "https://www.junggu.seoul.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-11d: 용산구청 고시공고 (채용·공사 등 통합 공고 게시판)
# URL: https://yongsan.go.kr/portal/bbs/B0000095/list.do?menuNo=200233
# 링크 형식: /portal/bbs/B0000095/view.do?nttId=...&menuNo=200233 (상대경로)
# 확인: 2026-04-09 ✅ 10행 수집
# ─────────────────────────────────────────────
def scrape_yongsan() -> list[dict]:
    return _scrape_seoul_board(
        "https://yongsan.go.kr/portal/bbs/B0000095/list.do?menuNo=200233",
        "🏢 용산구청", "https://yongsan.go.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-11e: 서대문구청 채용공고
# URL: https://www.sdm.go.kr/genre/economic/jobinfo/jobs.do
# 특이사항: 링크가 `javascript:goView('sdmBoardSeq')` → goView는 form에
#   sdmBoardSeq / mode=view 세팅 후 현재 페이지로 submit. 상세 URL 패턴:
#   {list_url}?mode=view&sdmBoardSeq={seq}
# 확인: 2026-04-09 ✅ 10행 수집
# ─────────────────────────────────────────────
def scrape_seodaemun() -> list[dict]:
    import re as _re
    list_url = "https://www.sdm.go.kr/genre/economic/jobinfo/jobs.do"
    label = "🏢 서대문구청"
    articles = []
    try:
        res = requests.get(list_url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        # 서대문구청은 EUC-KR 인코딩 — utf-8 강제 시 mojibake 발생.
        # requests가 Content-Type 헤더(charset=EUC-KR)에서 자동 감지하므로 별도 설정 없음.
        soup = BeautifulSoup(res.text, "lxml")
        rows = soup.select("table tbody tr")
        logger.info(f"{label}: {len(rows)}개 행 발견")
        for row in rows[:15]:
            try:
                link_tag = row.select_one("td.subject a, td.title a, td a")
                if not link_tag:
                    continue
                title = link_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                m = _re.search(r"goView\(\s*'(\d+)'\s*\)", href)
                if not (title and m):
                    continue
                detail_url = f"{list_url}?mode=view&sdmBoardSeq={m.group(1)}"
                articles.append({"title": title, "url": detail_url, "content": "", "source": "서대문구청"})
            except Exception as e:
                logger.warning(f"⚠️ {label} 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ {label} 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# Track A-11i: 양천구청 공지사항
# URL: https://www.yangcheon.go.kr/site/yangcheon/ex/bbs/List.do?cbIdx=254
# 링크 형식: 관악과 동일한 doBbsFView() — 다만 상세 경로는 ex/bbs/View.do
# 제목 특이사항: <script>document.write(wdigm_title('제목'))</script> 동적 렌더 →
#   정적 파싱은 빈 텍스트 → 정규식으로 wdigm_title 인자 추출
# 확인: 2026-05-06 ✅
# ─────────────────────────────────────────────
def scrape_yangcheon() -> list[dict]:
    list_url = "https://www.yangcheon.go.kr/site/yangcheon/ex/bbs/List.do?cbIdx=254"
    label    = "🏢 양천구청"
    articles = []
    try:
        res = requests.get(list_url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")
        rows = soup.select("table tbody tr")
        logger.info(f"{label}: {len(rows)}개 행 발견")
        for row in rows[:15]:
            try:
                a = row.select_one("td.subject a, td.title a")
                if not a:
                    continue
                onclick = a.get("onclick", "")
                m_id    = re.search(r"doBbsFView\(\s*'(\d+)'\s*,\s*'(\d+)'", onclick)
                # 제목은 <script>document.write(wdigm_title('...'))</script> 안
                m_title = re.search(r"wdigm_title\(\s*'([^']+)'", str(a))
                if not (m_id and m_title):
                    continue
                cb_idx, bc_idx = m_id.group(1), m_id.group(2)
                title = m_title.group(1).strip()
                detail_url = f"https://www.yangcheon.go.kr/site/yangcheon/ex/bbs/View.do?cbIdx={cb_idx}&bcIdx={bc_idx}"
                articles.append({"title": title, "url": detail_url, "content": "", "source": "양천구청"})
            except Exception as e:
                logger.warning(f"⚠️ {label} 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ {label} 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# Track A-12: 구립수락노인종합복지관 (노원구)
# URL: https://suraknoin.or.kr/bbs/board.php?bo_table=0201
# 확인: G5 BBS 표준 구조
# ─────────────────────────────────────────────
def scrape_surak_welfare() -> list[dict]:
    return _scrape_g5_board(
        "https://suraknoin.or.kr/bbs/board.php?bo_table=0201",
        "수락노인복지관", "https://suraknoin.or.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-15c: 약수노인종합복지관 (중구)
# URL: http://www.yssenior.co.kr/bbs/board.php?bo_table=notice
# 구조: G5 BBS 표준
# ─────────────────────────────────────────────
def scrape_yaksu_welfare() -> list[dict]:
    return _scrape_g5_board(
        "http://www.yssenior.co.kr/bbs/board.php?bo_table=notice",
        "약수노인복지관", "http://www.yssenior.co.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-15d: 시립용산노인종합복지관 (용산구)
# URL: https://www.ysnoin.or.kr/bbs/board.php?bo_table=0101
# 구조: G5 BBS 표준
# ─────────────────────────────────────────────
def scrape_yongsan_welfare() -> list[dict]:
    return _scrape_g5_board(
        "https://www.ysnoin.or.kr/bbs/board.php?bo_table=0101",
        "용산노인복지관", "https://www.ysnoin.or.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-15e: 서대문노인종합복지관 (서대문구)
# URL: http://www.sdmsenior.or.kr/main/sub.html?boardID=www44&page=1
# 구조: 은평노인복지관(ep-silver.org)과 동일한 anyboard/Mode=view 시스템
# ─────────────────────────────────────────────
def scrape_seodaemun_welfare() -> list[dict]:
    url      = "http://www.sdmsenior.or.kr/main/sub.html?boardID=www44&page=1"
    base     = "http://www.sdmsenior.or.kr"
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, "lxml")

        links = soup.select("a[href*='Mode=view']")
        logger.info(f"서대문노인복지관: {len(links)}개 링크 발견")

        seen = set()
        for link_tag in links:
            try:
                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")
                # num={id} 기준으로 중복 링크(같은 글의 제목·본문 anchor) 제거
                import re as _re
                num_m = _re.search(r"num=(\d+)", href)
                if not (title and href and num_m):
                    continue
                key = num_m.group(1)
                if key in seen:
                    continue
                seen.add(key)
                if href.startswith("/"):
                    detail_url = base + href
                elif href.startswith("http"):
                    detail_url = href
                else:
                    continue
                articles.append({"title": title, "url": detail_url, "content": "", "source": "서대문노인복지관"})
                if len(articles) >= 15:
                    break
            except Exception as e:
                logger.warning(f"⚠️ 서대문노인복지관 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ 서대문노인복지관 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# Track A-15b: 종로노인종합복지관 (종로구)
# URL: https://jongnonoin.or.kr/bbs/board.php?bo_table=050101
# 구조: G5 BBS 표준
# 특이사항: SSL 인증서 만료(2026-04 기준) → verify_ssl=False 필요
# ─────────────────────────────────────────────
def scrape_jongno_welfare() -> list[dict]:
    return _scrape_g5_board(
        "https://jongnonoin.or.kr/bbs/board.php?bo_table=050101",
        "종로노인복지관", "https://jongnonoin.or.kr", limit=15, verify_ssl=False
    )


# ─────────────────────────────────────────────
# Track A-17: 도봉노인종합복지관 (도봉구)
# URL: https://dobongnoin.or.kr/news (복지관소식 — 어르신 프로그램 모집/안내)
# 참고: /notice는 회계공시·납품업체 선정 등 행정 공고 전용 → Gemini가 100% SKIP
#       /news는 어르신 대상 강좌·상담·행사 모집 공고가 올라오는 게시판
# 확인: 2026-05-06 ✅ 커스텀 라우팅 (테이블 구조)
# ─────────────────────────────────────────────
def scrape_dobong_welfare() -> list[dict]:
    url      = "https://dobongnoin.or.kr/news"
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        rows = soup.select("table tbody tr, ul.notice_list li, div.board_list dl")
        if not rows:
            rows = soup.select("table tbody tr")
        logger.info(f"도봉노인복지관: {len(rows)}개 행 발견")

        for row in rows[:15]:
            try:
                link_tag = row.select_one("td.subject a, td.title a, a.subject, td a, a")
                if not link_tag:
                    continue
                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")
                if not title or href.startswith("javascript:"):
                    continue
                if href.startswith("/"):
                    detail_url = "https://dobongnoin.or.kr" + href
                elif href.startswith("http"):
                    detail_url = href
                else:
                    continue
                articles.append({"title": title, "url": detail_url, "content": "", "source": "도봉노인복지관"})
            except Exception as e:
                logger.warning(f"⚠️ 도봉노인복지관 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ 도봉노인복지관 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# Track A-18: 시립은평노인종합복지관 (은평구)
# URL: https://www.ep-silver.org/main/sub.html?boardID=www39
# 확인: 커스텀 boardID 시스템
# ─────────────────────────────────────────────
def scrape_eunpyeong_welfare() -> list[dict]:
    # anyboard 시스템 — Mode=view 파라미터 링크 추출
    url      = "https://www.ep-silver.org/main/sub.html?boardID=www39&page=1"
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        res.encoding = 'utf-8'  # 인코딩 명시 (requests 자동 감지 오류 방지)
        soup = BeautifulSoup(res.text, "lxml")

        links = soup.select("a[href*='Mode=view']")
        logger.info(f"은평노인복지관: {len(links)}개 링크 발견")

        seen = set()
        for link_tag in links[:15]:
            try:
                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")
                if not title or not href or href in seen:
                    continue
                seen.add(href)
                if href.startswith("/"):
                    detail_url = "https://www.ep-silver.org" + href
                elif href.startswith("http"):
                    detail_url = href
                else:
                    continue
                articles.append({"title": title, "url": detail_url, "content": "", "source": "은평노인복지관"})
            except Exception as e:
                logger.warning(f"⚠️ 은평노인복지관 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ 은평노인복지관 스크래핑 오류: {e}")
    return articles


# ─────────────────────────────────────────────
# 게시판 출처 (범용 목록 파서, v1.5)
# ─────────────────────────────────────────────
def _board_scraper(name: str, urls: list[str]):
    """board_sources의 출처 하나 → 파이프라인 스크래퍼 함수 (실행 기록에 이름이 보이게 __name__ 지정)"""
    labels = board_sources.BOARD_LABELS.get(name)
    def run() -> list[dict]:
        return board_parser.scrape_board(urls, name, HEADERS, labels=labels)
    run.__name__ = f"board:{name}"
    return run


def _json_scraper(name: str, cfg: dict):
    def run() -> list[dict]:
        return board_parser.scrape_json_board(cfg, name, HEADERS)
    run.__name__ = f"board:{name}"
    return run


# 새 출처 첫 실행은 알림 없이 저장 — 출처를 붙인 날 그동안 밀린 공고가 한꺼번에 알림으로 나가지 않게 (v1.5)
WARMUP_DOC = ("system_status", "source_warmup")


def _load_warm_sources() -> set[str]:
    """한 번 이상 수집을 마친 출처 이름. 문서가 없으면 빈 집합 → 이번 실행은 전부 무음 (안전한 쪽)"""
    try:
        snap = _get_db().collection(WARMUP_DOC[0]).document(WARMUP_DOC[1]).get()
        return set((snap.to_dict() or {}).get("sources", [])) if snap.exists else set()
    except Exception as e:
        logger.warning(f"⚠️ 출처 warm-up 기록 읽기 실패 — 이번 실행은 전부 무음: {e}")
        return set()


def _save_warm_sources(names: set[str]) -> None:
    try:
        _get_db().collection(WARMUP_DOC[0]).document(WARMUP_DOC[1]).set({
            "sources": sorted(names), "updated_at": datetime.now(timezone.utc),
        })
    except Exception as e:
        logger.warning(f"⚠️ 출처 warm-up 기록 저장 실패: {e}")


# ─────────────────────────────────────────────
# 메인 파이프라인
# ─────────────────────────────────────────────
def run_scraping_pipeline(request=None):
    """수집 파이프라인을 실행하고, 성공·실패와 관계없이 실행 기록을 남긴다 (monitoring.py 참고)."""
    stats = {
        "started_at":    datetime.now(timezone.utc),
        "collected":     0,
        "saved":         0,
        "skipped":       0,
        "llm_calls":     0,
        "llm_errors":    0,   # AI 요약 실패로 보류한 건수 (다음 실행에 재시도)
        "llm_error":     "",
        "source_counts": {},  # 스크래퍼 함수명 → 수집 건수 (-1 = 예외로 실패)
        "fatal":         "",
    }
    llm_judge.state["last_error"] = ""
    collector = ErrorCollector()
    root_logger = logging.getLogger()
    root_logger.addHandler(collector)
    try:
        return _run_pipeline(stats)
    except Exception as e:
        stats["fatal"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        root_logger.removeHandler(collector)
        stats["finished_at"] = datetime.now(timezone.utc)
        stats["llm_error"]   = llm_judge.state["last_error"]
        stats["errors"]      = collector.summary()
        record_pipeline_run(_get_db, stats)


def _run_pipeline(stats: dict) -> str:
    logger.info("🚀 스크래핑 파이프라인 시작")

    # 제외한 출처의 스크래퍼는 2026-11-18 코드에서 삭제 (되살릴 때는 git 이력 742c192 이전 참고):
    #   강북구청 채용·보도자료·언론보도(구글 IP·맥 모두 연결 끊김), 성동노인종합복지관(구글 IP 403),
    #   마포노인복지관(봇 차단 403), 강북노인복지관(403), 신내노인복지관(SSL 오류), 노원노인복지관(게시판 없음)
    scrapers = [
        fetch_bokjiro_api,
        scrape_seongdong_jobs,
        scrape_nowon,
        scrape_dobong,
        scrape_jungnang,
        scrape_mapo,
        scrape_eunpyeong,
        scrape_jongno,           # 종로 ✅ (2026-04-09 추가)
        scrape_junggu,           # 중구 ✅ (2026-04-09 추가)
        scrape_yongsan,          # 용산 ✅ (2026-04-09 추가)
        scrape_seodaemun,        # 서대문 ✅ (2026-04-09 추가)
        # 강서·동작·관악구청은 6개월 저장 0건 → 2026-11-18 그 구의 복지관으로 교체 (아래 게시판 출처)
        scrape_yangcheon,        # 양천 ✅ (2026-05-06 추가, doBbsFView + wdigm_title)
        # 노인복지관 (7곳)
        scrape_surak_welfare,    # 노원 수락 ✅
        scrape_dobong_welfare,   # 도봉 ✅
        scrape_eunpyeong_welfare, # 은평 ✅
        scrape_jongno_welfare,   # 종로 ✅ (2026-04-09 추가, SSL 만료로 verify=False)
        scrape_yaksu_welfare,    # 중구 약수 ✅ (2026-04-09 추가)
        scrape_yongsan_welfare,  # 용산 ✅ (2026-04-09 추가)
        scrape_seodaemun_welfare, # 서대문 ✅ (2026-04-09 추가)
    ]
    # 범용 목록 파서로 읽는 게시판 (board_sources.py): 서울 교체분은 항상, 경기는 GYEONGGI=1일 때만
    boards = board_sources.SEOUL_BOARDS + (board_sources.GYEONGGI_BOARDS if GYEONGGI else [])
    scrapers += [_board_scraper(name, urls) for name, _region, urls in boards]
    if GYEONGGI:
        scrapers += [_json_scraper(name, cfg) for name, _region, cfg in board_sources.JSON_BOARDS]

    all_articles: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(scrapers), 32)) as executor:
        futures = {executor.submit(fn): fn.__name__ for fn in scrapers}
        for future in concurrent.futures.as_completed(futures):
            fn_name = futures[future]
            try:
                result = future.result()
                logger.info(f"  ↳ {fn_name}: {len(result)}건 수집")
                all_articles.extend(result)
                stats["source_counts"][fn_name] = len(result)
            except Exception as e:
                logger.error(f"  ↳ {fn_name} 실패: {e}")
                stats["source_counts"][fn_name] = -1

    logger.info(f"📦 총 수집 건수: {len(all_articles)}")
    stats["collected"] = len(all_articles)

    saved_count   = 0
    skipped_count = 0
    bokjiro_saved = 0   # 이번 실행에서 저장한 복지로 건수
    warm = _load_warm_sources()
    new_sources = {a.get("source", "") for a in all_articles} - warm
    if new_sources:
        logger.info(f"🆕 첫 수집 출처(이번엔 알림 없이 저장): {', '.join(sorted(new_sources))}")

    for article in all_articles:
        title   = article.get("title",   "").strip()
        url     = article.get("url",     "").strip()
        content = article.get("content", "")
        source  = article.get("source",  "")

        if not title or not url:
            continue

        if is_duplicate(url):
            logger.info(f"⏭️  중복 건너뜀: {title[:30]}")
            skipped_count += 1
            continue

        # 복지로는 이미 노인 카테고리(srchKeyCode=003)로 필터됨 → Gemini 스킵
        if source == "복지로":
            # 신규가 한꺼번에 많으면(예: numOfRows 확대 직후 13건) 알림이 폭주하므로
            # 실행당 상한을 두고 나머지는 다음 실행으로 넘김
            if bokjiro_saved >= BOKJIRO_MAX_NEW_PER_RUN:
                continue
            bokjiro_saved += 1
            ai_summary = f"📢 {title[:28]}"
            logger.info(f"📋 복지로 직접 저장: {ai_summary}")
        else:
            # 규칙 필터: 합격자 발표·행정 공개 등 정책상 제외 유형은 AI에 묻지 않고 고정 (llm_judge.py)
            reason = llm_judge.rule_skip_reason(title)
            if reason:
                logger.info(f"🚫 규칙 필터({reason}): {title[:30]}")
                skipped_count += 1
                continue

            # 키워드 프리필터: 복지관 출처는 이미 어르신 대상 기관이라 통과.
            # 구청 등 일반 출처는 제목에 노인 관련 키워드가 없으면 AI 호출 생략 (llm_judge.SENIOR_KEYWORDS)
            if not sources.is_center(source) and not llm_judge.has_senior_keyword(title):
                logger.info(f"⏭️  키워드 필터: {title[:30]}")
                skipped_count += 1
                continue

            # 이전 실행에서 이미 SKIP 판정된 공고는 AI 재호출 없이 건너뜀
            if is_skipped(url):
                skipped_count += 1
                continue

            # 본문이 없으면 상세 페이지에서 가져옴
            if not content:
                content = fetch_detail_content(url, source, title)
            ai_summary = llm_judge.judge_notice(title, content, source, sources.is_center(source))
            stats["llm_calls"] += 1
            if ai_summary.strip().upper() == "ERROR":
                stats["llm_errors"] += 1
                logger.warning(f"⚠️ AI 요약 실패로 보류(다음 실행 재시도): {title[:30]}")
                continue
            if ai_summary.strip().upper() == "SKIP":
                logger.info(f"🚫 AI 필터링: {title[:30]}")
                mark_skipped(title, source, url)
                continue

        save_to_firestore(title, ai_summary, source, url, silent=source in new_sources)
        saved_count += 1

    if new_sources:
        _save_warm_sources(warm | new_sources)

    stats["saved"], stats["skipped"] = saved_count, skipped_count
    result_msg = (
        f"✅ 파이프라인 완료 | "
        f"수집: {len(all_articles)}건, "
        f"저장: {saved_count}건, "
        f"중복 스킵: {skipped_count}건"
    )
    logger.info(result_msg)
    return result_msg


if __name__ == "__main__":
    import sys
    result = run_scraping_pipeline()
    sys.stdout.buffer.write((result + "\n").encode("utf-8", errors="replace"))
