import 'package:firebase_analytics/firebase_analytics.dart';
import 'package:flutter/foundation.dart';

/// 사용 측정 (Firebase Analytics, v1.6 — 설계 4.5)
///
/// 이벤트는 모두 여기서 보낸다. **띠·출생연도는 어떤 이벤트에도 넣지 않는다** ("기기에만" 원칙).
/// 디버그 빌드는 수집을 끈다 — 태블릿 시험이 숫자에 섞이지 않게.
class AnalyticsService {
  AnalyticsService._();

  /// 테스트에서 보낸 이벤트를 받아 보는 구멍. 지정하면 Firebase를 부르지 않는다
  @visibleForTesting
  static void Function(String name, Map<String, Object> params)? debugSink;

  static Future<void> init() async {
    if (kIsWeb) return;
    try {
      await FirebaseAnalytics.instance.setAnalyticsCollectionEnabled(!kDebugMode);
    } catch (e) {
      debugPrint('Analytics 초기화 실패(무시): $e');
    }
  }

  static void _log(String name, [Map<String, Object> params = const {}]) {
    final sink = debugSink;
    if (sink != null) {
      sink(name, params);
      return;
    }
    if (kIsWeb) return;
    try {
      FirebaseAnalytics.instance.logEvent(name: name, parameters: params.isEmpty ? null : params);
    } catch (e) {
      debugPrint('Analytics 이벤트 실패(무시) [$name]: $e');
    }
  }

  /// 운세 화면이 열림. source: notification / home_card / settings
  static void fortuneView(String source) => _log('fortune_view', {'source': source});

  /// 알림 받기 질문에 답함. answer: yes / no / no_permission
  static void fortuneNotifAnswer(String answer) => _log('fortune_notif_answer', {'answer': answer});

  static void fortuneOtherAnimal() => _log('fortune_other_animal');

  static void fortuneToNotices() => _log('fortune_to_notices');

  /// [내일 운세 미리 보기]를 누름 (볼거리 보강 2026-11-21)
  static void fortuneTomorrow() => _log('fortune_tomorrow');

  /// 공고를 엶. source: notification / list / bookmark
  static void noticeOpen(String source) => _log('notice_open', {'source': source});
}
