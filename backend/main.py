"""
Firebase Cloud Functions 진입점 (main.py)
- scraping_function: Cloud Scheduler HTTP 트리거 (매일 09:00, 18:00 KST)
- notification_function: Firestore onCreate 트리거
- health_check_function: 수집 상태 점검 (매일 10:00, 19:00 KST) — monitoring.py
"""

from firebase_functions import https_fn, firestore_fn, scheduler_fn, options
from scraping_function import run_scraping_pipeline
from notification_function import on_welfare_notice_created
from monitoring import check_pipeline_health

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


# ─────────────────────────────────────────────
# 운영 감시: 수집 실행 기록·최신 공고 시각 점검 (2026-11-16 추가)
# 수집(09:00·18:00) 1시간 뒤 실행. 문제가 있으면 HEALTH_ALERT를 ERROR 로그로 남기고,
# Cloud Monitoring 로그 알림 정책이 이메일로 보낸다 (ARCHITECTURE.md 3.5)
# ─────────────────────────────────────────────
@scheduler_fn.on_schedule(
    schedule="0 10,19 * * *",
    timezone=options.Timezone("Asia/Seoul"),
    region="asia-northeast3",
    memory=options.MemoryOption.MB_256,
)
def health_check_function(event: scheduler_fn.ScheduledEvent) -> None:
    """스케줄 트리거: 수집 파이프라인 상태 점검."""
    check_pipeline_health()
