import 'dart:async';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../regions.dart';
import 'region_prefs.dart';

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

  /// 지금 구독 중인 토픽을 기기에 적어 둔다 — 바뀐 것만 구독·해지하려고 (v1.5).
  /// 토픽이 58개(서울 25 + 경기 31 + all + 복지로)라 매번 전부 해지하면 앱 시작이 느려진다
  static const String _subscribedKey = 'fcm_topics';

  /// v1.4까지 쓰던 토픽 — 적어 둔 목록이 없는(업데이트 직후) 기기는 이 중 무엇을 구독했는지 모른다
  static const List<String> _legacyTopics = [
    'all', 'bokjiro', 'nowon', 'dobong', 'jungnang', 'mapo', 'eunpyeong',
    'seongdong', 'gangbuk', 'jongno', 'junggu', 'yongsan', 'seodaemun',
    'gangseo', 'dongjak', 'gwanak', 'yangcheon',
  ];

  // 딥링크 라우팅을 위한 글로벌 네비게이터 키
  static final GlobalKey<NavigatorState> navigatorKey =
      GlobalKey<NavigatorState>();

  /// 초기화: 권한 요청 + 토픽 구독 + 핸들러 등록
  ///
  /// 단계마다 예외를 따로 잡는다 (2026-11-17 수정). 예전에는 한 try 안에 있어서
  /// 디버그용 getToken()이 실패하면(FIS_AUTH_ERROR, 첫 실행 오프라인 등) 토픽 구독과
  /// 알림 탭 처리기 등록까지 통째로 건너뛰었다.
  Future<void> initialize() async {
    final fcm = _fcm;
    if (fcm == null) return;

    // 1. 알림 권한 요청
    try {
      final settings = await fcm.requestPermission(
        alert:     true,
        badge:     true,
        sound:     true,
        provisional: false,
      );
      debugPrint('🔔 FCM 권한: ${settings.authorizationStatus}');
    } catch (e) {
      debugPrint('FCM 권한 요청 실패: $e');
    }

    // 2. FCM 토큰 출력 (디버그 확인용 — 실패해도 아래 단계는 계속)
    if (kDebugMode) {
      try {
        debugPrint('📱 FCM 토큰: ${await fcm.getToken()}');
      } catch (e) {
        debugPrint('FCM 토큰 조회 실패(무시): $e');
      }
    }

    // 3. 알림 탭 처리기 등록 (백그라운드 상태에서 알림 클릭 / 포그라운드 수신)
    _onMessageOpenedSub = FirebaseMessaging.onMessageOpenedApp
        .listen(_handleMessage);
    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      debugPrint('📩 포그라운드 FCM: ${message.notification?.title}');
    });

    // 4. 앱 완전 종료 상태에서 알림 클릭하여 진입한 경우
    try {
      final initialMessage = await fcm.getInitialMessage();
      if (initialMessage != null) _handleMessage(initialMessage);
    } catch (e) {
      debugPrint('FCM 시작 메시지 조회 실패: $e');
    }

    // 5. 저장된 설정(알림 ON/OFF, 선택 지역)에 맞춰 토픽 구독 동기화 (토픽별 예외는 내부에서 처리)
    await syncSubscriptions();
  }

  /// FCM 메시지 → WebView 라우팅
  ///
  /// 앱이 꺼진 상태에서 알림으로 시작하면 이 함수가 첫 화면보다 먼저 불려
  /// 네비게이터가 아직 없다 (예전엔 그대로 무시돼 공고 대신 홈이 열렸음, 2026-11-17 수정).
  /// 그럴 때는 첫 화면이 그려진 뒤 다시 시도한다.
  void _handleMessage(RemoteMessage message, [int attempt = 0]) {
    final data  = message.data;
    final url   = data['url']   as String?;
    final docId = data['doc_id'] as String?;

    if (url == null || url.isEmpty) return;

    final nav = navigatorKey.currentState;
    if (nav == null) {
      if (attempt < 10) {
        WidgetsBinding.instance.addPostFrameCallback(
          (_) => _handleMessage(message, attempt + 1),
        );
        WidgetsBinding.instance.ensureVisualUpdate();   // 프레임이 예약돼 있지 않으면 예약
      }
      return;
    }

    debugPrint('🔗 딥링크 처리: url=$url, docId=$docId');
    nav.pushNamed(
      '/webview',
      arguments: {
        'url':    url,
        'doc_id': docId ?? '',
      },
    );
  }

  /// 저장된 설정에 맞춰 토픽 구독을 맞춤 (앱 시작·지역 변경·알림 ON 시 호출)
  ///
  /// 중복 알림 방지: 서버는 모든 공고를 `all`과 지역 토픽에 동시 발송하므로
  /// 지역을 하나라도 고른 사용자는 `all`을 해지하고 지역 토픽(+복지로)만 구독한다.
  /// 지역을 고르지 않은 사용자만 `all`(서울·경기 전부)을 구독한다.
  Future<void> syncSubscriptions() async {
    final fcm = _fcm;
    if (fcm == null) return;

    try {
      final prefs   = await SharedPreferences.getInstance();
      final enabled = prefs.getBool('notif_enabled') ?? true;
      if (!enabled) {
        await unsubscribeAll();
        return;
      }
      final wanted = RegionPrefs.wantedTopics(
        regions: RegionPrefs.selected.value,
        bokjiro: RegionPrefs.bokjiroNotif.value,
      );
      final previous = (prefs.getStringList(_subscribedKey) ?? _legacyTopics).toSet();

      // 받을 토픽을 먼저, 한꺼번에 구독한 뒤 안 쓰는 토픽을 한꺼번에 해지한다 (2026-11-19).
      // 예전엔 하나씩 차례로(해지 16개 → 구독) 해서 업데이트 직후 첫 실행에 17초 걸렸고,
      // 그 사이 앱을 닫으면 새 지역 구독이 안 됐다 (태블릿 Play 내부 테스트에서 확인).
      // 토픽별로 예외를 따로 잡는다: 하나가 실패해도 나머지는 계속. 해지에 실패한 토픽은 다음에 다시 시도
      await Future.wait(wanted.map((topic) async {
        try {
          await fcm.subscribeToTopic(topic);
        } catch (e) {
          debugPrint('FCM 토픽 구독 실패 [$topic]: $e');
        }
      }));
      final failedUnsub = <String>{};
      await Future.wait(previous.difference(wanted).map((topic) async {
        try {
          await fcm.unsubscribeFromTopic(topic);
        } catch (e) {
          failedUnsub.add(topic);
          debugPrint('FCM 토픽 해지 실패 [$topic]: $e');
        }
      }));
      await prefs.setStringList(_subscribedKey, {...wanted, ...failedUnsub}.toList());
      debugPrint('✅ FCM 토픽 동기화: ${wanted.join(', ')}');
    } catch (e) {
      debugPrint('FcmService syncSubscriptions 오류: $e');
    }
  }

  /// 모든 알림 구독 해지 (알림 OFF) — 드문 동작이라 목록 전체를 해지해 확실히 끈다
  Future<void> unsubscribeAll() async {
    final fcm = _fcm;
    if (fcm == null) return;

    final topics = {...allTopics, ..._legacyTopics};
    for (final topic in topics) {
      try {
        await fcm.unsubscribeFromTopic(topic);
      } catch (e) {
        debugPrint('FCM 토픽 해지 실패 [$topic]: $e');
      }
    }
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_subscribedKey, const []);
    debugPrint('🚫 모든 FCM 토픽 해지 (${topics.length}개)');
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
