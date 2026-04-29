import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../theme.dart';

/// 공고 상세 WebView 화면
/// architecture.md 5.2, 5.3, 5.4:
/// - 앱 이탈 방지 인앱 브라우저
/// - 뒤로 가기 시 전면 광고 (Interstitial) 노출
/// - FCM Deep Linking으로 직접 진입 가능
class WebViewScreen extends StatefulWidget {
  final String url;
  final String title;
  final String docId;

  const WebViewScreen({
    super.key,
    required this.url,
    required this.title,
    required this.docId,
  });

  @override
  State<WebViewScreen> createState() => _WebViewScreenState();
}

class _WebViewScreenState extends State<WebViewScreen> {
  late final WebViewController _controller;
  bool _isLoading = true;
  InterstitialAd? _interstitialAd;

  static const String _adUnitId = 'ca-app-pub-5634467403173492/3253182704';

  @override
  void initState() {
    super.initState();
    _initWebView();
    _loadInterstitialAd();
  }

  @override
  void dispose() {
    _interstitialAd?.dispose();
    super.dispose();
  }

  void _initWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setNavigationDelegate(NavigationDelegate(
        onPageStarted:    (_) => setState(() => _isLoading = true),
        onPageFinished:   (_) => setState(() => _isLoading = false),
        onWebResourceError: (error) {
          debugPrint('WebView 오류: ${error.description}');
          setState(() => _isLoading = false);
        },
      ))
      ..loadRequest(Uri.parse(widget.url));
  }

  /// Interstitial 광고 미리 로드
  void _loadInterstitialAd() {
    InterstitialAd.load(
      adUnitId: _adUnitId,
      request: const AdRequest(),
      adLoadCallback: InterstitialAdLoadCallback(
        onAdLoaded: (ad) {
          ad.fullScreenContentCallback = FullScreenContentCallback(
            onAdDismissedFullScreenContent: (ad) {
              ad.dispose();
              _interstitialAd = null;
              if (mounted) Navigator.pop(context);
            },
            onAdFailedToShowFullScreenContent: (ad, error) {
              ad.dispose();
              _interstitialAd = null;
              if (mounted) Navigator.pop(context);
            },
          );
          setState(() => _interstitialAd = ad);
        },
        onAdFailedToLoad: (error) {
          debugPrint('Interstitial 로드 실패: ${error.message}');
          _interstitialAd = null;
        },
      ),
    );
  }

  /// 뒤로 가기 처리
  /// WebView 내부 페이지가 있으면 뒤로, 없으면 Interstitial 광고 → pop
  Future<void> _handleBack() async {
    if (await _controller.canGoBack()) {
      await _controller.goBack();
      return;
    }
    _showInterstitialAndPop();
  }

  void _showInterstitialAndPop() {
    if (_interstitialAd != null) {
      // 광고 표시 — 광고 닫힌 후 Navigator.pop은 FullScreenContentCallback에서 처리
      _interstitialAd!.show();
    } else {
      // 광고 미로드 시 즉시 pop
      if (mounted) Navigator.pop(context);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop) await _handleBack();
      },
      child: Scaffold(
        appBar: AppBar(
          backgroundColor: SeniorTheme.primary,
          foregroundColor: Colors.white,
          leading: IconButton(
            icon:    const Icon(Icons.arrow_back, size: 30),
            onPressed: _handleBack,
            tooltip: '뒤로',
          ),
          title: Text(
            widget.title,
            style: const TextStyle(
              fontSize:   SeniorTheme.fontSM, // 18px
              color:      Colors.white,
              fontWeight: FontWeight.bold,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          actions: [
            IconButton(
              icon:    const Icon(Icons.open_in_browser, size: 26),
              tooltip: '브라우저로 열기',
              onPressed: () async {
                final uri = Uri.parse(widget.url);
                if (await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              },
            ),
          ],
        ),
        body: Stack(
          children: [
            WebViewWidget(controller: _controller),
            if (_isLoading)
              Container(
                color: SeniorTheme.background,
                child: const Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      CircularProgressIndicator(color: SeniorTheme.primary),
                      SizedBox(height: 20),
                      Text(
                        '공고 페이지를 불러오는 중...',
                        style: TextStyle(
                          fontSize: SeniorTheme.fontMD,
                          color:    SeniorTheme.textSecond,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
