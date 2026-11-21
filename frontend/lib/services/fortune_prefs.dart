import 'dart:async';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/fortune.dart';
import 'fcm_service.dart';

/// 운세 설정 — 출생연도(띠)와 운세 알림 (v1.6)
///
/// 출생연도는 기기에만 저장한다. 서버·Analytics 어디로도 보내지 않는다 (설계 4.1, 4.5).
/// 운세 알림은 기본 꺼짐 — 첫 운세를 본 뒤 한 번 묻고 켠다 (사용자 결정 2026-11-18).
class FortunePrefs {
  FortunePrefs._();

  static const String _birthYearKey = 'fortune_birth_year';
  static const String _notifKey     = 'fortune_notif';
  static const String _askedKey     = 'fortune_notif_asked';

  static final ValueNotifier<int?> birthYear = ValueNotifier<int?>(null);
  static final ValueNotifier<bool> notif     = ValueNotifier<bool>(false);
  static bool notifAsked = false;

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    birthYear.value = prefs.getInt(_birthYearKey);
    notif.value     = prefs.getBool(_notifKey) ?? false;
    notifAsked      = prefs.getBool(_askedKey) ?? false;
  }

  static Future<void> setBirthYear(int year) async {
    birthYear.value = year;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_birthYearKey, year);
  }

  /// 운세 알림 켜기·끄기. 공고 알림 설정과 따로다 (토픽 `fortune`)
  static Future<void> setNotif(bool value) async {
    notif.value = value;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_notifKey, value);
    unawaited(FcmService.instance.syncSubscriptions());
  }

  static Future<void> markAsked() async {
    notifAsked = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_askedKey, true);
  }
}

/// 오늘 운세 문서 읽기 — 하루에 문서 1개. 같은 날은 메모리에 두고 다시 읽지 않는다
class FortuneRepo {
  FortuneRepo._();

  static FortuneDay? _cached;

  static Future<FortuneDay?> today() async {
    final id = fortuneDocId();
    if (_cached?.date == id) return _cached;
    final snap = await FirebaseFirestore.instance.collection('fortunes').doc(id).get();
    final data = snap.data();
    if (data == null) return null;
    return _cached = FortuneDay.fromMap(data);
  }

  /// 내일 운세 문서 — [내일 운세 미리 보기]를 누를 때만 읽는다 (서버가 오늘 07:00에 내일 것도 써 둔다)
  static FortuneDay? _cachedTomorrow;

  static Future<FortuneDay?> tomorrow() async {
    final id = fortuneDocId(null, 1);
    if (_cachedTomorrow?.date == id) return _cachedTomorrow;
    final snap = await FirebaseFirestore.instance.collection('fortunes').doc(id).get();
    final data = snap.data();
    if (data == null) return null;
    return _cachedTomorrow = FortuneDay.fromMap(data);
  }

  /// 오늘(한국 시간 0시 이후) 올라온 공고 수 — 운세 화면의 [오늘 새 공고 N건 보기]
  static Future<int> todayNoticeCount() async {
    final nowKst = DateTime.now().toUtc().add(const Duration(hours: 9));
    final midnightUtc = DateTime.utc(nowKst.year, nowKst.month, nowKst.day).subtract(const Duration(hours: 9));
    final agg = await FirebaseFirestore.instance
        .collection('welfare_notices')
        .where('timestamp', isGreaterThanOrEqualTo: Timestamp.fromDate(midnightUtc))
        .count()
        .get();
    return agg.count ?? 0;
  }
}
