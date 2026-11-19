import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:senior_welfare_app/models/fortune.dart';
import 'package:senior_welfare_app/screens/fortune_screen.dart';
import 'package:senior_welfare_app/services/analytics_service.dart';
import 'package:senior_welfare_app/services/fcm_service.dart';
import 'package:senior_welfare_app/services/fortune_prefs.dart';
import 'package:senior_welfare_app/theme.dart';
import 'package:senior_welfare_app/widgets/fortune_card.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 오늘의 운세 (v1.6) — 설계 문서 7장 프론트 항목
FortuneDay fakeDay() => FortuneDay.fromMap({
      'date': '2026-11-18',
      'iljin': '병신',
      'entries': {
        for (var i = 0; i < 60; i++)
          '$i': {
            'label': '☀️ 좋은 날',
            'headline': '뜻밖의 도움이 들어오는 날이에요. ($i)',
            'keyword': '뜻밖의 도움',
            'health': '아침 산책이 몸을 가볍게 해 줘요',
            'family': '오랜만에 자녀에게 먼저 전화해 보세요',
            'money': '작은 지출을 아끼면 마음이 편해요',
            'color': '노랑',
            'number': 5,
          },
      },
    });

void main() {
  final events = <(String, Map<String, Object>)>[];

  setUp(() {
    events.clear();
    AnalyticsService.debugSink = (name, params) => events.add((name, params));
  });
  tearDown(() => AnalyticsService.debugSink = null);

  Future<void> pumpScreen(WidgetTester tester, {
    Map<String, Object> prefs = const {},
    bool permission = true,
    double textScale = 1.0,
    Size size = const Size(360, 740),
    String source = 'home_card',
  }) async {
    tester.view.physicalSize = size * tester.view.devicePixelRatio;
    addTearDown(tester.view.resetPhysicalSize);
    SharedPreferences.setMockInitialValues(prefs);
    await FortunePrefs.load();
    await tester.pumpWidget(MaterialApp(
      theme: SeniorTheme.themeData,
      home: MediaQuery(
        data: MediaQueryData(size: size, textScaler: TextScaler.linear(textScale)),
        child: FortuneScreen(
          source: source,
          loadToday: () async => fakeDay(),
          loadNoticeCount: () async => 3,
          requestPermission: () async => permission,
          adsEnabled: false,
        ),
      ),
    ));
    await tester.pumpAndSettle();
  }

  /// 목록이 화면 밖 항목을 아직 만들지 않았을 수 있어, 보일 때까지 내린 뒤 누른다
  Future<void> scrollTo(WidgetTester tester, Finder finder) async {
    if (finder.evaluate().isEmpty) {
      await tester.scrollUntilVisible(finder, 200, scrollable: find.byType(Scrollable).first);
    }
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
  }

  Future<void> tapVisible(WidgetTester tester, Finder finder) async {
    await scrollTo(tester, finder);
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  group('띠·년생', () {
    test('년주 인덱스와 띠 (서버와 같은 식)', () {
      expect(yearIndex(1984), 0);
      expect(yearIndex(1956), 32);
      expect(zodiacOf(1956).name, '원숭이');
      expect(birthLabel(1956), '56년생 원숭이띠');
      expect(zodiacs[8].years, [1932, 1944, 1956, 1968, 1980]);
      for (final z in zodiacs) {
        expect(z.years.length, 5);
      }
    });

    test('문서 id는 한국 날짜', () {
      expect(fortuneDocId(DateTime.utc(2026, 11, 17, 22, 0)), '2026-11-18');   // 한국 07:00
      expect(fortuneDocId(DateTime.utc(2026, 11, 18, 14, 59)), '2026-11-18');
      expect(fortuneDocId(DateTime.utc(2026, 11, 18, 15, 0)), '2026-11-19');   // 한국 자정
    });

    testWidgets('처음엔 띠 → 년생을 고르고, 기기에 저장한 뒤 운세를 보여 준다', (tester) async {
      await pumpScreen(tester);
      expect(find.text('무슨 띠세요?'), findsOneWidget);
      await tapVisible(tester, find.text('원숭이띠'));
      await tapVisible(tester, find.text('1956년생 (56년생)'));
      expect(FortunePrefs.birthYear.value, 1956);
      expect((await SharedPreferences.getInstance()).getInt('fortune_birth_year'), 1956);
      expect(find.text('🐵 56년생 원숭이띠'), findsOneWidget);
      expect(find.text('뜻밖의 도움이 들어오는 날이에요. (32)'), findsOneWidget);
      await scrollTo(tester, find.text('오늘 새 공고 3건 보기'));
      await scrollTo(tester, find.text('재미로 보는 운세입니다'));
    });

    testWidgets('다른 띠 보기는 내 띠 설정을 바꾸지 않는다', (tester) async {
      await pumpScreen(tester, prefs: {'fortune_birth_year': 1956, 'fortune_notif_asked': true});
      await tapVisible(tester, find.text('다른 띠 보기'));
      await tapVisible(tester, find.text('쥐띠'));
      await tapVisible(tester, find.text('1948년생 (48년생)'));
      expect(find.text('🐭 48년생 쥐띠'), findsOneWidget);
      expect(FortunePrefs.birthYear.value, 1956);
      await tapVisible(tester, find.text('내 띠로'));
      expect(find.text('🐵 56년생 원숭이띠'), findsOneWidget);
    });
  });

  group('알림 받기 질문', () {
    Future<void> pickFirstTime(WidgetTester tester) async {
      await tapVisible(tester, find.text('원숭이띠'));
      await tapVisible(tester, find.text('1956년생 (56년생)'));
    }

    testWidgets('[네] → 운세 알림 켜짐, 다시 열면 묻지 않는다', (tester) async {
      await pumpScreen(tester);
      await pickFirstTime(tester);
      expect(find.text('내일 아침 7시에도 운세를 알려 드릴까요?'), findsOneWidget);
      await tapVisible(tester, find.text('네, 받을게요'));
      expect(FortunePrefs.notif.value, isTrue);
      expect(FortunePrefs.notifAsked, isTrue);
      expect(find.text('내일 아침 7시에도 운세를 알려 드릴까요?'), findsNothing);

      final prefs = await SharedPreferences.getInstance();
      await pumpScreen(tester, prefs: {
        'fortune_birth_year': prefs.getInt('fortune_birth_year')!,
        'fortune_notif': true,
        'fortune_notif_asked': true,
      });
      expect(find.text('내일 아침 7시에도 운세를 알려 드릴까요?'), findsNothing);
    });

    testWidgets('[괜찮아요] → 구독하지 않는다', (tester) async {
      await pumpScreen(tester);
      await pickFirstTime(tester);
      await tapVisible(tester, find.text('괜찮아요'));
      expect(FortunePrefs.notif.value, isFalse);
      expect(FortunePrefs.notifAsked, isTrue);
      expect(events.any((e) => e.$1 == 'fortune_notif_answer' && e.$2['answer'] == 'no'), isTrue);
    });

    testWidgets('[네]인데 휴대폰 알림 권한이 없으면 꺼진 채로 안내', (tester) async {
      await pumpScreen(tester, permission: false);
      await pickFirstTime(tester);
      await tapVisible(tester, find.text('네, 받을게요'));
      expect(FortunePrefs.notif.value, isFalse);
      expect(find.textContaining('휴대폰 설정에서 알림을 허용'), findsOneWidget);
      expect(events.any((e) => e.$2['answer'] == 'no_permission'), isTrue);
    });
  });

  group('알림 토픽', () {
    test('공고 알림과 운세 알림은 따로다', () {
      Set<String> w({required bool notices, required bool fortune, List<String> regions = const []}) =>
          FcmService.computeWanted(noticesEnabled: notices, regions: regions, bokjiro: true, fortune: fortune);
      expect(w(notices: true, fortune: false), {'all'});
      expect(w(notices: true, fortune: true), {'all', 'fortune'});
      expect(w(notices: false, fortune: true), {'fortune'});            // 공고를 꺼도 운세는 남는다
      expect(w(notices: false, fortune: false), isEmpty);
      expect(w(notices: true, fortune: false, regions: ['nowon']), {'nowon', 'bokjiro'});   // 운세를 꺼도 공고는 그대로
    });
  });

  group('측정', () {
    testWidgets('이벤트에 띠·년생이 들어가지 않는다', (tester) async {
      await pumpScreen(tester, source: 'notification');
      await tapVisible(tester, find.text('원숭이띠'));
      await tapVisible(tester, find.text('1956년생 (56년생)'));
      await tapVisible(tester, find.text('네, 받을게요'));
      await tapVisible(tester, find.text('다른 띠 보기'));
      expect(events.map((e) => e.$1), containsAll(['fortune_view', 'fortune_notif_answer', 'fortune_other_animal']));
      expect(events.first.$1, 'fortune_view');
      expect(events.first.$2, {'source': 'notification'});
      final dump = events.toString();
      for (final secret in ['1956', '56', '원숭이', '🐵', 'year', 'animal_name']) {
        expect(dump.contains(secret), isFalse, reason: secret);
      }
      for (final e in events) {
        expect(e.$2.keys.toSet().difference({'source', 'answer'}), isEmpty);
      }
    });
  });

  group('글자 크게', () {
    for (final scale in [1.0, 2.0]) {
      testWidgets('좁은 폰 + 글자 $scale배: 고르기·운세 화면이 넘치지 않는다', (tester) async {
        await pumpScreen(tester, textScale: scale, size: const Size(320, 640));
        expect(tester.takeException(), isNull);
        await tapVisible(tester, find.text('돼지띠'));
        expect(tester.takeException(), isNull);
        await tapVisible(tester, find.text('1947년생 (47년생)'));
        expect(tester.takeException(), isNull);
        await scrollTo(tester, find.text('재미로 보는 운세입니다'));
        expect(tester.takeException(), isNull);
      });

      testWidgets('홈 운세 카드 글자 $scale배', (tester) async {
        SharedPreferences.setMockInitialValues({'fortune_birth_year': 1956});
        await FortunePrefs.load();
        tester.view.physicalSize = const Size(320, 640) * tester.view.devicePixelRatio;
        addTearDown(tester.view.resetPhysicalSize);
        await tester.pumpWidget(MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(size: const Size(320, 640), textScaler: TextScaler.linear(scale)),
            child: Scaffold(body: FortuneCard(loadToday: () async => fakeDay())),
          ),
        ));
        await tester.pumpAndSettle();
        expect(find.text('☀️ 좋은 날 · 뜻밖의 도움'), findsOneWidget);
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('띠를 안 골랐으면 카드에 "내 띠 운세 보기"', (tester) async {
      SharedPreferences.setMockInitialValues({});
      await FortunePrefs.load();
      await tester.pumpWidget(const MaterialApp(home: Scaffold(body: FortuneCard())));
      expect(find.text('내 띠 운세 보기'), findsOneWidget);
    });
  });
}
