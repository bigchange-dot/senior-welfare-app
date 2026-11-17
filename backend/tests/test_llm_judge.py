"""llm_judge: 규칙 필터·요약 검사·날짜 판단 (LLM 호출 없음)."""

import json
from datetime import datetime

import pytest

import llm_judge as J

TODAY = datetime(2026, 11, 16, 22, 0, tzinfo=J.KST)


# ── 규칙 필터 ─────────────────────────────────────────────
@pytest.mark.parametrize("title, reason", [
    # 합격·결과 발표 (판정이 엇갈려 같은 알림이 15건 넘게 나갔던 유형)
    ("2026년 하반기 노년사회화교육(컴퓨터 기초) 합격자 발표", "합격·선정 결과"),
    ("2027년 약수노인종합복지관 식자재 납품업체 선정 서류심사 결과", "합격·선정 결과"),
    # 행정 공개·공고
    ("2026년 9월 업무추진비 공시", "행정 공개"),
    ("주·정차위반 과태료 사전통지서 공시송달 공고", "행정 공고"),
    ("2027년 약수노인종합복지관 식자재 납품업체 선정 서류", "행정 공고"),
    ("노인장기요양보험법 위반에 따른 명단 공표", "행정 공고"),
    # 종사자 채용 (LLM이 강사 채용을 통과시켰던 유형)
    ("[긴급] 노인맞춤돌봄서비스 남성특화 프로그램(필라테스) 강사 채용 공고", "종사자 채용"),
    ("2027년 하남시보건소 시니어 헬스센터 기간제근로자(간호사, 신체활동전문가 또는 물리치료사) 채용 공고", "종사자 채용"),
    ("[직원채용] 운전원 모집", "종사자 채용"),
    # 기관 모집
    ("2026년 노원구 일상돌봄 서비스 제공기관 모집 재공고", "기관 모집"),
    ("노인맞춤돌봄서비스 광역지원기관 모집공고", "기관 모집"),
    ("성남시 다함께돌봄센터 위탁운영 모집 공고", "기관 모집"),
    # 마감
    ("[접수마감] 구강교육 참여자 모집 안내", "마감"),
])
def test_rule_skips(title, reason):
    assert J.rule_skip_reason(title) == reason


@pytest.mark.parametrize("title", [
    # 결과 발표라도 새로 신청할 수 있으면 LLM에 넘긴다
    "[무악센터] 여름단기학기 추첨 결과 및 추가접수 안내",
    # 어르신을 고용하는 기관의 채용은 종사자 채용 규칙에서 뺀다
    "2026년 노원어르신행복주식회사 기간제 근로자(바리스타) 채용공고",
    "중랑구 시니어인턴 채용",
    "시니어 강사 모집",
    # 교육생·참여자 모집은 채용이 아니다
    "강북구, 경비원·요양보호사 양성교육 참여자 모집",
    "2027년 노인일자리 및 사회활동 지원사업 참여자 모집",
    # 마감 임박은 통과
    "모집 마감 임박! 건강교실",
    "어르신 독감 예방접종 무료 실시 안내",
])
def test_rule_keeps(title):
    assert J.rule_skip_reason(title) is None


def test_senior_keyword():
    assert J.has_senior_keyword("어르신 건강교실")
    assert not J.has_senior_keyword("주민참여예산 회의록")


# ── 요약 검사·후처리 ────────────────────────────────────────
TITLE = "어르신 독감 예방접종 무료 실시 안내"
BODY = "만 65세 이상 어르신 대상, 11월 30일까지 보건소에서 무료 접종"


def _pass(summary):
    return json.dumps({"decision": "PASS", "summary": summary}, ensure_ascii=False)


def test_valid_summary_kept():
    assert J.finalize(_pass("💉 65세 이상 독감 무료접종 · 11/30까지"), TITLE, BODY, TODAY) == "💉 65세 이상 독감 무료접종 · 11/30까지"


def test_warning_words_removed_and_emoji_added():
    out = J.finalize(_pass("🚨 [속보] 어르신 독감 무료접종 안내!"), TITLE, BODY, TODAY)
    assert "속보" not in out and "🚨" not in out and "!" not in out
    assert out.startswith("💉")          # 키워드 이모지


@pytest.mark.parametrize("summary", [
    "💉 어르신 독감 무료접종 선착순 50명",   # 제목·본문에 없는 숫자 = 지어낸 정보
    "取暖降温费 通知",                        # 한자
    "Free flu shot for seniors 안내",         # 원문에 없는 영어
])
def test_invalid_summary_falls_back_to_title(summary):
    out = J.finalize(_pass(summary), TITLE, BODY, TODAY)
    assert "독감 예방접종 무료 실시 안내" in out


def test_filler_tail_removed():
    assert J._clean("우울증 검사 접수 안내 · 오늘부터") == "우울증 검사 접수 안내"
    assert J._clean("치매선별검사 접수 안내 · 10월") == "치매선별검사 접수 안내 · 10월"


def test_skip_and_plain_skip():
    assert J.finalize('{"decision":"SKIP","summary":""}', TITLE, BODY, TODAY) == "SKIP"
    assert J.finalize("SKIP", TITLE, BODY, TODAY) == "SKIP"


def test_broken_json_raises():
    with pytest.raises(ValueError):
        J.finalize('{"decision":"MAYBE","summary":"x"}', TITLE, BODY, TODAY)


# ── 기간 지남 ─────────────────────────────────────────────
@pytest.mark.parametrize("summary, expired", [
    ("웃음, 그리다 전시회 관람 · 11/9~11/12", True),          # 첫 로컬 실행에서 저장됐던 지난 행사
    ("나다움 문화살롱 6차시 참여자 모집 · 10월 28일~30일", True),
    ("정신건강교육 참여자 모집 · 11월 26일", False),
    ("오늘 행사 · 11월 16일", False),
    ("신년 강좌 접수 · 1/5까지", False),                        # 11월에 쓴 1/5는 내년
])
def test_expired_dates(summary, expired):
    out = J.finalize(_pass(summary), summary, summary, TODAY)
    assert (out == "SKIP") == expired


@pytest.mark.parametrize("text", ["독감 접종 2.5단계", "혜택 1.5배", "1:1 맞춤 상담"])
def test_decimals_are_not_dates(text):
    assert J.latest_date_in(text, TODAY) is None


def test_fallback_summary_does_not_cut_words():
    out = J.fallback_summary("‘활기찬 노후를 응원합니다’… 은평구, 제30회 노인의 날 기념행사 개최")
    assert out.endswith("…")
    assert "제30회 노" not in out             # 단어 중간에서 자르지 않음


# ── 진입점: 호출 실패는 ERROR, 재시도 ──────────────────────
def test_judge_notice_retries_then_succeeds(monkeypatch):
    import requests

    calls = iter([500, 200])

    def fake_post(*a, **k):
        r = requests.Response()
        r.status_code = next(calls)
        r._content = json.dumps({"response": _pass("💉 독감 무료접종 · 11월 30일까지")}).encode()
        return r

    monkeypatch.setattr(J.requests, "post", fake_post)
    monkeypatch.setattr(J, "OLLAMA_RETRY_WAIT", 0)
    assert J.judge_notice(TITLE, BODY, "노원구청") == "💉 독감 무료접종 · 11월 30일까지"


def test_judge_notice_error_recorded(monkeypatch):
    import requests

    def fail(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(J.requests, "post", fail)
    monkeypatch.setattr(J, "OLLAMA_RETRY_WAIT", 0)
    J.state["last_error"] = ""
    assert J.judge_notice(TITLE, BODY, "노원구청") == "ERROR"
    assert "ollama" in J.state["last_error"]
