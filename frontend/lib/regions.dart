/// 지역 목록 — 앱에서 지역을 다루는 곳(홈·찜·설정·지역 선택·FCM 토픽)은 모두 여기를 쓴다 (v1.5, 2026-11-18).
///
/// [Region.id]는 세 가지로 함께 쓰인다:
///   - Firestore 공고 문서의 `region` 필드 값 (백엔드 `backend/sources.py`가 저장)
///   - FCM 토픽 이름 (서버는 공고를 `all` + 지역 토픽으로 보낸다)
///   - 기기에 저장하는 '내 지역' 값
/// 서울 id는 v1.4까지 쓰던 토픽 이름 그대로다 — 바꾸면 기존 구독이 끊긴다.
/// 백엔드 테스트(`backend/tests/test_sources.py`)가 이 파일의 id와 `sources.py`의 지역 코드를 맞춰 본다.
library;

class Region {
  final String id;
  final String name;        // 화면 표시 이름 (예: 노원구, 수원시)
  final String provinceId;
  /// 공고를 모으는 출처가 있는지. false면 지역 선택 화면에 '준비 중'으로 보인다
  final bool available;

  const Region(this.id, this.name, this.provinceId, {this.available = false});
}

class Province {
  final String id;
  final String name;        // 예: 서울특별시
  final String shortName;   // 예: 서울
  final List<Region> regions;

  const Province(this.id, this.name, this.shortName, this.regions);
}

/// 복지로(중앙정부) 공고의 지역 코드이자 토픽. 지역을 고른 사람도 따로 켜서 받을 수 있다
const String nationalRegionId = 'bokjiro';

/// 지역을 고르지 않은 사람이 받는 토픽 (서울·경기 모든 공고)
const String allTopic = 'all';

const Province seoul = Province('seoul', '서울특별시', '서울', [
  Region('gangnam',      '강남구',   'seoul'),
  Region('gangdong',     '강동구',   'seoul'),
  Region('gangbuk',      '강북구',   'seoul'),   // 수집 제외 (2026-11-17, 접속 끊김)
  Region('gangseo',      '강서구',   'seoul', available: true),   // 2026-11-18 구청 → 복지관 교체 (backend/board_sources.py)
  Region('gwanak',       '관악구',   'seoul', available: true),
  Region('gwangjin',     '광진구',   'seoul'),
  Region('guro',         '구로구',   'seoul'),
  Region('geumcheon',    '금천구',   'seoul'),
  Region('nowon',        '노원구',   'seoul', available: true),
  Region('dobong',       '도봉구',   'seoul', available: true),
  Region('dongdaemun',   '동대문구', 'seoul'),
  Region('dongjak',      '동작구',   'seoul', available: true),
  Region('mapo',         '마포구',   'seoul', available: true),
  Region('seodaemun',    '서대문구', 'seoul', available: true),
  Region('seocho',       '서초구',   'seoul'),
  Region('seongdong',    '성동구',   'seoul', available: true),
  Region('seongbuk',     '성북구',   'seoul'),
  Region('songpa',       '송파구',   'seoul'),
  Region('yangcheon',    '양천구',   'seoul', available: true),
  Region('yeongdeungpo', '영등포구', 'seoul'),
  Region('yongsan',      '용산구',   'seoul', available: true),
  Region('eunpyeong',    '은평구',   'seoul', available: true),
  Region('jongno',       '종로구',   'seoul', available: true),
  Region('junggu',       '중구',     'seoul', available: true),
  Region('jungnang',     '중랑구',   'seoul', available: true),
]);

/// 경기 31개 시·군. 출처 조사: docs/gyeonggi/gyeonggi_centers.yaml, 수집 출처: backend/board_sources.py
/// (수집은 맥 실행 환경변수 GYEONGGI=1일 때만 — v1.5 출시 때 켠다)
const Province gyeonggi = Province('gyeonggi', '경기도', '경기', [
  Region('gg-gapyeong',    '가평군',   'gyeonggi', available: true),
  Region('gg-goyang',      '고양시',   'gyeonggi', available: true),
  Region('gg-gwacheon',    '과천시',   'gyeonggi', available: true),
  Region('gg-gwangmyeong', '광명시',   'gyeonggi'),
  Region('gg-gwangju',     '광주시',   'gyeonggi', available: true),
  Region('gg-guri',        '구리시',   'gyeonggi'),
  Region('gg-gunpo',       '군포시',   'gyeonggi', available: true),
  Region('gg-gimpo',       '김포시',   'gyeonggi', available: true),
  Region('gg-namyangju',   '남양주시', 'gyeonggi', available: true),
  Region('gg-dongducheon', '동두천시', 'gyeonggi'),
  Region('gg-bucheon',     '부천시',   'gyeonggi', available: true),
  Region('gg-seongnam',    '성남시',   'gyeonggi', available: true),
  Region('gg-suwon',       '수원시',   'gyeonggi', available: true),
  Region('gg-siheung',     '시흥시',   'gyeonggi'),
  Region('gg-ansan',       '안산시',   'gyeonggi'),
  Region('gg-anseong',     '안성시',   'gyeonggi', available: true),
  Region('gg-anyang',      '안양시',   'gyeonggi'),
  Region('gg-yangju',      '양주시',   'gyeonggi', available: true),
  Region('gg-yangpyeong',  '양평군',   'gyeonggi', available: true),
  Region('gg-yeoju',       '여주시',   'gyeonggi', available: true),
  Region('gg-yeoncheon',   '연천군',   'gyeonggi'),
  Region('gg-osan',        '오산시',   'gyeonggi', available: true),
  Region('gg-yongin',      '용인시',   'gyeonggi', available: true),
  Region('gg-uiwang',      '의왕시',   'gyeonggi', available: true),
  Region('gg-uijeongbu',   '의정부시', 'gyeonggi', available: true),
  Region('gg-icheon',      '이천시',   'gyeonggi', available: true),
  Region('gg-paju',        '파주시',   'gyeonggi', available: true),
  Region('gg-pyeongtaek',  '평택시',   'gyeonggi', available: true),
  Region('gg-pocheon',     '포천시',   'gyeonggi', available: true),
  Region('gg-hanam',       '하남시',   'gyeonggi', available: true),
  Region('gg-hwaseong',    '화성시',   'gyeonggi', available: true),
]);

const List<Province> provinces = [seoul, gyeonggi];

final Map<String, Region> _byId = {
  for (final p in provinces)
    for (final r in p.regions) r.id: r,
};

Region? regionById(String id) => _byId[id];

/// 앱이 구독할 수 있는 모든 토픽 (알림 끄기 때 전부 해지하는 데 씀)
List<String> get allTopics => [allTopic, nationalRegionId, ..._byId.keys];

/// 화면 표시용 이름 목록. 예: ['노원구', '수원시'] → '노원구 · 수원시'
String regionNames(Iterable<String> ids) =>
    ids.map((id) => regionById(id)?.name ?? id).join(' · ');
