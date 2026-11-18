"""출처 등록표 (v1.5, 2026-11-18) — 출처 이름 → 지역 코드, 복지관 여부.

지역 코드는 세 곳에서 같은 값으로 쓰인다:
  - 공고 문서의 `region`·`province` 필드 (scraping_function.save_to_firestore)
  - FCM 지역 토픽 이름 (notification_function) — 서울 코드는 v1.4까지의 토픽 이름 그대로
  - 앱의 지역 id (frontend/lib/regions.dart) — tests/test_sources.py가 서로 맞는지 확인
예전에는 SOURCE_TOPIC_MAP(알림)·WELFARE_CENTER_SOURCES(수집)·앱의 칩 목록에 따로 적었다
(docs/구조-테스트-점검-2026-11-18.md 1번).

새 출처를 붙일 때: 여기 SOURCES에 추가 → 그 지역에 처음 생긴 출처면 regions.dart의 available을 true로.
"""

import board_sources

NATIONAL = "bokjiro"   # 복지로(중앙정부) 공고의 지역 코드·토픽

# 이름: (지역 코드, 복지관 여부). 복지관 출처는 제목 키워드 필터 없이 AI가 판정한다
SOURCES: dict[str, tuple[str, bool]] = {
    "복지로": (NATIONAL, False),

    # ── 서울 구청 ──
    "노원구청":   ("nowon", False),
    "도봉구청":   ("dobong", False),
    "중랑구청":   ("jungnang", False),
    "마포구청":   ("mapo", False),
    "은평구청":   ("eunpyeong", False),
    "성동구청":   ("seongdong", False),
    "종로구청":   ("jongno", False),
    "중구청":     ("junggu", False),
    "용산구청":   ("yongsan", False),
    "서대문구청": ("seodaemun", False),
    "양천구청":   ("yangcheon", False),

    # ── 서울 노인복지관·일자리 ──
    "수락노인복지관":       ("nowon", True),
    "도봉노인복지관":       ("dobong", True),
    "은평노인복지관":       ("eunpyeong", True),
    "종로노인복지관":       ("jongno", True),
    "약수노인복지관":       ("junggu", True),
    "용산노인복지관":       ("yongsan", True),
    "서대문노인복지관":     ("seodaemun", True),
    "성동구 어르신일자리":  ("seongdong", True),
}

# 지금은 수집하지 않지만 저장된 공고가 남아 있는 출처 — 지역 표시·알림 토픽에만 쓴다
LEGACY_SOURCES: dict[str, tuple[str, bool]] = {
    "강북구청":       ("gangbuk", False),   # 2026-11-17 수집 제외 (접속 끊김)
    "마포노인복지관": ("mapo", True),       # 봇 차단 403
    # 2026-05 추가 후 6개월 저장 0건 → 2026-11-18 그 구의 복지관으로 교체 (board_sources.SEOUL_BOARDS)
    "강서구청":       ("gangseo", False),
    "동작구청":       ("dongjak", False),
    "관악구청":       ("gwanak", False),
}

# 범용 목록 파서로 읽는 복지관·시니어클럽 (서울 교체분 + 경기) — 모두 복지관 출처
for _name, _region, _urls in board_sources.ALL_BOARDS:
    for _src in board_sources.BOARD_LABELS.get(_name, {_name: _name}).values():
        SOURCES[_src] = (_region, True)
for _name, _region, _cfg in board_sources.JSON_BOARDS:
    SOURCES[_name] = (_region, True)

_ALL = {**SOURCES, **LEGACY_SOURCES}


def region_of(source: str) -> str | None:
    """출처의 지역 코드. 등록표에 없으면 None (저장은 하되 지역 없음)"""
    entry = _ALL.get(source)
    return entry[0] if entry else None


def province_of(region: str | None) -> str | None:
    """지역 코드 → 시·도 코드 (national / seoul / gyeonggi)"""
    if not region:
        return None
    if region == NATIONAL:
        return "national"
    if region.startswith("gg-"):
        return "gyeonggi"
    return "seoul"


def is_center(source: str) -> bool:
    """복지관 출처인지 (제목 키워드 필터를 건너뛰고 AI가 판정)"""
    entry = _ALL.get(source)
    return bool(entry and entry[1])


def active_regions() -> set[str]:
    """지금 수집 중인 출처가 하나라도 있는 지역 (앱에서 '준비 중'이 아닌 지역)"""
    return {region for region, _ in SOURCES.values() if region != NATIONAL}
