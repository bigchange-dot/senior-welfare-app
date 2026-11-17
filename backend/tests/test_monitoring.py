"""monitoring: 헬스체크 판정 (2026-10-23 장애가 25일간 드러나지 않았던 것의 재발 방지)."""

import logging
from datetime import datetime, timedelta, timezone

import monitoring as M
from conftest import FakeDB

NOW = datetime(2026, 11, 17, 1, 0, tzinfo=timezone.utc)   # 11/17 10:00 KST
OK = {"finished_at": NOW - timedelta(hours=1), "collected": 225, "llm_calls": 3, "llm_errors": 0}
RECENT = NOW - timedelta(days=1)


def test_healthy():
    assert M.find_problems(OK, RECENT, NOW) == []


def test_gemini_outage_detected():
    """실제 장애 상황: 호출 전부 402, 25일째 새 공고 없음."""
    status = {**OK, "llm_calls": 33, "llm_errors": 33, "llm_error": "402 RESOURCE_EXHAUSTED"}
    problems = M.find_problems(status, datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc), NOW)
    assert any("AI 요약 실패 33/33" in p for p in problems)
    assert any("25일째 새 공고" in p for p in problems)


def test_single_transient_llm_error_ignored():
    assert M.find_problems({**OK, "llm_calls": 10, "llm_errors": 1}, RECENT, NOW) == []


def test_all_llm_calls_failed_even_if_one():
    assert M.find_problems({**OK, "llm_calls": 1, "llm_errors": 1}, RECENT, NOW)


def test_stale_run_and_fatal_and_zero_collected():
    assert M.find_problems({**OK, "finished_at": NOW - timedelta(hours=20)}, RECENT, NOW)
    assert M.find_problems({**OK, "fatal": "RuntimeError: boom"}, RECENT, NOW)
    assert M.find_problems({**OK, "collected": 0}, RECENT, NOW)


def test_new_notice_threshold():
    assert M.find_problems(OK, NOW - timedelta(days=3, hours=20), NOW) == []
    assert M.find_problems(OK, NOW - timedelta(days=5), NOW)


def test_missing_status():
    assert M.find_problems(None, RECENT, NOW) == ["수집 실행 기록이 없음"]


def test_check_pipeline_health_logs_alert(caplog):
    db = FakeDB()
    db.collection("welfare_notices").document("a").set({"timestamp": NOW - timedelta(days=10)})
    with caplog.at_level(logging.ERROR):
        problems = M.check_pipeline_health(db, NOW)
    assert problems
    assert any("HEALTH_ALERT" in r.getMessage() for r in caplog.records)


def test_record_failure_does_not_raise():
    def broken_db():
        raise RuntimeError("인증 없음")

    M.record_pipeline_run(broken_db, {"collected": 1})   # 예외 없이 지나가야 함
