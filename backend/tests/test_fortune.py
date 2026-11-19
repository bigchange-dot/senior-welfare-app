"""오늘의 운세 (fortune.py, fortune_phrases.yaml) — 설계 문서 7장의 검사 항목"""

from datetime import date

import pytest

import fortune as F

PHRASES = F.load_phrases()


# ── 간지 기준값 ────────────────────────────────────────
@pytest.mark.parametrize("d, expected", [
    (date(2000, 1, 1), "무오"), (date(1900, 1, 1), "갑술"), (date(2026, 11, 18), "병신"),
])
def test_day_ganji(d, expected):
    assert F.ganji(F.day_index(d)) == expected


@pytest.mark.parametrize("year, expected", [(1984, "갑자"), (2026, "병오"), (1956, "병신")])
def test_year_ganji(year, expected):
    assert F.ganji(F.year_index(year)) == expected


def test_ten_gods_from_gap():
    # 갑(양목) 기준: 갑 비견, 을 겁재, 병 식신, 정 상관, 무 편재, 기 정재, 경 편관, 신 정관, 임 편인, 계 정인
    assert [F.ten_god(0, s) for s in range(10)] == F.TEN_GODS


def test_ten_gods_from_eul():
    # 을(음목) 기준: 을 비견, 갑 겁재, 정 식신, 병 상관, 기 편재, 무 정재, 신 편관, 경 정관, 계 편인, 임 정인
    assert [F.ten_god(1, s) for s in (1, 0, 3, 2, 5, 4, 7, 6, 9, 8)] == F.TEN_GODS


def test_hap_and_chung():
    haps = [(0, 1), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)]
    for a, b in haps:
        assert F.relation(a, b) == F.relation(b, a) == "합"
    for a in range(6):
        assert F.relation(a, a + 6) == "충"
    assert F.relation(0, 4) == "평"      # 자-진 (삼합이지만 육합·충은 아님)
    assert F.relation(3, 3) == "평"


def test_levels():
    assert F.level_of("편관", "합") == "좋음"
    assert F.level_of("정재", "충") == "차분히"
    assert F.level_of("정인", "평") == "좋음"
    assert F.level_of("겁재", "평") == "보통"


def test_push_years_and_message():
    assert F.push_years(date(2026, 11, 18)) == [1944, 1956, 1968]
    for d in [date(2026, 11, 18) + __import__("datetime").timedelta(days=i) for i in range(12)]:
        assert len(F.push_years(d)) == 3          # 띠마다 정확히 3개
    doc = F.build_day_doc(date(2026, 11, 18), PHRASES)
    assert doc["push"]["title"] == "🐵 오늘은 원숭이띠 날 · 오늘의 운세"
    assert doc["push"]["body"].startswith("44년생 ") and " · 56년생 " in doc["push"]["body"]


def test_same_day_same_result():
    a = F.build_day_doc(date(2026, 12, 1), PHRASES)
    b = F.build_day_doc(date(2026, 12, 1), PHRASES)
    assert a == b
    assert a != F.build_day_doc(date(2026, 12, 2), PHRASES)


def test_day_doc_shape():
    doc = F.build_day_doc(date(2026, 11, 18), PHRASES)
    assert doc["iljin"] == "병신" and doc["day_animal"] == "원숭이"
    assert sorted(doc["entries"], key=int) == [str(i) for i in range(60)]
    e = doc["entries"]["32"]      # 1956 병신생 — 오늘과 같은 간지 → 비견·평
    assert (e["god"], e["relation"]) == ("비견", "평")
    for key in ["level", "label", "headline", "keyword", "health", "family", "money", "color", "number"]:
        assert e[key], key


def test_level_mix_leans_good():
    """등급은 좋은 쪽으로 — 1년 치를 돌려 '차분히'가 1/12 안팎인지"""
    from collections import Counter
    from datetime import timedelta
    c = Counter()
    for i in range(365):
        d = date(2027, 1, 1) + timedelta(days=i)
        di = F.day_index(d)
        for y in range(60):
            c[F.level_of(F.ten_god(y % 10, di % 10), F.relation(y % 12, di % 12))] += 1
    total = sum(c.values())
    assert 0.07 < c["차분히"] / total < 0.10      # 충인 날만 — 12일 중 하루꼴 (설계 2.2)
    assert c["좋음"] / total > 0.35                # 합 + 평의 좋은 십신 4가지


# ── 문장 묶음 ──────────────────────────────────────────
def test_phrase_counts():
    for god in F.TEN_GODS:
        rels = PHRASES["headlines"][god]
        assert (len(rels["평"]), len(rels["합"]), len(rels["충"])) == (12, 6, 6), god
    for level in F.LEVELS:
        for area in F.AREAS:
            assert len(PHRASES["areas"][level][area]) == 10, (level, area)


def _all_texts():
    for god, rels in PHRASES["headlines"].items():
        for rel, items in rels.items():
            for it in items:
                yield f"{god}/{rel}", it["text"], it["keyword"]
    for level, areas in PHRASES["areas"].items():
        for area, items in areas.items():
            for t in items:
                yield f"{level}/{area}", t, None


def test_phrase_rules():
    for where, text, keyword in _all_texts():
        assert len(text) <= 40, (where, text)
        assert not any(w in text for w in F.FORBIDDEN_WORDS), (where, text)
        if keyword is not None:
            assert len(keyword) <= 6, (where, keyword)
            assert not any(w in keyword for w in F.FORBIDDEN_WORDS), (where, keyword)
    headlines = [t for w, t, k in _all_texts() if k is not None]
    assert all(t.endswith(("요.", "요")) for t in headlines)        # ~해요체


def test_push_body_fits_40_chars_every_day():
    from datetime import timedelta
    for i in range(120):
        doc = F.build_day_doc(date(2026, 11, 18) + timedelta(days=i), PHRASES)
        assert len(doc["push"]["body"]) <= 40, doc["push"]["body"]


# ── 실행: 문서 쓰기·알림 한 번만 ─────────────────────────
def test_run_daily_writes_two_days_and_pushes_once():
    from datetime import datetime, timezone
    from conftest import FakeDB
    db, sent = FakeDB(), []
    now = datetime(2026, 11, 17, 22, 0, tzinfo=timezone.utc)      # 한국 11/18 07:00
    r1 = F.run_daily(db, sent.append, now, PHRASES)
    r2 = F.run_daily(db, sent.append, now, PHRASES)               # 재시도
    assert (r1["date"], r1["pushed"], r2["pushed"]) == ("2026-11-18", True, False)
    assert len(sent) == 1 and sent[0]["iljin"] == "병신"
    assert sorted(db.collection("fortunes").docs) == ["2026-11-18", "2026-11-19"]
    assert db.collection("system_status").document("fortune").get().to_dict()["last_push_date"] == "2026-11-18"


def test_health_check_flags_missing_fortune_push():
    from datetime import datetime, timezone
    from conftest import FakeDB
    import monitoring
    db = FakeDB()
    ten_am = datetime(2026, 11, 18, 1, 0, tzinfo=timezone.utc)    # 한국 10:00
    assert monitoring.fortune_problems(db, ten_am) == []          # 배포 전: 검사 안 함
    db.collection("system_status").document("fortune").set({"last_push_date": "2026-11-17"})
    assert "운세" in monitoring.fortune_problems(db, ten_am)[0]
    db.collection("system_status").document("fortune").set({"last_push_date": "2026-11-18"})
    assert monitoring.fortune_problems(db, ten_am) == []
