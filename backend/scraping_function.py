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
def summarize_with_gemini(title: str, content: str = "") -> str:
    """
    노인 관련 공고인지 판별하고, 맞으면 30자 이내 속보 요약 반환.
    관련 없으면 'SKIP' 반환.
    """
    prompt = f"""당신은 노인 복지 전문 에디터입니다. 다음 공고를 분석해주세요.

제목: {title}
내용: {content[:500] if content else '(내용 없음)'}

규칙:
1. 이 공고가 노인(60세 이상) 혜택, 일자리, 지원금, 모집, 신청과 관련이 있으면
   → 이모지를 포함한 30자 이내 속보 제목만 출력하세요. (예: 📢 성동구 시니어 일자리 100명 모집!)
2. 관련 없는 공고라면 → 정확히 'SKIP' 만 출력하세요.
3. 다른 설명이나 부가 문장은 절대 추가하지 마세요."""

    for attempt in range(3):
        try:
            client   = _get_gemini()
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            result = response.text.strip()
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
    ]

    all_articles: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
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
            ai_summary = summarize_with_gemini(title, content)
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
