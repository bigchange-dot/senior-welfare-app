
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import 'package:timeago/timeago.dart' as timeago;

import 'screens/bookmarks_screen.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/webview_screen.dart';
import 'services/fcm_service.dart';
import 'theme.dart';

import 'package:flutter/foundation.dart';

import 'firebase_options.dart';

/// 앱 최상단 진입점
void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    if (kIsWeb) {
      debugPrint('웹 환경 감지됨: UI 테스트를 위해 Firebase 초기화를 임시로 건너뜁니다.');
    } else {
      // Firebase 초기화
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );

      // FCM 백그라운드 핸들러 (반드시 runApp 전에 등록)
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

      // FCM 서비스 초기화
      await FcmService.instance.initialize();

      // AdMob 초기화
      await MobileAds.instance.initialize();
    }
  } catch (e) {
    debugPrint('Firebase/AdMob 초기화 예외 발생 (에러 무시하고 앱 실행): $e');
  }

  // timeago 한국어 로케일 등록
  timeago.setLocaleMessages('ko', timeago.KoMessages());

  runApp(const SeniorWelfareApp());
}

class SeniorWelfareApp extends StatelessWidget {
  const SeniorWelfareApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title:        '노인 복지 속보',
      theme:        SeniorTheme.themeData,
      debugShowCheckedModeBanner: false,
      navigatorKey: FcmService.navigatorKey, // Deep Linking용 글로벌 네비게이터 키

      // 라우트 (FCM Deep Linking)
      initialRoute: '/',
      routes: {
        '/': (_) => const MainScaffold(),
      },
      onGenerateRoute: (settings) {
        if (settings.name == '/webview') {
          final args = settings.arguments as Map<String, String>? ?? {};
          return MaterialPageRoute(
            builder: (_) => WebViewScreen(
              url:   args['url']    ?? '',
              title: args['title']  ?? '공고 상세',
              docId: args['doc_id'] ?? '',
            ),
          );
        }
        return null;
      },
    );
  }
}

/// 3-탭 메인 스캐폴드 (홈 / 찜 / 설정)
class MainScaffold extends StatefulWidget {
  const MainScaffold({super.key});

  @override
  State<MainScaffold> createState() => _MainScaffoldState();
}

class _MainScaffoldState extends State<MainScaffold> {
  int _currentIndex = 0;

  final _bookmarksKey = GlobalKey<BookmarksScreenState>();

  static const List<String> _titles = ['홈 (속보)', '찜한 공고', '설정'];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_currentIndex]),
        actions: [
          if (_currentIndex == 0)
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Icon(
                Icons.autorenew,
                color: Colors.white.withValues(alpha: 0.8),
                size: 24,
              ),
            ),
        ],
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: [
          const HomeScreen(),
          BookmarksScreen(key: _bookmarksKey),
          const SettingsScreen(),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (idx) {
          // 찜 탭으로 전환 시 최신 데이터 새로고침
          if (idx == 1) _bookmarksKey.currentState?.refresh();
          setState(() => _currentIndex = idx);
        },
        items: const [
          BottomNavigationBarItem(
            icon:       Icon(Icons.home_outlined,    size: 30),
            activeIcon: Icon(Icons.home,             size: 30),
            label:      '홈',
          ),
          BottomNavigationBarItem(
            icon:       Icon(Icons.favorite_outline, size: 30),
            activeIcon: Icon(Icons.favorite,         size: 30),
            label:      '찜',
          ),
          BottomNavigationBarItem(
            icon:       Icon(Icons.settings_outlined, size: 30),
            activeIcon: Icon(Icons.settings,          size: 30),
            label:      '설정',
          ),
        ],
      ),
    );
  }
}
