import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:timeago/timeago.dart' as timeago;

import 'package:senior_welfare_app/models/welfare_notice.dart';
import 'package:senior_welfare_app/theme.dart';
import 'package:senior_welfare_app/widgets/notice_card.dart';

/// 공고 카드 테스트 (2026-11-17, 전체 검토 6번)
///
/// 예전 템플릿 테스트(앱 전체를 띄움)는 Firebase 없이 실행돼 항상 실패했다.
/// 앱 점검(docs/앱-점검-2026-11-17.md)에서 고친 카드 동작을 고정한다.
/// 실행: cd frontend && flutter test
void main() {
  setUpAll(() => timeago.setLocaleMessages('ko', timeago.KoMessages()));

  final notice = WelfareNotice(
    id:         'n1',
    title:      '2026년 노년사회화교육사업 특별강좌(가족과 나의 행복한 노후를 위해 꼭! 알아야 할 신탁이야기) 참여자 모집',
    aiSummary:  '📚 가족과 행복한 노후를 위한 신탁 특별강좌 참여자 모집',
    source:     '서대문노인복지관',   // 가장 긴 출처 이름
    url:        'https://example.com',
    timestamp:  DateTime.now().subtract(const Duration(hours: 5)),
    isNotified: true,
  );

  /// 폭(논리 픽셀)·글자 배율을 정해 카드 하나를 그린다
  Future<void> pumpCard(
    WidgetTester tester, {
    double width = 400,
    double textScale = 1.0,
    VoidCallback? onTap,
    VoidCallback? onBookmark,
  }) async {
    tester.view.physicalSize     = Size(width * 3, 2400);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      theme: SeniorTheme.themeData,
      home: Builder(
        builder: (context) => MediaQuery(
          data:  MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: Scaffold(
            body: SingleChildScrollView(
              child: NoticeCard(
                notice:     notice,
                onTap:      onTap ?? () {},
                onBookmark: onBookmark ?? () {},
              ),
            ),
          ),
        ),
      ),
    ));
  }

  testWidgets('요약·제목·출처·시간을 보여 준다', (tester) async {
    await pumpCard(tester);
    // 요약 앞 이모지는 떼고, 분야는 출처 옆에 글자로 (v1.6 다듬기)
    expect(find.text('가족과 행복한 노후를 위한 신탁 특별강좌 참여자 모집'), findsOneWidget);
    expect(find.text(notice.title), findsOneWidget);
    expect(find.textContaining('서대문노인복지관', findRichText: true), findsOneWidget);
    expect(find.textContaining('교육', findRichText: true), findsWidgets);
    expect(find.text('5시간 전'), findsOneWidget);
  });

  testWidgets('찜 버튼은 카드 누름과 따로 동작하고 터치 영역이 48 이상', (tester) async {
    var taps = 0, bookmarks = 0;
    await pumpCard(tester, onTap: () => taps++, onBookmark: () => bookmarks++);

    final heart = find.byType(IconButton);
    expect(tester.getSize(heart).width,  greaterThanOrEqualTo(48));
    expect(tester.getSize(heart).height, greaterThanOrEqualTo(48));

    await tester.tap(heart);
    expect(bookmarks, 1);
    expect(taps, 0);          // 예전엔 28px 아이콘을 빗나가면 카드가 눌려 상세가 열렸음

    await tester.tap(find.text('가족과 행복한 노후를 위한 신탁 특별강좌 참여자 모집'));
    expect(taps, 1);
  });

  testWidgets('좁은 폰 + 글자 2배에서도 넘치지 않고 출처가 다 보인다', (tester) async {
    await pumpCard(tester, width: 360, textScale: 2.0);
    expect(tester.takeException(), isNull);   // RenderFlex overflow가 나면 여기서 잡힘
    final badgeFinder = find.textContaining('서대문노인복지관', findRichText: true);
    expect(badgeFinder, findsOneWidget);

    final badge = tester.renderObject<RenderParagraph>(badgeFinder);
    expect(badge.didExceedMaxLines, isFalse); // "서대문노…"처럼 잘리지 않음
  });

  test('요약 앞 이모지를 분야로 바꾼다', () {
    expect(splitSummary('💼 2027년 노인일자리 참여자 모집'), ('일자리', '2027년 노인일자리 참여자 모집'));
    expect(splitSummary('📢 11월 행사 안내'), (null, '11월 행사 안내'));          // 📢는 분야 없음
    expect(splitSummary('⚖️ 양성평등교육 참여자 모집'), ('권익', '양성평등교육 참여자 모집'));
    expect(splitSummary('스마트폰 교실 모집'), (null, '스마트폰 교실 모집'));     // 이모지 없는 요약
    expect(splitSummary('📢'), (null, '📢'));
  });
}
