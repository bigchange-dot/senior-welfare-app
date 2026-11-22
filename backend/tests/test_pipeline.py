"""scraping_function: 본문 추출과 파이프라인 실행 기록 (네트워크·Firestore·LLM은 가짜)."""

import logging

import pytest
import requests

import llm_judge
import scraping_function as sf
from conftest import FakeDB


# ── 본문 추출 ─────────────────────────────────────────────
def _fake_get(html, content_type="text/html; charset=utf-8"):
    def get(url, headers=None, timeout=None):
        r = requests.Response()
        r.status_code = 200
        r._content = html.encode("utf-8")
        r.headers["content-type"] = content_type
        r.encoding = "utf-8"
        return r
    return get


def test_board_body_selector_used(monkeypatch):
    html = '<div class="view_content">' + "어르신 건강교실 참여자 모집 안내입니다. " * 5 + "</div>"
    monkeypatch.setattr(sf.requests, "get", _fake_get(html))
    assert sf.fetch_detail_content("https://x.go.kr/view", "노원구청", "건강교실 참여자 모집").startswith("어르신 건강교실")


def test_generic_paragraphs_rejected_when_unrelated(monkeypatch):
    """강북 언론보도 사례: 외부 신문사 페이지의 <p>들은 다른 기사 제목이라 쓰면 안 된다."""
    html = "<p>" + "</p><p>".join(["이성배 서울시의원 공사장 발언", "청년 창업의 실리콘밸리", "1회용품 제로 만 다회용"] * 3) + "</p>"
    monkeypatch.setattr(sf.requests, "get", _fake_get(html))
    assert sf.fetch_detail_content("https://go.seoul.co.kr/news/1", "강북구청", "강북구 신청사 기공식 새 출발") == ""


def test_generic_paragraphs_used_when_related(monkeypatch):
    html = "<p>" + "강북구 신청사 기공식이 열렸다. 지역발전의 새 출발을 알렸다. " * 3 + "</p>"
    monkeypatch.setattr(sf.requests, "get", _fake_get(html))
    assert "신청사 기공식" in sf.fetch_detail_content("https://go.seoul.co.kr/news/1", "강북구청", "강북구 신청사 기공식 새 출발")


def test_missing_charset_does_not_break_korean(monkeypatch):
    html = '<div class="view_content">' + "어르신 한랭질환 예방 건강수칙 안내 " * 4 + "</div>"
    monkeypatch.setattr(sf.requests, "get", _fake_get(html, content_type="text/html"))
    assert "한랭질환" in sf.fetch_detail_content("https://ep-silver.org/x", "은평노인복지관", "한랭질환 예방")


# ── 파이프라인 실행 기록 ────────────────────────────────────
@pytest.fixture
def pipeline(monkeypatch):
    """스크래퍼 전부를 가짜로 바꾸고, 도봉노인복지관에만 공고 3건을 준다."""
    db = FakeDB()
    monkeypatch.setattr(sf, "_get_db", lambda: db)
    monkeypatch.setattr(sf, "is_duplicate", lambda url: False)
    monkeypatch.setattr(sf, "is_skipped", lambda url: False)
    monkeypatch.setattr(sf, "mark_skipped", lambda *a: None)
    monkeypatch.setattr(sf, "fetch_detail_content", lambda url, source, title="": "본문")
    saved = []
    monkeypatch.setattr(sf, "save_to_firestore", lambda t, s, src, url, silent=False: saved.append((t, s)))
    # 게시판 출처(board_sources)도 네트워크를 부르지 않게
    monkeypatch.setattr(sf.board_parser, "scrape_board", lambda *a, **k: [])

    names = [n for n in sf._run_pipeline.__code__.co_names if n.startswith("scrape_") or n == "fetch_bokjiro_api"]
    for n in names:
        monkeypatch.setattr(sf, n, lambda: [])
    def scrape_dobong_welfare():   # 실행 기록의 출처별 건수는 함수 이름(__name__)으로 집계
        return [
            {"title": "어르신 건강교실 모집", "url": "u1", "source": "도봉노인복지관"},
            {"title": "하반기 건강교실 합격자 발표", "url": "u2", "source": "도봉노인복지관"},
            {"title": "실패할공고 어르신 행사", "url": "u3", "source": "도봉노인복지관"},
        ]

    monkeypatch.setattr(sf, "scrape_dobong_welfare", scrape_dobong_welfare)

    def broken():
        raise RuntimeError("파서 깨짐")

    monkeypatch.setattr(sf, "scrape_jongno", broken)

    def fake_judge(title, content, source, is_center):
        if "실패할공고" in title:
            llm_judge.state["last_error"] = "ollama: down"
            logging.getLogger("llm_judge").error("❌ AI 요약 오류(ollama): down")
            return "ERROR"
        return "📚 어르신 건강교실 참여자 모집"

    monkeypatch.setattr(sf.llm_judge, "judge_notice", fake_judge)
    return db, saved


def test_run_records_stats(pipeline):
    db, saved = pipeline
    sf.run_scraping_pipeline()
    st = db.collection("system_status").document("pipeline").get().to_dict()
    assert st["collected"] == 3
    assert st["saved"] == 1 and saved == [("어르신 건강교실 모집", "📚 어르신 건강교실 참여자 모집")]
    assert st["skipped"] == 1                      # 합격자 발표는 규칙 필터
    assert st["llm_calls"] == 2 and st["llm_errors"] == 1
    assert "ollama" in st["llm_error"]
    assert st["source_counts"]["scrape_dobong_welfare"] == 3
    assert any("파서 깨짐" in e["message"] for e in st["errors"])
    assert st["fatal"] == ""
    assert len(db.collection("pipeline_runs").docs) == 1


def test_run_records_fatal_and_reraises(pipeline, monkeypatch):
    db, _ = pipeline

    def boom(url):
        raise RuntimeError("Firestore 연결 실패")

    monkeypatch.setattr(sf, "is_duplicate", boom)
    with pytest.raises(RuntimeError):
        sf.run_scraping_pipeline()
    st = db.collection("system_status").document("pipeline").get().to_dict()
    assert "Firestore 연결 실패" in st["fatal"]


def test_error_collector_removed_after_run(pipeline):
    before = len(logging.getLogger().handlers)
    sf.run_scraping_pipeline()
    assert len(logging.getLogger().handlers) == before


# ── 저장 (v1.5: 지역 코드) ─────────────────────────────────
def test_save_adds_region(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(sf, "_get_db", lambda: db)
    doc_id = sf.save_to_firestore("어르신 스마트폰 교실", "📱 스마트폰 교실 모집", "수락노인복지관", "https://x.or.kr/1")
    doc = db.collection(sf.FIREBASE_COLLECTION).document(doc_id).get().to_dict()
    assert (doc["region"], doc["province"]) == ("nowon", "seoul")


def test_save_unknown_source_keeps_notice(monkeypatch, caplog):
    db = FakeDB()
    monkeypatch.setattr(sf, "_get_db", lambda: db)
    with caplog.at_level(logging.WARNING):
        doc_id = sf.save_to_firestore("제목", "요약", "새로운복지관", "https://y.or.kr/1")
    doc = db.collection(sf.FIREBASE_COLLECTION).document(doc_id).get().to_dict()
    assert doc["region"] == "" and doc["source"] == "새로운복지관"
    assert "등록표에 없는 출처" in caplog.text


# ── 새 출처 첫 실행은 알림 없이 (v1.5) ─────────────────────────
def test_new_source_saved_silently_then_recorded(monkeypatch):
    db = FakeDB()
    db.collection("system_status").document("source_warmup").set({"sources": ["도봉노인복지관"]})
    monkeypatch.setattr(sf, "_get_db", lambda: db)
    monkeypatch.setattr(sf, "is_duplicate", lambda url: False)
    monkeypatch.setattr(sf, "is_skipped", lambda url: False)
    monkeypatch.setattr(sf, "fetch_detail_content", lambda url, source, title="": "본문")
    monkeypatch.setattr(sf.llm_judge, "judge_notice", lambda *a: "📢 요약")
    calls = []
    monkeypatch.setattr(sf, "save_to_firestore", lambda t, s, src, url, silent=False: calls.append((src, silent)))
    monkeypatch.setattr(sf.board_parser, "scrape_board", lambda *a, **k: [])
    for n in [n for n in sf._run_pipeline.__code__.co_names if n.startswith("scrape_") or n == "fetch_bokjiro_api"]:
        monkeypatch.setattr(sf, n, lambda: [])
    monkeypatch.setattr(sf, "scrape_dobong_welfare", lambda: [
        {"title": "어르신 건강교실 모집", "url": "a1", "source": "도봉노인복지관"},
        {"title": "어르신 스마트폰 교실 모집", "url": "a2", "source": "강서노인종합복지관"},
    ])
    sf._run_pipeline({"source_counts": {}, "llm_calls": 0, "llm_errors": 0})
    assert sorted(calls) == [("강서노인종합복지관", True), ("도봉노인복지관", False)]
    warm = db.collection("system_status").document("source_warmup").get().to_dict()["sources"]
    assert set(warm) == {"도봉노인복지관", "강서노인종합복지관"}


# ── Firestore 일시 오류 재시도 (2026-11-22: 맥이 잠든 뒤 504로 회차 전체가 중단됐던 문제) ──
def test_firestore_retry_recovers_from_transient_error(monkeypatch):
    from google.api_core import exceptions as gexc
    import scraping_function as sf
    waits = []
    monkeypatch.setattr(sf.time, "sleep", waits.append)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] <= 2:
            raise gexc.DeadlineExceeded("504 Deadline Exceeded")
        return "ok"

    assert sf._firestore_retry(flaky, "시험") == "ok"
    assert calls["n"] == 3 and waits == [5, 20]


def test_firestore_retry_gives_up_and_raises(monkeypatch):
    from google.api_core import exceptions as gexc
    import scraping_function as sf
    monkeypatch.setattr(sf.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def always():
        calls["n"] += 1
        raise gexc.ServiceUnavailable("503")

    import pytest
    with pytest.raises(gexc.ServiceUnavailable):
        sf._firestore_retry(always, "시험")
    assert calls["n"] == 4                      # 처음 + 재시도 3번

    def bug():
        calls["n"] += 1
        raise ValueError("코드 오류는 재시도하지 않는다")

    with pytest.raises(ValueError):
        sf._firestore_retry(bug, "시험")
    assert calls["n"] == 5
