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

/// 오늘 날짜(한국 시간)의 문서 id — "2026-11-18"
String fortuneDocId([DateTime? now]) {
  final kst = (now ?? DateTime.now()).toUtc().add(const Duration(hours: 9));
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

  const FortuneEntry({
    required this.label,
    required this.headline,
    required this.keyword,
    required this.health,
    required this.family,
    required this.money,
    required this.color,
    required this.number,
  });

  factory FortuneEntry.fromMap(Map<String, dynamic> m) => FortuneEntry(
        label:    m['label']    as String? ?? '',
        headline: m['headline'] as String? ?? '',
        keyword:  m['keyword']  as String? ?? '',
        health:   m['health']   as String? ?? '',
        family:   m['family']   as String? ?? '',
        money:    m['money']    as String? ?? '',
        color:    m['color']    as String? ?? '',
        number:   (m['number'] as num?)?.toInt() ?? 0,
      );
}

class FortuneDay {
  final String date;     // "2026-11-18"
  final String iljin;    // "병신"
  final Map<String, FortuneEntry> entries;   // 년주 인덱스("0"~"59") → 운세

  const FortuneDay({required this.date, required this.iljin, required this.entries});

  factory FortuneDay.fromMap(Map<String, dynamic> m) => FortuneDay(
        date:  m['date']  as String? ?? '',
        iljin: m['iljin'] as String? ?? '',
        entries: {
          for (final e in ((m['entries'] as Map?) ?? const {}).entries)
            e.key as String: FortuneEntry.fromMap(Map<String, dynamic>.from(e.value as Map)),
        },
      );

  FortuneEntry? entryFor(int birthYear) => entries['${yearIndex(birthYear)}'];

  /// "11월 18일 (병신일)"
  String get dateLabel {
    final p = date.split('-');
    if (p.length != 3) return date;
    return '${int.parse(p[1])}월 ${int.parse(p[2])}일 ($iljin일)';
  }
}
