"""출처 등록표 (sources.py) — 앱 지역 목록과 맞는지, 예전 토픽이 그대로인지 (v1.5, 2026-11-18)"""

import os
import re

import sources

REGIONS_DART = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "lib", "regions.dart")

# v1.4까지 notification_function.py의 SOURCE_TOPIC_MAP — 이미 구독한 사람의 알림이 끊기지 않게 그대로여야 한다
OLD_SOURCE_TOPIC_MAP = {
    "복지로": "bokjiro", "성동구청": "seongdong", "성동구 어르신일자리": "seongdong", "강북구청": "gangbuk",
    "노원구청": "nowon", "도봉구청": "dobong", "중랑구청": "jungnang", "마포구청": "mapo",
    "은평구청": "eunpyeong", "종로구청": "jongno", "중구청": "junggu", "용산구청": "yongsan",
    "서대문구청": "seodaemun", "강서구청": "gangseo", "동작구청": "dongjak", "관악구청": "gwanak",
    "양천구청": "yangcheon", "수락노인복지관": "nowon", "마포노인복지관": "mapo", "도봉노인복지관": "dobong",
    "은평노인복지관": "eunpyeong", "종로노인복지관": "jongno", "약수노인복지관": "junggu",
    "용산노인복지관": "yongsan", "서대문노인복지관": "seodaemun",
}
# v1.4까지 scraping_function.py의 WELFARE_CENTER_SOURCES
OLD_CENTERS = {"수락노인복지관", "마포노인복지관", "도봉노인복지관", "은평노인복지관", "종로노인복지관",
               "약수노인복지관", "용산노인복지관", "서대문노인복지관", "성동구 어르신일자리"}


def _app_regions():
    """regions.dart의 Region(id, 이름, 시도, available: true?) 목록"""
    text = open(REGIONS_DART, encoding="utf-8").read()
    rows = re.findall(r"Region\('([^']+)',\s*'[^']+',\s*'([^']+)'(,\s*available:\s*true)?\)", text)
    return {rid: (prov, bool(avail)) for rid, prov, avail in rows}


def test_앱_지역_목록을_읽을_수_있다():
    regions = _app_regions()
    assert sum(1 for p, _ in regions.values() if p == "seoul") == 25
    assert sum(1 for p, _ in regions.values() if p == "gyeonggi") == 31


def test_등록표의_지역은_모두_앱에_있다():
    app = _app_regions()
    for name, (region, _) in {**sources.SOURCES, **sources.LEGACY_SOURCES}.items():
        assert region == sources.NATIONAL or region in app, f"{name} → {region} 이 regions.dart에 없음"
        if region != sources.NATIONAL:
            assert sources.province_of(region) == app[region][0], name


def test_수집_중인_지역과_앱의_available이_같다():
    """출처를 붙이고 앱의 available을 안 켜면(또는 반대면) '준비 중' 표시가 틀린다"""
    app_available = {rid for rid, (_, avail) in _app_regions().items() if avail}
    assert app_available == sources.active_regions()


def test_예전_토픽과_복지관_구분이_그대로다():
    for name, topic in OLD_SOURCE_TOPIC_MAP.items():
        assert sources.region_of(name) == topic, name
    for name in OLD_SOURCE_TOPIC_MAP:
        assert sources.is_center(name) == (name in OLD_CENTERS), name


def test_시도_코드():
    assert sources.province_of("bokjiro") == "national"
    assert sources.province_of("nowon") == "seoul"
    assert sources.province_of("gg-suwon") == "gyeonggi"
    assert sources.province_of(None) is None
    assert sources.region_of("없는 출처") is None
    assert sources.is_center("없는 출처") is False
