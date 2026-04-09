"""
Firebase Cloud Functions 진입점 (main.py)
- scraping_function: Cloud Scheduler HTTP 트리거 (매일 09:00, 18:00 KST)
- notification_function: Firestore onCreate 트리거
"""

from firebase_functions import https_fn, firestore_fn, options
from scraping_function import run_scraping_pipeline
from notification_function import on_welfare_notice_created

# ─────────────────────────────────────────────
# Track A: 스크래핑 HTTP Function
# Cloud Scheduler 또는 직접 HTTP 호출로 실행
# ─────────────────────────────────────────────
@https_fn.on_request(
    region="asia-northeast3",       # 서울 리전
    timeout_sec=1800,               # 30분 (Gemini rate limit sleep 13초 × 100+건 대응)
    memory=options.MemoryOption.MB_512,
    secrets=["GEMINI_API_KEY", "DATA_GO_KR_KEY"],
)
def scraping_function(req: https_fn.Request) -> https_fn.Response:
    """HTTP 트리거: 데이터 수집 & AI 요약 & Firestore 저장."""
    try:
        result = run_scraping_pipeline(req)
        return https_fn.Response(f"✅ {result}", status=200)
    except Exception as e:
        return https_fn.Response(f"❌ 오류: {str(e)}", status=500)


# ─────────────────────────────────────────────
# Track B: Firestore 트리거 (알림 발송)
# welfare_notices/{docId} 에 새 문서 생성 시 자동 호출
# ─────────────────────────────────────────────
@firestore_fn.on_document_created(
    document="welfare_notices/{docId}",
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
)
def notification_function(
    event: firestore_fn.Event[firestore_fn.DocumentSnapshot],
) -> None:
    """Firestore 트리거: 새 공고 문서 생성 시 FCM 푸시 알림 발송."""
    on_welfare_notice_created(event)
