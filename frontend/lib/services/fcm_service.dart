import 'dart:async';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// FCM 수신 & Deep Linking 처리 서비스
/// architecture.md 5.3 원칙:
/// - 앱 종료 상태 알림 클릭 → 해당 공고 WebView로 즉시 이동
/// - 백그라운드 알림 클릭 → onMessageOpenedApp 스트림 처리
class FcmService {
  FcmService._();
  static final FcmService instance = FcmService._();

  FirebaseMessaging? get _fcm {
    if (kIsWeb) return null;
    try {
      return FirebaseMessaging.instance;
    } catch (e) {
      return null;
    }
  }

  StreamSubscription? _onMessageOpenedSub;

  // 딥링크 라우팅을 위한 글로벌 네비게이터 키
  static final GlobalKey<NavigatorState> navigatorKey =
      GlobalKey<NavigatorState>();

  /// 초기화: 권한 요청 + 토픽 구독 + 핸들러 등록
  Future<void> initialize() async {
    final fcm = _fcm;
    if (fcm == null) return;

    try {
      // 1. 알림 권한 요청
      final settings = await fcm.requestPermission(
        alert:     true,
        badge:     true,
        sound:     true,
        provisional: false,
      );
      debugPrint('🔔 FCM 권한: ${settings.authorizationStatus}');

      // 2. 기본 토픽 구독 (전체 알림)
      await fcm.subscribeToTopic('all');
      debugPrint('✅ FCM 토픽 구독: all');

      // 3. 앱 완전 종료 상태에서 알림 클릭하여 진입한 경우
      final initialMessage = await fcm.getInitialMessage();
      if (initialMessage != null) {
        _handleMessage(initialMessage);
      }

      // 4. 백그라운드 상태에서 알림 클릭
      _onMessageOpenedSub = FirebaseMessaging.onMessageOpenedApp
          .listen(_handleMessage);

      // 5. 포그라운드 알림 (Android: 직접 표시, iOS: 자동)
      FirebaseMessaging.onMessage.listen((RemoteMessage message) {
        debugPrint('📩 포그라운드 FCM: ${message.notification?.title}');
        // 포그라운드는 앱 내 스낵바나 배너로 표시 (선택사항)
      });
    } catch (e) {
      debugPrint('FcmService initialize 오류: $e');
    }
  }

  /// FCM 메시지 → WebView 라우팅
  void _handleMessage(RemoteMessage message) {
    final data  = message.data;
    final url   = data['url']   as String?;
    final docId = data['doc_id'] as String?;

    debugPrint('🔗 딥링크 처리: url=$url, docId=$docId');

    if (url != null && url.isNotEmpty) {
      navigatorKey.currentState?.pushNamed(
        '/webview',
        arguments: {
          'url':    url,
          'doc_id': docId ?? '',
        },
      );
    }
  }

  /// 지역 토픽 구독 변경
  Future<void> updateRegionTopic({
    String? oldTopic,
    String? newTopic,
  }) async {
    final fcm = _fcm;
    if (fcm == null) return;

    try {
      if (oldTopic != null && oldTopic.isNotEmpty) {
        await fcm.unsubscribeFromTopic(oldTopic);
        debugPrint('🚫 FCM 토픽 해지: $oldTopic');
      }
      if (newTopic != null && newTopic.isNotEmpty) {
        await fcm.subscribeToTopic(newTopic);
        debugPrint('✅ FCM 토픽 구독: $newTopic');
      }
    } catch (e) {
      debugPrint('FcmService updateRegionTopic 오류: $e');
    }
  }

  /// 모든 알림 구독 해지 (알림 OFF)
  Future<void> unsubscribeAll() async {
    final fcm = _fcm;
    if (fcm == null) return;

    try {
      await fcm.unsubscribeFromTopic('all');
      await fcm.unsubscribeFromTopic('bokjiro');
      await fcm.unsubscribeFromTopic('seongdong');
      await fcm.unsubscribeFromTopic('gangbuk');
      debugPrint('🚫 모든 FCM 토픽 해지');
    } catch (e) {
      debugPrint('FcmService unsubscribeAll 오류: $e');
    }
  }

  void dispose() {
    _onMessageOpenedSub?.cancel();
  }
}

/// 백그라운드 메시지 핸들러 (top-level 함수 필수)
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  debugPrint('📩 백그라운드 FCM: ${message.notification?.title}');
}
