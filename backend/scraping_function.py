"""
Track A: 데이터 수집 및 AI 가공
- 복지로 공공데이터 API
- 성동구청 채용/어르신 일자리 스크래핑
- 강북구청 채용/보도자료/언론보도 스크래핑
- Gemini AI 필터링 & 요약
- Firestore 저장 (중복 방지)
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

GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
DATA_GO_KR_KEY      = os.getenv("DATA_GO_KR_KEY", "").strip()
FIREBASE_COLLECTION = "welfare_notices"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
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
# Firestore / Gemini 클라이언트는 첫 호출 시 생성
# ─────────────────────────────────────────────
_db            = None
_gemini_client = None


def _get_db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db


def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────
def make_doc_id(url: str) -> str:
    """URL의 SHA-256 해시를 Document ID로 사용 (중복 방지)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def is_duplicate(url: str) -> bool:
    """Firestore에 해당 URL 문서가 이미 존재하는지 확인."""
    doc_id = make_doc_id(url)
    doc = _get_db().collection(FIREBASE_COLLECTION).document(doc_id).get()
    return doc.exists


def save_to_firestore(title: str, ai_summary: str, source: str, url: str) -> str:
    """유효한 공고를 Firestore에 저장하고 Document ID를 반환."""
    doc_id  = make_doc_id(url)
    doc_ref = _get_db().collection(FIREBASE_COLLECTION).document(doc_id)
    doc_ref.set({
        "title":       title,
        "ai_summary":  ai_summary,
        "source":      source,
        "url":         url,
        "timestamp":   datetime.now(timezone.utc),
        "is_notified": False,
    })
    logger.info(f"✅ 저장 완료: [{source}] {ai_summary}")
    return doc_id


# ─────────────────────────────────────────────
# Gemini AI 요약 (google-genai SDK)
# ─────────────────────────────────────────────
def fetch_detail_content(url: str, source: str) -> str:
    """상세 페이지에서 본문 텍스트 최대 300자 추출."""
    try:
        if "gangbuk" in url:
            session = _get_gangbuk_session(url)
            res = session.get(url, timeout=10)
        else:
            res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        # 공통 본문 셀렉터 (한국 공공기관 게시판 패턴)
        for selector in [
            "div.view_content", "div.bbs_content", "div.board_view",
            "div.cont_area", "div.view_txt", "td.view_con",
            "div.detail_content", "div#content",
        ]:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    return text[:300]

        # 셀렉터 실패 시 <p> 태그 합산
        paragraphs = " ".join(p.get_text(strip=True) for p in soup.select("p") if p.get_text(strip=True))
        return paragraphs[:300]
    except Exception as e:
        logger.warning(f"⚠️ 본문 fetch 실패 ({url[:40]}): {e}")
        return ""


WELFARE_CENTER_SOURCES = {
    "수락노인복지관", "마포노인복지관", "도봉노인복지관", "은평노인복지관",
    "종로노인복지관", "약수노인복지관", "용산노인복지관", "서대문노인복지관",
    "성동구 어르신일자리",
}


def summarize_with_gemini(title: str, content: str = "", source: str = "") -> str:
    """
    노인 관련 공고인지 판별하고, 맞으면 30자 이내 속보 요약 반환.
    관련 없으면 'SKIP' 반환.
    복지관 출처는 어르신 대상 맥락을 명시해 SKIP 비율 완화.
    """
    # 노인복지관 출처일 때 판별 기준 완화 — 이미 어르신 대상 기관
    if source in WELFARE_CENTER_SOURCES:
        context = f"출처: {source} (노인복지관 — 모든 프로그램·서비스가 어르신 대상)\n"
        pass_criteria = """통과(PASS): 아래 중 하나라도 해당하면 통과
  - 어르신 참여 프로그램 모집 (교육, 문화, 여가, 취미, 운동 등)
  - 어르신 일자리·취업 프로그램
  - 어르신 복지서비스·지원금·수당 신청
  - 어르신 건강·의료·돌봄 서비스"""
        skip_criteria = """스킵(SKIP): 아래에 해당하면 SKIP
  - 직원·강사·요양보호사 등 종사자 채용 공고
  - 업무추진비·계약 등 행정·회계 공개 공고
  - 시설 공사·점검 안내"""
    else:
        context = ""
        pass_criteria = """통과(PASS): 노인·어르신(60세 이상) 본인이 직접 혜택받는 공고
  - 노인 대상 지원금, 수당, 서비스 신청
  - 노인 일자리·취업 프로그램 참여자 모집
  - 노인 의료·요양·돌봄 서비스"""
        skip_criteria = """스킵(SKIP): 아래 중 하나라도 해당하면 반드시 SKIP
  - 노인 관련 업무 직원·강사·지도사·요양사·봉사자 채용 (예: "시니어 지도사 모집", "요양보호사 채용")
  - 노인과 무관한 일반 구정 소식, 시설 공사, 행정 공고
  - 제목과 본문에 노인·어르신·시니어·고령·경로 관련 내용이 전혀 없는 경우"""

    prompt = f"""당신은 노인 복지 공고 필터링 전문가입니다. 아래 공고를 분석하세요.

{context}제목: {title}
본문: {content[:300] if content else '(없음)'}

【판별 기준】
{pass_criteria}

{skip_criteria}

【출력 규칙】
- PASS이면: 이모지 포함 30자 이내 속보 제목 출력 (제목·본문에 있는 사실만 사용, 없는 단어 추가 금지)
- SKIP이면: 정확히 'SKIP' 만 출력
- 설명, 이유, 부가 문장 절대 추가 금지"""

    for attempt in range(3):
        try:
            client   = _get_gemini()
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
            )
            result = response.text.strip()
            # Gemini가 간혹 "PASS: ..." 또는 "PASS ..." 형태로 응답하는 경우 접두어 제거
            if result.upper().startswith("PASS"):
                result = result[4:].lstrip(":").strip()
            logger.info(f"🤖 Gemini 결과: {result[:50]}")
            time.sleep(13)  # 무료 티어 분당 5회 제한 준수
            return result
        except Exception as e:
            err_str = str(e)
            if "429" in err_str and attempt < 2:
                wait = 65 if attempt == 0 else 130
                logger.warning(f"⏳ Gemini 429 Rate Limit, {wait}초 대기 후 재시도...")
                time.sleep(wait)
            else:
                logger.error(f"❌ Gemini API 오류: {e}")
                return "SKIP"
    return "SKIP"


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
            "numOfRows":  "20",
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
        logger.error(f"❌ 복지로 API 오류: {e}")

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
# Track A-3: 성동구 어르신 일자리
# ─────────────────────────────────────────────
def scrape_sdsenior() -> list[dict]:
    base_url = "https://www.sdsenior.or.kr/"
    articles = []

    try:
        res  = requests.get(base_url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        rows = soup.select(
            "ul.notice_list li, div.board_list tbody tr, "
            "section.job_list article, table tbody tr"
        )
        logger.info(f"👴 성동구 어르신 일자리: {len(rows)}개 항목 발견")

        for row in rows[:15]:
            try:
                link_tag = row.select_one("a")
                if not link_tag:
                    continue

                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")

                if href.startswith("/"):
                    detail_url = "https://www.sdsenior.or.kr" + href
                elif href.startswith("http"):
                    detail_url = href
                else:
                    continue

                if title and len(title) > 2:
                    articles.append({"title": title, "url": detail_url, "content": "", "source": "성동구 어르신일자리"})
            except Exception as e:
                logger.warning(f"⚠️ sdsenior 행 파싱 오류: {e}")

    except Exception as e:
        logger.error(f"❌ 성동구 어르신 일자리 스크래핑 오류: {e}")

    return articles


# ─────────────────────────────────────────────
# 강북구청 봇 감지(SAB) 우회 세션 생성
# ─────────────────────────────────────────────
def _get_gangbuk_session(url: str) -> requests.Session:
    """
    강북구청 SAB(ShieldABit) 봇 감지를 우회하는 세션 반환.
    JS 챌린지 응답에서 sabFingerPrint / sabSignature 쿠키를 파싱해 재요청.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    res = session.get(url, timeout=15)
    if "sabFingerPrint" in res.text:
        fp_match  = re.search(r'sabFingerPrint\s*=\s*["\']?(\w+)', res.text)
        sig_match = re.search(r'sabSignature\s*=\s*["\']?(\w+)', res.text)
        if fp_match:
            session.cookies.set("sabFingerPrint", fp_match.group(1), domain="www.gangbuk.go.kr")
        if sig_match:
            session.cookies.set("sabSignature", sig_match.group(1), domain="www.gangbuk.go.kr")
        # 쿠키 설정 후 재요청
        res = session.get(url, timeout=15)

    res.raise_for_status()
    return session


def _scrape_gangbuk_board(url: str, label: str, limit: int = 15) -> list[dict]:
    """강북구청 게시판 공통 스크래핑 로직."""
    articles = []
    try:
        session = _get_gangbuk_session(url)
        res     = session.get(url, timeout=15)
        res.raise_for_status()
        soup    = BeautifulSoup(res.text, "lxml")

        rows = soup.select("table.board-list tbody tr, ul.board-list-ul li")
        if not rows:
            rows = soup.select("table tbody tr")

        logger.info(f"{label}: {len(rows)}개 행 발견")

        for row in rows[:limit]:
            try:
                link_tag = row.select_one("td.subject a, td.title a, td a")
                if not link_tag:
                    continue
                title = link_tag.get_text(strip=True)
                href  = link_tag.get("href", "")
                if href.startswith("/"):
                    detail_url = "https://www.gangbuk.go.kr" + href
                elif href.startswith("http"):
                    detail_url = href
                elif "viewCount" in href:
                    # 언론보도: javascript:viewCount('ID', 'https://...')
                    m = re.search(r"viewCount\([^,]+,\s*'([^']+)'", href)
                    if not m:
                        continue
                    detail_url = m.group(1)
                else:
                    continue
                if title:
                    articles.append({"title": title, "url": detail_url, "content": "", "source": "강북구청"})
            except Exception as e:
                logger.warning(f"⚠️ {label} 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ {label} 스크래핑 오류: {e}")
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
# Track A-4: 강북구청 채용공고
# ─────────────────────────────────────────────
def scrape_gangbuk_jobs() -> list[dict]:
    return _scrape_gangbuk_board(
        "https://www.gangbuk.go.kr/portal/bbs/B0000154/list.do?menuNo=200510",
        "🏢 강북구청 채용", limit=15
    )


# ─────────────────────────────────────────────
# Track A-5: 강북구청 보도자료
# ─────────────────────────────────────────────
def scrape_gangbuk_press() -> list[dict]:
    return _scrape_gangbuk_board(
        "https://www.gangbuk.go.kr/portal/bbs/B0000142/list.do?menuNo=200625",
        "📰 강북구청 보도자료", limit=10
    )


# ─────────────────────────────────────────────
# Track A-6: 강북구청 언론보도
# ─────────────────────────────────────────────
def scrape_gangbuk_media() -> list[dict]:
    return _scrape_gangbuk_board(
        "https://www.gangbuk.go.kr/portal/bbs/B0000260/list.do?menuNo=200638",
        "📺 강북구청 언론보도", limit=10
    )


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
# Track A-11f: 강서구청 공지사항
# URL: https://www.gangseo.seoul.kr/gs020502
# 링크 형식: /gs020502/319334?... (절대경로) — 표준 헬퍼 사용
# 확인: 2026-05-06 ✅ 10행 수집
# ─────────────────────────────────────────────
def scrape_gangseo() -> list[dict]:
    return _scrape_seoul_board(
        "https://www.gangseo.seoul.kr/gs020502",
        "🏢 강서구청", "https://www.gangseo.seoul.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-11g: 동작구청 공지사항
# URL: https://www.dongjak.go.kr/portal/bbs/B0001396/list.do?menuNo=201658
# 링크 형식: /portal/bbs/B0001396/view.do?nttId=...&menuNo=201658 (절대경로)
# 확인: 2026-05-06 ✅ 10행 수집
# ─────────────────────────────────────────────
def scrape_dongjak() -> list[dict]:
    return _scrape_seoul_board(
        "https://www.dongjak.go.kr/portal/bbs/B0001396/list.do?menuNo=201658",
        "🏢 동작구청", "https://www.dongjak.go.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-11h: 관악구청 공지사항
# URL: https://www.gwanak.go.kr/site/365/bbs/list.do?cbIdx=302
# 링크 형식: onclick="doBbsFView('302','198737','16010100','198737')"
#   → /site/365/bbs/view.do?cbIdx=302&bcIdx=198737 (Gbn은 menuId, parentSeq는 동일)
# 확인: 2026-05-06 ✅
# ─────────────────────────────────────────────
def scrape_gwanak() -> list[dict]:
    list_url = "https://www.gwanak.go.kr/site/365/bbs/list.do?cbIdx=302"
    label    = "🏢 관악구청"
    articles = []
    try:
        res = requests.get(list_url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")
        rows = soup.select("table tbody tr")
        logger.info(f"{label}: {len(rows)}개 행 발견")
        for row in rows[:15]:
            try:
                a = row.select_one("td.title a, td.subject a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                onclick = a.get("onclick", "")
                m = re.search(r"doBbsFView\(\s*'(\d+)'\s*,\s*'(\d+)'", onclick)
                if not (title and m):
                    continue
                cb_idx, bc_idx = m.group(1), m.group(2)
                detail_url = f"https://www.gwanak.go.kr/site/365/bbs/view.do?cbIdx={cb_idx}&bcIdx={bc_idx}"
                articles.append({"title": title, "url": detail_url, "content": "", "source": "관악구청"})
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
# Track A-13: 시립노원노인종합복지관 (노원구)
# URL: https://www.nowonsenior.or.kr/bbs/board.php?bo_table=board01
# 확인: G5 BBS 표준 구조
# ─────────────────────────────────────────────
def scrape_nowon_welfare() -> list[dict]:
    return _scrape_g5_board(
        "https://www.nowonsenior.or.kr/bbs/board.php?bo_table=board01",
        "노원노인복지관", "https://www.nowonsenior.or.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-14: 신내노인종합복지관 (중랑구)
# URL: http://shinnaesenior.or.kr/bbs/board.php?bo_table=0401
# 확인: G5 BBS 표준 구조
# ─────────────────────────────────────────────
def scrape_shinnae_welfare() -> list[dict]:
    return _scrape_g5_board(
        "http://shinnaesenior.or.kr/bbs/board.php?bo_table=0401",
        "신내노인복지관", "http://shinnaesenior.or.kr", limit=15
    )


# ─────────────────────────────────────────────
# Track A-15: 마포노인종합복지관 (마포구)
# URL: http://senior21.or.kr/bbs/board.php?bo_table=notice
# 확인: G5 BBS 표준 구조
# ─────────────────────────────────────────────
def scrape_mapo_welfare() -> list[dict]:
    # data-wr-id 속성으로 URL 조합하는 커스텀 구조
    url      = "https://senior21.or.kr/bbs/board.php?bo_table=MPB_2010&lang=ko&me_code=2010"
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        rows = soup.select("tbody tr.list-row-clickable[data-wr-id]")
        logger.info(f"마포노인복지관: {len(rows)}개 행 발견")

        for row in rows[:15]:
            try:
                wr_id = row.get("data-wr-id", "").strip()
                if not wr_id:
                    continue
                # 제목: 두 번째 td 또는 .card-subject
                title_tag = row.select_one("td:nth-child(2), .card-subject")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                if not title:
                    continue
                detail_url = f"https://senior21.or.kr/bbs/board.php?bo_table=MPB_2010&wr_id={wr_id}&lang=ko&me_code=2010"
                articles.append({"title": title, "url": detail_url, "content": "", "source": "마포노인복지관"})
            except Exception as e:
                logger.warning(f"⚠️ 마포노인복지관 행 파싱 오류: {e}")
    except Exception as e:
        logger.error(f"❌ 마포노인복지관 스크래핑 오류: {e}")
    return articles


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
# Track A-16: 시립강북노인종합복지관 (강북구)
# URL: https://www.gswc.or.kr/bbs/board.php?bo_table=0201_1
# 확인: G5 BBS 표준 구조
# ─────────────────────────────────────────────
def scrape_gangbuk_welfare() -> list[dict]:
    return _scrape_g5_board(
        "https://www.gswc.or.kr/bbs/board.php?bo_table=0201_1",
        "강북노인복지관", "https://www.gswc.or.kr", limit=15
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
# 메인 파이프라인
# ─────────────────────────────────────────────
def run_scraping_pipeline(request=None):
    logger.info("🚀 스크래핑 파이프라인 시작")

    scrapers = [
        fetch_bokjiro_api,
        scrape_seongdong_jobs,
        scrape_sdsenior,
        scrape_gangbuk_jobs,
        scrape_gangbuk_press,
        scrape_gangbuk_media,
        scrape_nowon,
        scrape_dobong,
        scrape_jungnang,
        scrape_mapo,
        scrape_eunpyeong,
        scrape_jongno,           # 종로 ✅ (2026-04-09 추가)
        scrape_junggu,           # 중구 ✅ (2026-04-09 추가)
        scrape_yongsan,          # 용산 ✅ (2026-04-09 추가)
        scrape_seodaemun,        # 서대문 ✅ (2026-04-09 추가)
        scrape_gangseo,          # 강서 ✅ (2026-05-06 추가)
        scrape_dongjak,          # 동작 ✅ (2026-05-06 추가)
        scrape_gwanak,           # 관악 ✅ (2026-05-06 추가, doBbsFView)
        scrape_yangcheon,        # 양천 ✅ (2026-05-06 추가, doBbsFView + wdigm_title)
        # 노인복지관 (접속 가능한 8개)
        scrape_surak_welfare,    # 노원 수락 ✅
        scrape_mapo_welfare,     # 마포 ✅
        scrape_dobong_welfare,   # 도봉 ✅
        scrape_eunpyeong_welfare, # 은평 ✅
        scrape_jongno_welfare,   # 종로 ✅ (2026-04-09 추가, SSL 만료로 verify=False)
        scrape_yaksu_welfare,    # 중구 약수 ✅ (2026-04-09 추가)
        scrape_yongsan_welfare,  # 용산 ✅ (2026-04-09 추가)
        scrape_seodaemun_welfare, # 서대문 ✅ (2026-04-09 추가)
        # scrape_nowon_welfare   — 게시판 없음 (존재하지 않는 bo_table)
        # scrape_shinnae_welfare — SSL 인증서 오류
        # scrape_gangbuk_welfare — 403 Forbidden
    ]

    all_articles: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=23) as executor:
        futures = {executor.submit(fn): fn.__name__ for fn in scrapers}
        for future in concurrent.futures.as_completed(futures):
            fn_name = futures[future]
            try:
                result = future.result()
                logger.info(f"  ↳ {fn_name}: {len(result)}건 수집")
                all_articles.extend(result)
            except Exception as e:
                logger.error(f"  ↳ {fn_name} 실패: {e}")

    logger.info(f"📦 총 수집 건수: {len(all_articles)}")

    saved_count   = 0
    skipped_count = 0

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
            ai_summary = f"📢 {title[:28]}"
            logger.info(f"📋 복지로 직접 저장: {ai_summary}")
        else:
            # 키워드 프리필터: 복지관 출처는 이미 어르신 대상 기관이라 통과.
            # 구청 등 일반 출처는 제목에 노인 관련 키워드가 없으면 Gemini 호출 생략
            # → Gemini 무료 티어 분당 5회 제한(sleep 13초) 때문에 전체 실행 시간을
            #   크게 줄이기 위한 최적화. 함수 timeout 초과 방지.
            SENIOR_KEYWORDS = (
                "노인", "어르신", "경로", "실버", "시니어", "고령", "65세",
                "요양", "돌봄", "치매", "장사", "기초연금", "복지관", "경로당",
            )
            if source not in WELFARE_CENTER_SOURCES and not any(k in title for k in SENIOR_KEYWORDS):
                logger.info(f"⏭️  키워드 필터: {title[:30]}")
                skipped_count += 1
                continue

            # 본문이 없으면 상세 페이지에서 가져옴
            if not content:
                content = fetch_detail_content(url, source)
            ai_summary = summarize_with_gemini(title, content, source)
            if ai_summary.strip().upper() == "SKIP":
                logger.info(f"🚫 AI 필터링: {title[:30]}")
                continue

        save_to_firestore(title, ai_summary, source, url)
        saved_count += 1

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
