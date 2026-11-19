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
AREAS = ["건강", "가족", "재물"]

# 행운의 색·숫자 (오행)
LUCKY = {"목": ("초록", (3, 8)), "화": ("빨강", (2, 7)), "토": ("노랑", (5, 10)),
         "금": ("흰색", (4, 9)), "수": ("남색", (1, 6))}

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


def entry_for(day: date, year_idx: int, phrases: dict) -> dict:
    """년주 하나의 오늘 운세"""
    di = day_index(day)
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
    }
    for area, key in zip(AREAS, ["health", "family", "money"]):
        entry[key] = _pick(phrases["areas"][level][area], day, year_idx, area)
    return entry


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
    entries = {str(i): entry_for(day, i, phrases) for i in range(60)}
    return {
        "date": day.isoformat(),
        "iljin": ganji(di),
        "day_animal": ANIMALS[di % 12],
        "push": push_message(day, entries),
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
