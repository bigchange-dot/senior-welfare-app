import 'package:flutter/foundation.dart';

/// AdMob 광고 단위 ID 및 전면광고 노출 빈도 제한
///
/// - 디버그 빌드에서는 구글 공식 테스트 ID를 사용 (개발 중 실제 광고 클릭 → 무효 트래픽 방지)
/// - 릴리스 빌드에서만 실제 광고 단위 ID 사용
class AdService {
  AdService._();

  // ── 실제 광고 단위 ID (AdMob 콘솔) ──
  static const String _interstitialProd = 'ca-app-pub-5634467403173492/3253182704';
  // TODO: AdMob 콘솔에서 "배너" 광고 단위를 새로 만들고 아래 ID를 교체할 것.
  //       교체 전에는 로드 실패 → 배너 자리가 비어 보임 (앱 동작에는 영향 없음)
  static const String _bannerProd = 'ca-app-pub-5634467403173492/0000000000';

  // ── 구글 공식 테스트 ID (Android) ──
  static const String _interstitialTest = 'ca-app-pub-3940256099942544/1033173712';
  static const String _bannerTest       = 'ca-app-pub-3940256099942544/6300978111';

  static String get interstitialAdUnitId =>
      kDebugMode ? _interstitialTest : _interstitialProd;
  static String get bannerAdUnitId =>
      kDebugMode ? _bannerTest : _bannerProd;

  // ── 전면광고 빈도 제한 ──
  // 노인 사용자의 뒤로가기 오클릭·과다 노출은 AdMob 무효 트래픽 판정 소지가 있어
  // 세션당 최대 횟수와 최소 간격을 둠.
  static const int      maxInterstitialsPerSession = 3;
  static const Duration minInterstitialInterval    = Duration(minutes: 3);

  static int       _shownThisSession = 0;
  static DateTime? _lastShownAt;

  /// 지금 전면광고를 띄워도 되는지 (로드 전에 호출해 불필요한 광고 요청도 막음)
  static bool canShowInterstitial() {
    if (_shownThisSession >= maxInterstitialsPerSession) return false;
    final last = _lastShownAt;
    if (last != null && DateTime.now().difference(last) < minInterstitialInterval) {
      return false;
    }
    return true;
  }

  /// 전면광고가 실제로 표시됐을 때 호출
  static void recordInterstitialShown() {
    _shownThisSession += 1;
    _lastShownAt = DateTime.now();
  }
}
