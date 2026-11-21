"""오늘의 운세 (v1.6, 설계: docs/운세-설계-2026-11-18.md)

하루 한 번 클라우드 예약 함수(main.fortune_function)가 오늘·내일 문서를 만들고 알림 1건을 보낸다.
AI는 쓰지 않는다 — 미리 검토한 문장 묶음(fortune_phrases.yaml)에서 고르기만 한다.

- 일진: (날짜 − 2000-01-01 일수 + 54) mod 60   (2000-01-01 무오, 1900-01-01 갑술, 2026-11-18 병신)
- 년주: (출생연도 − 4) mod 60                  (1984 갑자, 2026 병오, 1956 병신)
- 판정: 내 년간과 오늘 일간의 십신 + 내 년지와 오늘 일지의 합·충 → 등급 3가지 (좋은 쪽으로 기울게)
- 고르기: sha256("{날짜}|{년주}|{칸}") — 같은 날·같은 년주면 언제 계산해도 같은 결과
"""

import hashlib
import os
from datetime import date, timedelta

import yaml

STEMS = "갑을병정무기경신임계"
BRANCHES = "자축인묘진사오미신유술해"
ANIMALS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]
ANIMAL_EMOJI = ["🐭", "🐮", "🐯", "🐰", "🐲", "🐍", "🐴", "🐑", "🐵", "🐔", "🐶", "🐷"]

# 오행: 목 화 토 금 수 (천간 두 개씩)
ELEMENTS = ["목", "화", "토", "금", "수"]
_GENERATES = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}   # 생
_CONTROLS = {"목": "토", "토": "수", "수": "화", "화": "금", "금": "목"}    # 극

TEN_GODS = ["비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "정인"]
GOOD_GODS = {"정재", "정관", "정인", "식신"}

# 육합·충 (지지 인덱스 쌍)
_HAP = {frozenset(p) for p in [(0, 1), (2, 11), (3, 10), (4, 9), (5, 8), (6, 7)]}

LEVELS = ["좋음", "보통", "차분히"]
LEVEL_LABEL = {"좋음": "☀️ 좋은 날", "보통": "⛅ 무난한 날", "차분히": "🌤 천천히 가는 날"}
AREAS = ["건강", "가족", "재물", "마음"]
AREA_KEYS = ["health", "family", "money", "mind"]

# 행운의 색·숫자 (오행)
LUCKY = {"목": ("초록", (3, 8)), "화": ("빨강", (2, 7)), "토": ("노랑", (5, 10)),
         "금": ("흰색", (4, 9)), "수": ("남색", (1, 6))}

# 행운의 방향(오행)·시간 (볼거리 보강 2026-11-21)
LUCKY_DIRECTION = {"목": "동쪽", "화": "남쪽", "토": "남서쪽", "금": "서쪽", "수": "북쪽"}
LUCKY_TIMES = ["오전 7~9시", "오전 9~11시", "오전 11시~오후 1시", "오후 1~3시", "오후 3~5시", "오후 5~7시"]

# 원진·해 (지지 인덱스 쌍) — '양보하면 좋은 띠' 후보. 충과 함께 쓴다
_WONJIN = [(0, 7), (1, 6), (2, 9), (3, 8), (4, 11), (5, 10)]
_HAE = [(0, 7), (1, 6), (2, 5), (3, 4), (8, 11), (9, 10)]

# 알림에 띄울 년생: (올해 − 91) ~ (올해 − 56) — 36년 범위라 띠마다 정확히 3개
PUSH_AGE_MIN, PUSH_AGE_MAX = 56, 91

PHRASES_PATH = os.path.join(os.path.dirname(__file__), "fortune_phrases.yaml")
FORBIDDEN_WORDS = ["사고", "사망", "죽", "병원", "수술", "질병", "손실", "손해", "파산", "이별",
                   "다툼", "소송", "도난", "불운", "흉", "재앙", "위험"]

_EPOCH = date(2000, 1, 1)


# ── 간지 ─────────────────────────────────────────────
def day_index(d: date) -> int:
    """일진의 60갑자 인덱스"""
    return ((d - _EPOCH).days + 54) % 60


def year_index(year: int) -> int:
    """년주의 60갑자 인덱스"""
    return (year - 4) % 60


def ganji(i: int) -> str:
    return STEMS[i % 10] + BRANCHES[i % 12]


def stem_element(stem: int) -> str:
    return ELEMENTS[stem // 2]


def ten_god(my_stem: int, day_stem: int) -> str:
    """내 천간 기준 오늘 천간의 십신. 음양이 같으면 앞쪽(비견·식신·편재·편관·편인), 다르면 뒤쪽"""
    me, other = stem_element(my_stem), stem_element(day_stem)
    same_yinyang = (my_stem % 2) == (day_stem % 2)
    if me == other:
        pair = ("비견", "겁재")
    elif _GENERATES[me] == other:
        pair = ("식신", "상관")
    elif _CONTROLS[me] == other:
        pair = ("편재", "정재")
    elif _CONTROLS[other] == me:
        pair = ("편관", "정관")
    else:   # 오늘이 나를 생함
        pair = ("편인", "정인")
    return pair[0] if same_yinyang else pair[1]


def relation(my_branch: int, day_branch: int) -> str:
    """지지 관계: 육합이면 합, 충(여섯 칸 차이)이면 충, 나머지는 평"""
    if frozenset((my_branch, day_branch)) in _HAP:
        return "합"
    if (my_branch - day_branch) % 12 == 6:
        return "충"
    return "평"


def level_of(god: str, rel: str) -> str:
    if rel == "합":
        return "좋음"
    if rel == "충":
        return "차분히"
    return "좋음" if god in GOOD_GODS else "보통"


# ── 문장 고르기 ────────────────────────────────────────
def _pick(options: list, day: date, year_idx: int, slot: str):
    h = hashlib.sha256(f"{day.isoformat()}|{year_idx}|{slot}".encode("utf-8")).digest()
    return options[int.from_bytes(h[:8], "big") % len(options)]


def load_phrases(path: str = PHRASES_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def entry_for(day: date, year_idx: int, phrases: dict, ranking: list[int] | None = None) -> dict:
    """년주 하나의 오늘 운세"""
    di = day_index(day)
    ranking = ranking or animal_ranking(day)
    my_branch = year_idx % 12
    rank = ranking.index(my_branch) + 1
    god = ten_god(year_idx % 10, di % 10)
    rel = relation(year_idx % 12, di % 12)
    level = level_of(god, rel)
    head = _pick(phrases["headlines"][god][rel], day, year_idx, "headline")
    element = _pick(ELEMENTS, day, year_idx, "lucky")
    color, numbers = LUCKY[element]
    entry = {
        "level": level,
        "label": LEVEL_LABEL[level],
        "god": god,
        "relation": rel,
        "headline": head["text"],
        "keyword": head["keyword"],
        "color": color,
        "number": _pick(list(numbers), day, year_idx, "number"),
        # 볼거리 보강 (2026-11-21)
        "rank": rank,
        "score": score_of(level, rank, day, year_idx),
        "stars": stars_of(level, day, year_idx),
        "detail": [                               # 총운 이어지는 세 문장
            _pick(phrases["flow"][level], day, year_idx, "flow"),
            _pick(phrases["advice"][god], day, year_idx, "advice"),
            _pick(phrases["closing"][level], day, year_idx, "closing"),
        ],
        "direction": LUCKY_DIRECTION[element],
        "time": _pick(LUCKY_TIMES, day, year_idx, "time"),
        "food": _pick(phrases["foods"], day, year_idx, "food"),
        # 궁합은 띠가 같으면 같게 — 년주가 아니라 지지로 고른다 (지지 인덱스)
        "good_with": _pick(good_partners(my_branch), day, my_branch, "good-branch"),
        "care_with": _pick(care_partners(my_branch), day, my_branch, "care-branch"),
    }
    for area, key in zip(AREAS, AREA_KEYS):
        entry[key] = _pick(phrases["areas"][level][area], day, year_idx, area)
    return entry


def ranking_rows(day: date, ranking: list[int], phrases: dict) -> list[dict]:
    """띠 순위 12줄: 지지 인덱스 + 한마디 (1~4위 상, 5~8위 중, 9~12위 하)"""
    rows = []
    for t, tier in enumerate(["상", "중", "하"]):
        # 같은 날 같은 한마디가 두 번 나오지 않게, 묶음을 날짜로 섞어 앞에서부터 쓴다
        pool = sorted(phrases["rank_comments"][tier], key=lambda c: _hash_int(f"{day.isoformat()}|rank-comment|{c}"))
        for j, branch in enumerate(ranking[t * 4:t * 4 + 4]):
            rows.append({"branch": branch, "comment": pool[j]})
    return rows


# ── 띠 순위·궁합·점수 (볼거리 보강 2026-11-21) ─────────────
def _hash_int(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def animal_ranking(day: date) -> list[int]:
    """오늘의 띠 순위 — 지지 인덱스 12개를 1위부터.

    오늘 일지와 육합인 띠가 늘 1위, 충인 띠가 늘 12위 (등급 좋음·차분히와 맞춘다).
    삼합·오늘의 띠는 위쪽, 나머지는 날짜로 섞는다 — 띠마다 12일에 한 번은 1위가 된다."""
    db = day_index(day) % 12

    def weight(b: int) -> int:
        jitter = _hash_int(f"{day.isoformat()}|rank|{b}") % 1000
        rel = relation(b, db)
        if rel == "합":
            return 5000
        if rel == "충":
            return -1
        if b == db or (b - db) % 12 in (4, 8):   # 오늘의 띠, 삼합
            return 3000 + jitter
        return 1000 + jitter

    return sorted(range(12), key=weight, reverse=True)


def good_partners(branch: int) -> list[int]:
    """잘 맞는 띠 후보: 육합 하나 + 삼합 둘"""
    hap = next(b for b in range(12) if frozenset((branch, b)) in _HAP)
    return [hap, (branch + 4) % 12, (branch + 8) % 12]


def care_partners(branch: int) -> list[int]:
    """양보하면 좋은 띠 후보: 충 + 원진 + 해 (겹치면 하나로)"""
    out = [(branch + 6) % 12]
    for pairs in (_WONJIN, _HAE):
        for a, b in pairs:
            other = b if a == branch else a if b == branch else None
            if other is not None and other not in out:
                out.append(other)
    return out


def score_of(level: str, rank: int, day: date, year_idx: int) -> int:
    """총운 점수. 등급이 폭을 정하고, 띠 순위가 높을수록 그 안에서 올라간다 (좋음 80~98, 보통 62~80, 차분히 52~61)"""
    h = _hash_int(f"{day.isoformat()}|{year_idx}|score")
    if level == "차분히":
        return 52 + h % 10
    base = 80 if level == "좋음" else 62
    return base + round((12 - rank) * 1.4) + h % 3


def stars_of(level: str, day: date, year_idx: int) -> dict:
    """분야별 별 (5개 만점). 좋음 3~5, 보통 2~4, 차분히 2~3"""
    low, high = {"좋음": (3, 5), "보통": (2, 4), "차분히": (2, 3)}[level]
    return {key: low + _hash_int(f"{day.isoformat()}|{year_idx}|star|{key}") % (high - low + 1)
            for key in AREA_KEYS}


# ── 날짜 문서·알림 ─────────────────────────────────────
def push_years(day: date) -> list[int]:
    """오늘의 띠(오늘 일지)에 해당하는 년생 3개 — 올해 기준 만 56~91세 범위"""
    branch = day_index(day) % 12
    return [y for y in range(day.year - PUSH_AGE_MAX, day.year - PUSH_AGE_MIN + 1) if (y - 4) % 12 == branch]


def push_message(day: date, entries: dict) -> dict:
    """알림 제목·본문. 본문은 '44년생 반가운 소식 · 56년생 …' (40자 이내)"""
    branch = day_index(day) % 12
    title = f"{ANIMAL_EMOJI[branch]} 오늘은 {ANIMALS[branch]}띠 날 · 오늘의 운세"
    parts = [f"{y % 100:02d}년생 {entries[str(year_index(y))]['keyword']}" for y in push_years(day)]
    return {"title": title, "body": " · ".join(parts)}


def build_day_doc(day: date, phrases: dict) -> dict:
    """fortunes/{YYYY-MM-DD} 문서 — 60갑자 년주 전부 (앱은 이 문서 1개만 읽는다)"""
    di = day_index(day)
    ranking = animal_ranking(day)
    entries = {str(i): entry_for(day, i, phrases, ranking) for i in range(60)}
    return {
        "date": day.isoformat(),
        "iljin": ganji(di),
        "day_animal": ANIMALS[di % 12],
        "push": push_message(day, entries),
        "ranking": ranking_rows(day, ranking, phrases),
        "entries": entries,
    }


def days_to_write(today: date) -> list[date]:
    """오늘과 내일 — 07:00 전에 앱을 연 사람도 오늘 운세를 볼 수 있게 내일 것도 미리 쓴다"""
    return [today, today + timedelta(days=1)]


# ── 실행 (클라우드 예약 함수가 부른다) ─────────────────────
FORTUNE_COLLECTION = "fortunes"
STATUS_REF = ("system_status", "fortune")
TOPIC = "fortune"
KST_OFFSET = timedelta(hours=9)


def run_daily(db, send, now_utc, phrases: dict | None = None) -> dict:
    """오늘·내일 문서를 쓰고, 오늘 알림을 아직 안 보냈으면 1건 보낸다. 다시 불려도 두 번 보내지 않는다.

    db: Firestore 클라이언트, send(doc) -> None: 알림 발송 함수 (테스트에서 가짜로 바꿈)"""
    phrases = phrases or load_phrases()
    today = (now_utc + KST_OFFSET).date()
    docs = {}
    for day in days_to_write(today):
        docs[day] = build_day_doc(day, phrases)
        db.collection(FORTUNE_COLLECTION).document(day.isoformat()).set(docs[day])

    status_ref = db.collection(STATUS_REF[0]).document(STATUS_REF[1])
    snap = status_ref.get()
    status = (snap.to_dict() or {}) if snap.exists else {}
    pushed = False
    if status.get("last_push_date") != today.isoformat():
        send(docs[today])
        status["last_push_date"] = today.isoformat()
        pushed = True
    status["last_run_at"] = now_utc
    status_ref.set(status)
    return {"date": today.isoformat(), "pushed": pushed}


def send_push(doc: dict) -> None:
    """토픽 fortune으로 알림 1건 (설계 5.3). 12시간 안에 못 받으면 버린다 — 다음 날 어제 운세가 오지 않게"""
    from firebase_admin import messaging

    messaging.send(messaging.Message(
        notification=messaging.Notification(title=doc["push"]["title"], body=doc["push"]["body"]),
        data={"type": "fortune", "date": doc["date"]},
        topic=TOPIC,
        android=messaging.AndroidConfig(
            priority="high",
            ttl=timedelta(hours=12),
            notification=messaging.AndroidNotification(
                icon="ic_notification", color="#0056B3", channel_id="fortune", tag="fortune"),
        ),
        fcm_options=messaging.FCMOptions(analytics_label="fortune"),
    ))
