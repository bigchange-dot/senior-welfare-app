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
    for key in ["level", "label", "headline", "keyword", "health", "family", "money", "mind", "color", "number",
                "score", "stars", "detail", "direction", "time", "food", "rank"]:
        assert e[key], key
    assert len(e["detail"]) == 3 and set(e["stars"]) == set(F.AREA_KEYS)


# ── 볼거리 보강 (2026-11-21): 띠 순위·점수·별·궁합 ───────────
def _days(n, start=date(2027, 1, 1)):
    from datetime import timedelta
    return [start + timedelta(days=i) for i in range(n)]


def test_ranking_is_a_permutation_and_fair():
    from collections import Counter
    firsts, lasts = Counter(), Counter()
    for d in _days(120):
        r = F.animal_ranking(d)
        assert sorted(r) == list(range(12))
        db = F.day_index(d) % 12
        assert F.relation(r[0], db) == "합" and F.relation(r[-1], db) == "충"
        firsts[r[0]] += 1
        lasts[r[-1]] += 1
    assert set(firsts.values()) == {10} and set(lasts.values()) == {10}     # 띠마다 12일에 한 번씩 1위·12위


def test_ranking_rows_in_doc():
    doc = F.build_day_doc(date(2026, 11, 18), PHRASES)
    rows = doc["ranking"]
    assert [r["branch"] for r in rows] == F.animal_ranking(date(2026, 11, 18))
    assert all(r["comment"] and len(r["comment"]) <= 16 for r in rows)
    assert len({r["comment"] for r in rows}) == 12                 # 한마디가 겹치지 않는다
    for i, e in doc["entries"].items():
        assert rows[e["rank"] - 1]["branch"] == int(i) % 12       # 내 순위 = 순위표의 내 띠 자리


def test_score_and_stars_follow_level():
    ranges = {"좋음": (80, 98), "보통": (62, 80), "차분히": (52, 61)}
    star_ranges = {"좋음": (3, 5), "보통": (2, 4), "차분히": (2, 3)}
    seen = set()
    for d in _days(60):
        doc = F.build_day_doc(d, PHRASES)
        for e in doc["entries"].values():
            lo, hi = ranges[e["level"]]
            assert lo <= e["score"] <= hi, e
            slo, shi = star_ranges[e["level"]]
            assert all(slo <= v <= shi for v in e["stars"].values()), e
            seen.add(e["score"])
        first = [e for e in doc["entries"].values() if e["rank"] == 1]
        assert all(e["level"] == "좋음" and e["score"] >= 95 for e in first)      # 1위 띠는 늘 좋은 날
    assert len(seen) > 25                                                         # 점수가 날마다 다양하다


def test_partners():
    assert F.good_partners(0) == [1, 4, 8]            # 쥐: 소(육합), 용·원숭이(삼합)
    assert F.care_partners(0) == [6, 7]               # 쥐: 말(충), 양(원진·해)
    for b in range(12):
        assert b not in F.good_partners(b) + F.care_partners(b)
        assert not set(F.good_partners(b)) & set(F.care_partners(b))
    doc = F.build_day_doc(date(2026, 11, 18), PHRASES)
    for i, e in doc["entries"].items():
        same = doc["entries"][str((int(i) + 12) % 60)]            # 같은 띠 다른 년생
        assert (e["good_with"], e["care_with"]) == (same["good_with"], same["care_with"])
        assert e["good_with"] in F.good_partners(int(i) % 12)


def test_lucky_items():
    doc = F.build_day_doc(date(2026, 11, 18), PHRASES)
    for e in doc["entries"].values():
        assert e["direction"] in F.LUCKY_DIRECTION.values()
        assert e["time"] in F.LUCKY_TIMES and e["food"] in PHRASES["foods"]


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
        assert len(PHRASES["flow"][level]) == 12 and len(PHRASES["closing"][level]) == 8, level
    for god in F.TEN_GODS:
        assert len(PHRASES["advice"][god]) == 6, god
    assert all(len(v) == 8 for v in PHRASES["rank_comments"].values()) and len(PHRASES["foods"]) == 20


def _all_texts():
    for god, rels in PHRASES["headlines"].items():
        for rel, items in rels.items():
            for it in items:
                yield f"{god}/{rel}", it["text"], it["keyword"]
    for level, areas in PHRASES["areas"].items():
        for area, items in areas.items():
            for t in items:
                yield f"{level}/{area}", t, None
    for pool in ("flow", "advice", "closing", "rank_comments"):
        for group, items in PHRASES[pool].items():
            for t in items:
                yield f"{pool}/{group}", t, None
    for t in PHRASES["foods"]:
        yield "foods", t, None


def test_phrase_rules():
    for where, text, keyword in _all_texts():
        assert len(text) <= 40, (where, text)
        assert not any(w in text for w in F.FORBIDDEN_WORDS), (where, text)
        if keyword is not None:
            assert len(keyword) <= 6, (where, keyword)
            assert not any(w in keyword for w in F.FORBIDDEN_WORDS), (where, keyword)
    headlines = [t for w, t, k in _all_texts() if k is not None]
    assert all(t.endswith(("요.", "요")) for t in headlines)        # ~해요체
    # 총운으로 이어 붙는 문장은 마침표로 끝나야 한 문단으로 읽힌다
    for w, t, k in _all_texts():
        if w.split("/")[0] in ("flow", "advice", "closing"):
            assert t.endswith("요."), (w, t)
    texts = [t for w, t, k in _all_texts()]
    assert len(texts) == len(set(texts))                            # 같은 문장이 두 번 없다


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
