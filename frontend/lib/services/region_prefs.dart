import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../regions.dart';
import 'fcm_service.dart';

/// '내 지역' 설정 — 홈(내 지역 칩)·찜(내 지역 공고)·알림이 함께 쓴다 (v1.5, 2026-11-18).
///
/// 예전(v1.4까지)에는 홈 칩과 설정의 알림 지역이 따로였고, 출처 이름('노원구청')과
/// 토픽('nowon')을 두 목록으로 저장했다. 지금은 지역 id 하나만 저장한다 ([Region.id]).
class RegionPrefs {
  RegionPrefs._();

  static const int maxRegions = 3;

  static const String _regionsKey = 'selected_regions';
  static const String _bokjiroKey = 'bokjiro_notif';

  /// 고른 지역 id 목록. 화면들은 이 값을 듣고 다시 그린다
  static final ValueNotifier<List<String>> selected = ValueNotifier<List<String>>(const []);

  /// 지역을 고른 사람도 복지로(전국) 공고 알림을 받을지 (지역을 안 고르면 'all'로 어차피 받음)
  static final ValueNotifier<bool> bokjiroNotif = ValueNotifier<bool>(true);

  /// 앱 시작 때 한 번. v1.4 설정이 있으면 옮긴다
  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    var ids = prefs.getStringList(_regionsKey);
    if (ids == null) {
      // v1.4: selected_topics에 서울 구 토픽('nowon' 등)이 들어 있다 — 지역 id와 같은 이름
      final oldTopics = prefs.getStringList('selected_topics') ?? const [];
      ids = oldTopics.where((t) => regionById(t) != null).take(maxRegions).toList();
      await prefs.setStringList(_regionsKey, ids);
      // 예전에는 지역을 고른 사람은 '복지로'를 따로 골라야 복지로 알림을 받았다 → 하던 대로 둔다
      if (ids.isNotEmpty) await prefs.setBool(_bokjiroKey, oldTopics.contains(nationalRegionId));
      await prefs.remove('selected_topics');
      await prefs.remove('selected_sources');
    }
    selected.value = ids.where((id) => regionById(id) != null).toList();
    bokjiroNotif.value = prefs.getBool(_bokjiroKey) ?? true;
  }

  static Future<void> setRegions(List<String> ids) async {
    final cleaned = ids.where((id) => regionById(id) != null).toSet().take(maxRegions).toList();
    selected.value = cleaned;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_regionsKey, cleaned);
    unawaited(FcmService.instance.syncSubscriptions());
  }

  static Future<void> setBokjiroNotif(bool value) async {
    bokjiroNotif.value = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_bokjiroKey, value);
    unawaited(FcmService.instance.syncSubscriptions());
  }

  /// 알림으로 받을 토픽. 지역을 안 고르면 'all'(서울·경기 전부), 고르면 그 지역(+복지로)
  static Set<String> wantedTopics({required List<String> regions, required bool bokjiro}) {
    if (regions.isEmpty) return {allTopic};
    return {...regions, if (bokjiro) nationalRegionId};
  }
}
