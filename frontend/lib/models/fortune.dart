/// 오늘의 운세 데이터 (v1.6, 설계: docs/운세-설계-2026-11-18.md)
///
/// 서버(backend/fortune.py)가 매일 `fortunes/{YYYY-MM-DD}` 문서에 60갑자 년주 전부의 운세를 써 둔다.
/// 앱은 그 문서 하나를 읽고, 기기에만 저장한 출생연도로 내 항목을 고른다 (출생연도는 서버로 보내지 않는다).
library;

/// 띠 12가지 (지지 순서: 자=쥐 … 해=돼지)
class Zodiac {
  final int branch;
  final String name;
  final String emoji;
  const Zodiac(this.branch, this.name, this.emoji);

  /// 이 띠의 년생 — 1930~1989년 (60갑자 한 바퀴, 띠마다 5개)
  List<int> get years => [for (var y = 1930; y <= 1989; y++) if ((y - 4) % 12 == branch) y];
}

const List<Zodiac> zodiacs = [
  Zodiac(0, '쥐', '🐭'), Zodiac(1, '소', '🐮'), Zodiac(2, '호랑이', '🐯'), Zodiac(3, '토끼', '🐰'),
  Zodiac(4, '용', '🐲'), Zodiac(5, '뱀', '🐍'), Zodiac(6, '말', '🐴'), Zodiac(7, '양', '🐑'),
  Zodiac(8, '원숭이', '🐵'), Zodiac(9, '닭', '🐔'), Zodiac(10, '개', '🐶'), Zodiac(11, '돼지', '🐷'),
];

/// 년주의 60갑자 인덱스 (서버 fortune.year_index와 같은 식)
int yearIndex(int birthYear) => (birthYear - 4) % 60;

Zodiac zodiacOf(int birthYear) => zodiacs[(birthYear - 4) % 12];

/// "56년생 원숭이띠"
String birthLabel(int birthYear) =>
    '${(birthYear % 100).toString().padLeft(2, '0')}년생 ${zodiacOf(birthYear).name}띠';

/// 오늘 날짜(한국 시간)의 문서 id — "2026-11-18". [addDays] 1이면 내일
String fortuneDocId([DateTime? now, int addDays = 0]) {
  final kst = (now ?? DateTime.now()).toUtc().add(Duration(hours: 9, days: addDays));
  return '${kst.year}-${kst.month.toString().padLeft(2, '0')}-${kst.day.toString().padLeft(2, '0')}';
}

class FortuneEntry {
  final String label;      // "☀️ 좋은 날"
  final String headline;
  final String keyword;
  final String health;
  final String family;
  final String money;
  final String color;
  final int number;

  // 볼거리 보강 (2026-11-21) — 예전 문서에는 없을 수 있어 모두 비어도 된다
  final int score;                 // 총운 점수 (0이면 없음)
  final int rank;                  // 오늘 내 띠 순위 1~12 (0이면 없음)
  final Map<String, int> stars;    // health·family·money·mind → 1~5
  final List<String> detail;       // 총운에 이어지는 문장들
  final String mind;
  final String direction;
  final String time;
  final String food;
  final int? goodWith;             // 잘 맞는 띠 (지지 인덱스)
  final int? careWith;             // 양보하면 좋은 띠

  const FortuneEntry({
    required this.label,
    required this.headline,
    required this.keyword,
    required this.health,
    required this.family,
    required this.money,
    required this.color,
    required this.number,
    this.score = 0,
    this.rank = 0,
    this.stars = const {},
    this.detail = const [],
    this.mind = '',
    this.direction = '',
    this.time = '',
    this.food = '',
    this.goodWith,
    this.careWith,
  });

  static int? _branch(Object? v) {
    final i = (v as num?)?.toInt();
    return (i != null && i >= 0 && i < 12) ? i : null;
  }

  factory FortuneEntry.fromMap(Map<String, dynamic> m) => FortuneEntry(
        label:    m['label']    as String? ?? '',
        headline: m['headline'] as String? ?? '',
        keyword:  m['keyword']  as String? ?? '',
        health:   m['health']   as String? ?? '',
        family:   m['family']   as String? ?? '',
        money:    m['money']    as String? ?? '',
        color:    m['color']    as String? ?? '',
        number:   (m['number'] as num?)?.toInt() ?? 0,
        score:    (m['score'] as num?)?.toInt() ?? 0,
        rank:     (m['rank'] as num?)?.toInt() ?? 0,
        stars: {
          for (final e in ((m['stars'] as Map?) ?? const {}).entries)
            e.key as String: ((e.value as num?)?.toInt() ?? 0).clamp(0, 5),
        },
        detail:    [for (final t in (m['detail'] as List?) ?? const []) t as String],
        mind:      m['mind']      as String? ?? '',
        direction: m['direction'] as String? ?? '',
        time:      m['time']      as String? ?? '',
        food:      m['food']      as String? ?? '',
        goodWith:  _branch(m['good_with']),
        careWith:  _branch(m['care_with']),
      );
}

/// 오늘의 띠 순위 한 줄
class RankRow {
  final int branch;       // 지지 인덱스 (zodiacs의 자리)
  final String comment;   // "하는 일마다 술술"
  const RankRow(this.branch, this.comment);
}

class FortuneDay {
  final String date;     // "2026-11-18"
  final String iljin;    // "병신"
  final Map<String, FortuneEntry> entries;   // 년주 인덱스("0"~"59") → 운세
  final List<RankRow> ranking;               // 1위부터 12줄 (예전 문서면 비어 있음)

  const FortuneDay({required this.date, required this.iljin, required this.entries, this.ranking = const []});

  factory FortuneDay.fromMap(Map<String, dynamic> m) => FortuneDay(
        date:  m['date']  as String? ?? '',
        iljin: m['iljin'] as String? ?? '',
        entries: {
          for (final e in ((m['entries'] as Map?) ?? const {}).entries)
            e.key as String: FortuneEntry.fromMap(Map<String, dynamic>.from(e.value as Map)),
        },
        ranking: [
          for (final r in (m['ranking'] as List?) ?? const [])
            if (r is Map && FortuneEntry._branch(r['branch']) != null)
              RankRow(FortuneEntry._branch(r['branch'])!, r['comment'] as String? ?? ''),
        ],
      );

  FortuneEntry? entryFor(int birthYear) => entries['${yearIndex(birthYear)}'];

  /// "11월 18일 (병신일)"
  String get dateLabel {
    final p = date.split('-');
    if (p.length != 3) return date;
    return '${int.parse(p[1])}월 ${int.parse(p[2])}일 ($iljin일)';
  }
}
