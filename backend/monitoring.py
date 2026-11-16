"""
운영 감시 (2026-11-16 추가)

배경: 2026-10-23부터 Gemini 선불 크레딧 소진(402)으로 25일간 신규 공고 저장이 0건이었는데
아무도 몰랐다. 수집 함수는 매번 200(정상)으로 끝나서 Cloud Scheduler에도 실패로 잡히지 않았다.

구조:
- 기록: 수집 파이프라인이 실행마다 결과를 Firestore에 남긴다 (record_pipeline_run).
    pipeline_runs/{자동 ID}    실행 이력 (건수, 출처별 수집 수, 오류 요약)
    system_status/pipeline     마지막 실행 1건 (헬스체크가 읽음)
  수집을 클라우드에서 하든 로컬에서 하든 같은 기록을 남기므로 감시 방식은 그대로다.
- 점검: health_check_function(main.py, 매일 10:00·19:00 KST)이 기록과 최신 공고 시각을 보고
  문제가 있으면 "HEALTH_ALERT ..."를 ERROR 로그로 남긴다 (check_pipeline_health).
- 알림: Cloud Monitoring 로그 기반 알림 정책이 health-check-function의 ERROR 로그를 이메일로 보낸다.
  (정책 정의: ARCHITECTURE.md 3.5)

두 컬렉션은 firestore.rules의 기본 차단 규칙에 걸려 앱(클라이언트)에서는 읽을 수 없다.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

logger = logging.getLogger(__name__)

RUNS_COLLECTION   = "pipeline_runs"
STATUS_COLLECTION = "system_status"
STATUS_DOC        = "pipeline"
NOTICE_COLLECTION = "welfare_notices"

# 판정 기준
STALE_RUN_HOURS    = 16  # 09·18시 실행 → 정상이면 최대 15시간 간격
NO_NEW_NOTICE_DAYS = 4   # 2026-03~10 평균 하루 1.8건 저장. 주말·연휴를 고려해 4일
LLM_ERROR_MIN      = 3   # 일시적 429 한두 건은 무시 (전부 실패하면 건수와 관계없이 알림)

KST = timezone(timedelta(hours=9))


class ErrorCollector(logging.Handler):
    """실행 중 나온 ERROR 로그를 모아 실행 기록에 요약해 넣는다.

    스크래퍼 30여 개가 각자 예외를 잡고 로그만 남기므로, 스크래퍼를 고치지 않고
    루트 로거에서 한꺼번에 모은다. 같은 메시지(앞 120자 기준)는 횟수로 묶는다.
    """

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.counts: dict[str, int] = {}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            key = record.getMessage()[:120]
        except Exception:
            return
        self.counts[key] = self.counts.get(key, 0) + 1

    def summary(self, limit: int = 20) -> list[dict]:
        items = sorted(self.counts.items(), key=lambda kv: -kv[1])[:limit]
        return [{"message": m, "count": c} for m, c in items]


def record_pipeline_run(get_db, run: dict) -> None:
    """실행 결과를 남긴다. 기록 실패(DB 연결 포함)가 수집 결과를 망치지 않도록 예외는 로그만 남긴다."""
    try:
        db  = get_db()
        run = {**run, "runner": "cloud" if os.getenv("K_SERVICE") else "local"}
        db.collection(RUNS_COLLECTION).add(run)
        db.collection(STATUS_COLLECTION).document(STATUS_DOC).set(run)
    except Exception as e:
        logger.warning(f"⚠️ 실행 기록 저장 실패: {e}")


def _kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%m/%d %H:%M")


def find_problems(status: dict | None, latest_notice_at: datetime | None, now: datetime) -> list[str]:
    """마지막 실행 기록과 최신 공고 시각으로 문제 목록을 만든다 (Firestore 없이 시험할 수 있게 분리)."""
    problems: list[str] = []

    if not status:
        problems.append("수집 실행 기록이 없음")
    else:
        finished = status.get("finished_at")
        if finished and now - finished > timedelta(hours=STALE_RUN_HOURS):
            hours = int((now - finished).total_seconds() // 3600)
            problems.append(f"수집이 {hours}시간째 실행되지 않음 (마지막 {_kst(finished)})")
        if status.get("fatal"):
            problems.append(f"수집이 오류로 중단됨: {status['fatal'][:150]}")
        elif status.get("collected", 0) == 0:
            problems.append("수집 0건 (모든 출처 실패)")

        calls, errors = status.get("llm_calls", 0), status.get("llm_errors", 0)
        if errors and (errors >= LLM_ERROR_MIN or errors == calls):
            detail = status.get("llm_error") or ""
            problems.append(f"AI 요약 실패 {errors}/{calls}건: {detail[:150]}")

    if latest_notice_at is None:
        problems.append("저장된 공고가 없음")
    elif now - latest_notice_at > timedelta(days=NO_NEW_NOTICE_DAYS):
        days = (now - latest_notice_at).days
        problems.append(f"{days}일째 새 공고 저장 없음 (마지막 {_kst(latest_notice_at)})")

    return problems


def check_pipeline_health(db=None, now: datetime | None = None) -> list[str]:
    """헬스체크 진입점. 문제가 있으면 ERROR 로그(HEALTH_ALERT)를 남기고 문제 목록을 돌려준다."""
    db  = db or firestore.client()
    now = now or datetime.now(timezone.utc)

    snap   = db.collection(STATUS_COLLECTION).document(STATUS_DOC).get()
    status = snap.to_dict() if snap.exists else None

    latest = (
        db.collection(NOTICE_COLLECTION)
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(1)
        .get()
    )
    latest_notice_at = latest[0].to_dict().get("timestamp") if latest else None

    problems = find_problems(status, latest_notice_at, now)

    # 참고 정보: 이번 실행에서 0건이었거나 실패한 출처 (알림 조건은 아님, 메일 본문에만 포함)
    note = ""
    if status:
        zero = [name for name, n in (status.get("source_counts") or {}).items() if n <= 0]
        if zero:
            note = f" | 참고: 0건·실패 출처 {len(zero)}곳 ({', '.join(sorted(zero))})"

    if problems:
        logger.error("HEALTH_ALERT | " + " / ".join(problems) + note)
    else:
        logger.info("HEALTH_OK" + note)
    return problems
