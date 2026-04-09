import 'package:flutter/material.dart';

/// Senior-Friendly 글로벌 테마
/// architecture.md 5.1 원칙 엄격 적용:
/// - 초대형 폰트 (기본 대비 1.5배)
/// - 흰 배경 + 진한 검은색(#111111) 텍스트
/// - 고대비 파란색 포인트 컬러
/// - 넉넉한 터치 영역 (전역 Padding)
class SeniorTheme {
  SeniorTheme._();

  // ── 컬러 (figma.md 디자인 토큰 기준) ────
  static const Color primary      = Color(0xFF0056B3); // Primary Blue
  static const Color orangeAccent = Color(0xFFE65100); // Orange Accent (긴급 버튼, 배지)
  static const Color onPrimary    = Colors.white;
  static const Color background   = Color(0xFFF8F9FA); // Background
  static const Color surface      = Colors.white;       // 카드 배경 (흰색)
  static const Color textPrimary  = Color(0xFF111111);  // Body Text
  static const Color textSecond   = Color(0xFF555555);  // Sub Text
  static const Color divider      = Color(0xFFE0E0E0);  // Card Border
  static const Color badgeBokjiro    = Color(0xFF0056B3); // 복지로 = Primary Blue
  static const Color badgeSeongdong  = Color(0xFF2E7D32); // Green
  static const Color badgeGangbuk    = Color(0xFFB71C1C);

  // ── 폰트 크기 (figma.md 접근성 기준) ──
  // 본문 18px 이상, 제목 24px 이상 (WCAG AA)
  static const double fontXS  = 14.0;  // 캡션·배지 (비본문)
  static const double fontSM  = 18.0;  // 보조 본문 (figma: 18px 최소)
  static const double fontMD  = 20.0;  // 메인 본문
  static const double fontLG  = 24.0;  // 카드 제목 (figma: 24px 최소)
  static const double fontXL  = 28.0;  // 섹션 헤더
  static const double fontXXL = 34.0;  // 앱바/히어로 텍스트

  // ── 폰트 패밀리 ──────────────────────
  // Android: Roboto 시스템 기본, iOS: 시스템 폰트 폴백
  static const String fontFamily = 'Roboto';

  // ── 터치 영역 ─────────────────────────
  static const double touchPaddingV = 20.0; // 상하 패딩 (넉넉한 터치)
  static const double touchPaddingH = 16.0;
  static const double cardRadius    = 16.0;
  static const double cardElevation = 2.0;

  // ── ThemeData ─────────────────────────
  static ThemeData get themeData => ThemeData(
    useMaterial3: true,
    // fontFamily 미지정 → 시스템 기본 폰트 사용 (이모지 fallback 정상 동작)
    colorScheme: const ColorScheme.light(
      primary:    primary,
      onPrimary:  onPrimary,
      surface:    surface,
      onSurface:  textPrimary,
    ),
    scaffoldBackgroundColor: background,

    // 앱바
    appBarTheme: const AppBarTheme(
      backgroundColor:  primary,
      foregroundColor:  onPrimary,
      centerTitle:      true,
      elevation:        0,
      titleTextStyle:   TextStyle(
        color:      onPrimary,
        fontSize:   fontXL,
        fontWeight: FontWeight.bold,
        letterSpacing: 0.5,
      ),
    ),

    // 텍스트 테마 (전역 1.5배 폰트)
    textTheme: const TextTheme(
      // 공고 속보 제목 (카드 메인)
      titleLarge: TextStyle(
        fontSize:   fontLG,
        fontWeight: FontWeight.w800,
        color:      textPrimary,
        height:     1.4,
      ),
      // 보조 정보 (출처, 시간)
      bodyMedium: TextStyle(
        fontSize:   fontSM,
        color:      textSecond,
        height:     1.5,
      ),
      // 원본 제목 (서브텍스트)
      bodySmall: TextStyle(
        fontSize:   fontXS,
        color:      textSecond,
        height:     1.4,
      ),
      // 섹션 헤더
      headlineSmall: TextStyle(
        fontSize:   fontXL,
        fontWeight: FontWeight.bold,
        color:      textPrimary,
      ),
    ),

    // 하단 네비게이션 바
    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor:      background,
      selectedItemColor:    primary,
      unselectedItemColor:  textSecond,
      selectedLabelStyle:   TextStyle(fontSize: fontSM, fontWeight: FontWeight.bold),
      unselectedLabelStyle: TextStyle(fontSize: fontXS),
      showUnselectedLabels: true,
      type:                 BottomNavigationBarType.fixed,
      elevation:            8,
    ),

    // 카드 (흰 배경 + #E0E0E0 테두리 — figma.md Card Border 기준)
    cardTheme: CardThemeData(
      color:      surface,
      elevation:  0, // 테두리로 구분, 그림자 제거
      shape:      RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(cardRadius),
        side: const BorderSide(color: divider), // #E0E0E0
      ),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
    ),

    // ElevatedButton (신청하기 등)
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor:  primary,
        foregroundColor:  onPrimary,
        minimumSize:      const Size(double.infinity, 56), // 넓은 터치 영역
        shape:            RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        textStyle: const TextStyle(
          fontSize:   fontMD,
          fontWeight: FontWeight.bold,
        ),
      ),
    ),

    // 구분선
    dividerTheme: const DividerThemeData(
      color:     divider,
      thickness: 1,
      space:     0,
    ),
  );

  /// 출처별 배지 색상 반환
  /// 복지관은 소속 구청과 같은 색상으로 매핑 (수락/마포/도봉/은평/종로/약수/용산/서대문)
  static Color sourceColor(String source) {
    // 복지로 (중앙정부)
    if (source.contains('복지로')) return badgeBokjiro;
    // 노원구 (수락노인복지관 포함)
    if (source.contains('노원') || source.contains('수락')) return const Color(0xFF00695C);
    // 도봉구
    if (source.contains('도봉')) return const Color(0xFF5D4037);
    // 중랑구
    if (source.contains('중랑')) return const Color(0xFF6A1B9A);
    // 마포구
    if (source.contains('마포')) return const Color(0xFFC62828);
    // 은평구
    if (source.contains('은평')) return const Color(0xFF1565C0);
    // 성동구
    if (source.contains('성동')) return badgeSeongdong;
    // 강북구
    if (source.contains('강북')) return badgeGangbuk;
    // 종로구
    if (source.contains('종로')) return const Color(0xFFAD1457);
    // 중구 (약수노인복지관 포함)
    if (source.contains('중구') || source.contains('약수')) return const Color(0xFFEF6C00);
    // 용산구
    if (source.contains('용산')) return const Color(0xFF283593);
    // 서대문구
    if (source.contains('서대문')) return const Color(0xFF00838F);
    return badgeBokjiro; // 기본값
  }
}
