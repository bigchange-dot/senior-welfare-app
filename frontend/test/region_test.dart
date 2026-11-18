import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:senior_welfare_app/regions.dart';
import 'package:senior_welfare_app/screens/region_picker_screen.dart';
import 'package:senior_welfare_app/services/region_prefs.dart';
import 'package:senior_welfare_app/theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 지역 목록·내 지역 설정·지역 선택 화면 (v1.5, 2026-11-18)
void main() {
  group('지역 목록', () {
    test('서울 25개 구, 경기 31개 시·군, id가 겹치지 않는다', () {
      expect(seoul.regions.length, 25);
      expect(gyeonggi.regions.length, 31);
      final ids = [for (final p in provinces) ...p.regions.map((r) => r.id)];
      expect(ids.toSet().length, ids.length);
    });

    test('id는 FCM 토픽 이름으로 쓸 수 있다', () {
      final topic = RegExp(r'^[a-zA-Z0-9\-_.~%]+$');
      for (final t in allTopics) {
        expect(topic.hasMatch(t), isTrue, reason: t);
      }
    });

    test('서울 id는 v1.4 토픽 이름 그대로 (기존 구독 유지)', () {
      for (final t in ['nowon', 'dobong', 'jungnang', 'mapo', 'eunpyeong', 'seongdong', 'gangbuk',
                       'jongno', 'junggu', 'yongsan', 'seodaemun', 'gangseo', 'dongjak', 'gwanak', 'yangcheon']) {
        expect(regionById(t)?.provinceId, 'seoul', reason: t);
      }
    });
  });

  group('내 지역 설정', () {
    test('v1.4 설정(selected_topics)을 옮긴다 — 복지로를 골랐던 사람은 복지로 알림 유지', () async {
      SharedPreferences.setMockInitialValues({
        'selected_topics':  ['nowon', 'bokjiro', 'mapo'],
        'selected_sources': ['노원구청', '복지로', '마포구청'],
      });
      await RegionPrefs.load();
      expect(RegionPrefs.selected.value, ['nowon', 'mapo']);
      expect(RegionPrefs.bokjiroNotif.value, isTrue);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getStringList('selected_topics'), isNull);
      expect(prefs.getStringList('selected_sources'), isNull);
    });

    test('v1.4에서 지역만 고른 사람은 복지로 알림을 받지 않던 대로', () async {
      SharedPreferences.setMockInitialValues({'selected_topics': ['dobong']});
      await RegionPrefs.load();
      expect(RegionPrefs.selected.value, ['dobong']);
      expect(RegionPrefs.bokjiroNotif.value, isFalse);
    });

    test('처음 설치: 지역 없음, 복지로 켬', () async {
      SharedPreferences.setMockInitialValues({});
      await RegionPrefs.load();
      expect(RegionPrefs.selected.value, isEmpty);
      expect(RegionPrefs.bokjiroNotif.value, isTrue);
    });

    test('알림 토픽: 지역 없으면 all(서울·경기 전부), 있으면 지역(+복지로)', () {
      expect(RegionPrefs.wantedTopics(regions: [], bokjiro: true), {'all'});
      expect(RegionPrefs.wantedTopics(regions: ['nowon', 'gg-suwon'], bokjiro: true), {'nowon', 'gg-suwon', 'bokjiro'});
      expect(RegionPrefs.wantedTopics(regions: ['nowon'], bokjiro: false), {'nowon'});
    });

    test('저장은 최대 3곳, 없는 id는 버린다', () async {
      SharedPreferences.setMockInitialValues({});
      await RegionPrefs.load();
      await RegionPrefs.setRegions(['nowon', 'xx', 'mapo', 'dobong', 'jongno']);
      expect(RegionPrefs.selected.value, ['nowon', 'mapo', 'dobong']);
    });
  });

  group('지역 선택 화면', () {
    Future<void> pumpPicker(WidgetTester tester,
        {double textScale = 1.0, Size size = const Size(360, 740), List<String> regions = const []}) async {
      tester.view.physicalSize = size * tester.view.devicePixelRatio;
      addTearDown(tester.view.resetPhysicalSize);
      SharedPreferences.setMockInitialValues({'selected_regions': regions});
      await RegionPrefs.load();
      await tester.pumpWidget(MaterialApp(
        theme: SeniorTheme.themeData,
        home: MediaQuery(
          data: MediaQueryData(size: size, textScaler: TextScaler.linear(textScale)),
          child: const RegionPickerScreen(),
        ),
      ));
    }

    testWidgets('공고가 있는 구를 누르면 내 지역이 되고, 다시 누르면 빠진다', (tester) async {
      await pumpPicker(tester);
      await tester.tap(find.text('노원구'));
      await tester.pump();
      expect(RegionPrefs.selected.value, ['nowon']);
      expect(find.text('완료 (1곳)'), findsOneWidget);

      await tester.tap(find.text('노원구').last);
      await tester.pump();
      expect(RegionPrefs.selected.value, isEmpty);
    });

    testWidgets('준비 중인 구는 고를 수 없고 안내가 뜬다', (tester) async {
      await pumpPicker(tester);
      await tester.tap(find.text('강남구'));
      await tester.pump();
      expect(RegionPrefs.selected.value, isEmpty);
      expect(find.text('강남구 공고는 아직 준비 중이에요.'), findsOneWidget);
    });

    testWidgets('4번째는 고를 수 없다', (tester) async {
      await pumpPicker(tester, size: const Size(800, 1400));
      for (final name in ['노원구', '도봉구', '마포구', '용산구']) {
        await tester.tap(find.text(name));
        await tester.pump();
      }
      expect(RegionPrefs.selected.value, ['nowon', 'dobong', 'mapo']);
      expect(find.textContaining('최대 3곳까지'), findsWidgets);
    });

    testWidgets('경기도 버튼을 누르면 경기 시·군이 보인다', (tester) async {
      await pumpPicker(tester);
      await tester.tap(find.text('경기도'));
      await tester.pump();
      expect(find.text('가평군'), findsOneWidget);
      expect(find.text('강남구'), findsNothing);
    });

    for (final scale in [1.0, 1.5, 2.0]) {
      testWidgets('좁은 폰 + 글자 $scale배에서 넘치지 않고 끝까지 스크롤된다', (tester) async {
        await pumpPicker(tester, textScale: scale, size: const Size(320, 640), regions: ['nowon', 'yongsan', 'jungnang']);
        expect(tester.takeException(), isNull);
        // 서울 마지막 구(중랑구)까지 스크롤해 누를 수 있어야 한다
        await tester.scrollUntilVisible(find.text('중랑구').last, 300, scrollable: find.byType(Scrollable).first);
        expect(tester.takeException(), isNull);
        await tester.scrollUntilVisible(find.text('경기도'), -300, scrollable: find.byType(Scrollable).first);
        await tester.tap(find.text('경기도'));
        await tester.pump();
        await tester.scrollUntilVisible(find.text('화성시'), 300, scrollable: find.byType(Scrollable).first);
        expect(tester.takeException(), isNull);
      });
    }
  });
}
