import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';

import '../models/fortune.dart';
import '../services/ad_service.dart';
import '../services/analytics_service.dart';
import '../services/fcm_service.dart';
import '../services/fortune_prefs.dart';
import '../theme.dart';
import '../widgets/notice_card.dart';

/// 오늘의 운세 (v1.6, 설계: docs/운세-설계-2026-11-18.md 4장)
///
/// 처음 들어오면 띠(12개) → 년생(5개)을 고른다. 고른 값은 기기에만 저장하고 다음부터는 바로 내 운세.
/// [다른 띠 보기]는 가족 띠를 잠깐 보는 것 — 내 띠 설정은 바뀌지 않는다.
/// 전면광고는 [다른 띠 보기]·[새 공고 보기]를 누를 때만 (알림 탭 직후·화면 진입 때는 띄우지 않는다, AdMob 정책).
class FortuneScreen extends StatefulWidget {
  /// 어디서 들어왔는지 (Analytics): notification / home_card / settings
  final String source;

  /// 테스트에서 Firestore·광고·알림 권한을 가짜로 바꾸는 구멍
  final Future<FortuneDay?> Function()? loadToday;
  final Future<int> Function()? loadNoticeCount;
  final Future<bool> Function()? requestPermission;
  final bool adsEnabled;

  const FortuneScreen({
    super.key,
    this.source = 'home_card',
    this.loadToday,
    this.loadNoticeCount,
    this.requestPermission,
    this.adsEnabled = true,
  });

  @override
  State<FortuneScreen> createState() => _FortuneScreenState();
}

class _FortuneScreenState extends State<FortuneScreen> {
  late Future<FortuneDay?> _dayFuture;
  int? _noticeCount;

  int? _myYear = FortunePrefs.birthYear.value;
  int? _otherYear;                 // [다른 띠 보기]로 잠깐 보는 년생
  bool _picking = false;           // 띠·년생 고르는 중
  bool _pickingOther = false;      // 고르는 것이 '다른 띠'인지 (내 띠 설정을 바꾸지 않음)
  Zodiac? _pickedZodiac;

  bool _showQuestion = false;      // "내일 아침 7시에도 알려 드릴까요?"
  String? _questionResult;

  InterstitialAd? _interstitial;

  // 띠를 고르면 년생 목록을 맨 위부터 보여 주려고 (아래쪽 띠를 누르면 목록이 밀려 보였음 — 위젯 테스트로 확인)
  final ScrollController _pickerScroll = ScrollController();

  void _setZodiac(Zodiac? zodiac) {
    setState(() => _pickedZodiac = zodiac);
    if (_pickerScroll.hasClients) _pickerScroll.jumpTo(0);
  }

  @override
  void initState() {
    super.initState();
    _dayFuture = (widget.loadToday ?? FortuneRepo.today)();
    _picking = _myYear == null;
    AnalyticsService.fortuneView(widget.source);
    (widget.loadNoticeCount ?? FortuneRepo.todayNoticeCount)().then((n) {
      if (mounted) setState(() => _noticeCount = n);
    }).catchError((_) {});
    _loadInterstitial();
  }

  @override
  void dispose() {
    _interstitial?.dispose();
    _pickerScroll.dispose();
    super.dispose();
  }

  // ── 전면광고: 화면을 열 때 미리 받아 두고, 버튼을 누를 때만 보여 준다 ──
  void _loadInterstitial() {
    if (!widget.adsEnabled || kIsWeb || !AdService.canShowInterstitial()) return;
    InterstitialAd.load(
      adUnitId: AdService.interstitialAdUnitId,
      request: const AdRequest(),
      adLoadCallback: InterstitialAdLoadCallback(
        onAdLoaded: (ad) => _interstitial = ad,
        onAdFailedToLoad: (error) => debugPrint('운세 전면광고 로드 실패: ${error.message}'),
      ),
    );
  }

  /// 광고가 준비돼 있고 빈도 제한 안이면 광고를 보여 준 뒤 [then], 아니면 바로 [then]
  void _withInterstitial(VoidCallback then) {
    final ad = _interstitial;
    if (ad == null || !AdService.canShowInterstitial()) {
      then();
      return;
    }
    _interstitial = null;
    ad.fullScreenContentCallback = FullScreenContentCallback(
      onAdDismissedFullScreenContent: (ad) {
        ad.dispose();
        then();
      },
      onAdFailedToShowFullScreenContent: (ad, error) {
        ad.dispose();
        then();
      },
    );
    AdService.recordInterstitialShown();
    ad.show();
  }

  // ── 띠·년생 고르기 ──
  void _startPicking({required bool other}) {
    setState(() {
      _picking = true;
      _pickingOther = other;
      _pickedZodiac = null;
    });
  }

  Future<void> _pickYear(int year) async {
    if (_pickingOther) {
      setState(() {
        _otherYear = year;
        _picking = false;
      });
      return;
    }
    final first = _myYear == null;
    await FortunePrefs.setBirthYear(year);
    if (!mounted) return;
    setState(() {
      _myYear = year;
      _otherYear = null;
      _picking = false;
      // 처음 고르고 첫 운세를 본 뒤 한 번만 묻는다
      _showQuestion = first && !FortunePrefs.notifAsked;
    });
  }

  // ── 알림 받기 질문 ──
  Future<void> _answerQuestion(bool yes) async {
    await FortunePrefs.markAsked();
    if (!yes) {
      AnalyticsService.fortuneNotifAnswer('no');
      if (mounted) setState(() => _showQuestion = false);
      return;
    }
    final granted = await (widget.requestPermission ?? FcmService.instance.requestPermission)();
    if (granted) {
      await FortunePrefs.setNotif(true);
      AnalyticsService.fortuneNotifAnswer('yes');
    } else {
      AnalyticsService.fortuneNotifAnswer('no_permission');
    }
    if (!mounted) return;
    setState(() {
      _showQuestion = false;
      _questionResult = granted
          ? '내일 아침 7시에 알려 드릴게요.'
          : '휴대폰 설정에서 알림을 허용해 주세요. 그다음 설정 탭에서 운세 알림을 켤 수 있어요.';
    });
  }

  void _goToNotices() {
    AnalyticsService.fortuneToNotices();
    _withInterstitial(() {
      if (mounted) Navigator.of(context).pop();
    });
  }

  void _seeOtherAnimal() {
    AnalyticsService.fortuneOtherAnimal();
    _withInterstitial(() {
      if (mounted) _startPicking(other: true);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SeniorTheme.background,
      appBar: AppBar(title: const Text('오늘의 운세')),
      body: SafeArea(
        child: _picking ? _buildPicker() : _buildFortune(),
      ),
    );
  }

  // ── 고르는 화면: 띠 12개 → 년생 5개 ──
  Widget _buildPicker() {
    final zodiac = _pickedZodiac;
    final scale = MediaQuery.textScalerOf(context).scale(1.0).clamp(1.0, 2.5);
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = ((constraints.maxWidth - 32) / (110 * scale)).floor().clamp(2, 4);
        return CustomScrollView(
          controller: _pickerScroll,
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 20, 16, 12),
                child: Text(
                  zodiac == null
                      ? (_pickingOther ? '어느 띠 운세를 볼까요?' : '무슨 띠세요?')
                      : '${zodiac.emoji} ${zodiac.name}띠 — 몇 년생이세요?',
                  style: const TextStyle(
                    fontSize: SeniorTheme.fontXL, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary),
                ),
              ),
            ),
            if (zodiac == null)
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                sliver: SliverGrid(
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: columns, mainAxisSpacing: 10, crossAxisSpacing: 10, mainAxisExtent: 104 * scale),
                  delegate: SliverChildBuilderDelegate(
                    (context, i) => _PickTile(
                      top: zodiacs[i].emoji,
                      label: '${zodiacs[i].name}띠',
                      onTap: () => _setZodiac(zodiacs[i]),
                    ),
                    childCount: zodiacs.length,
                  ),
                ),
              )
            else ...[
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                sliver: SliverList(
                  delegate: SliverChildListDelegate([
                    for (final y in zodiac.years)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: ElevatedButton(
                          onPressed: () => _pickYear(y),
                          child: Text('$y년생 (${(y % 100).toString().padLeft(2, '0')}년생)'),
                        ),
                      ),
                  ]),
                ),
              ),
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  child: TextButton(
                    onPressed: () => _setZodiac(null),
                    child: const Text('← 띠 다시 고르기', style: TextStyle(fontSize: SeniorTheme.fontMD)),
                  ),
                ),
              ),
            ],
            if (!_pickingOther && _myYear == null)
              const SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.fromLTRB(16, 0, 16, 24),
                  child: Text(
                    '고른 띠는 이 휴대폰에만 저장돼요.',
                    style: TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  // ── 운세 화면 ──
  Widget _buildFortune() {
    final year = _otherYear ?? _myYear!;
    return FutureBuilder<FortuneDay?>(
      future: _dayFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator(color: SeniorTheme.primary));
        }
        final day = snapshot.data;
        final entry = day?.entryFor(year);
        if (day == null || entry == null) {
          return _Preparing(
            failed: snapshot.hasError,
            onRetry: () => setState(() => _dayFuture = (widget.loadToday ?? FortuneRepo.today)()),
          );
        }
        final count = _noticeCount;
        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
          children: [
            Text(day.dateLabel, style: const TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond)),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${zodiacOf(year).emoji} ${birthLabel(year)}',
                    style: const TextStyle(
                      fontSize: SeniorTheme.fontLG, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary),
                  ),
                ),
                if (_otherYear == null)
                  TextButton(
                    onPressed: () => _startPicking(other: false),
                    child: const Text('띠 바꾸기', style: TextStyle(fontSize: SeniorTheme.fontSM)),
                  )
                else
                  TextButton(
                    onPressed: () => setState(() => _otherYear = null),
                    child: const Text('내 띠로', style: TextStyle(fontSize: SeniorTheme.fontSM)),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            _FortuneBody(entry: entry),
            if (_showQuestion) ...[
              const SizedBox(height: 16),
              _NotifQuestion(onAnswer: _answerQuestion),
            ],
            if (_questionResult != null) ...[
              const SizedBox(height: 16),
              Text(_questionResult!,
                  style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.primary, height: 1.4)),
            ],
            const SizedBox(height: 20),
            OutlinedButton(
              onPressed: _seeOtherAnimal,
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(60),
                side: const BorderSide(color: SeniorTheme.primary, width: 2),
                foregroundColor: SeniorTheme.primary,
                textStyle: const TextStyle(fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text('다른 띠 보기'),
            ),
            const SizedBox(height: 10),
            ElevatedButton(
              onPressed: _goToNotices,
              child: Text(count != null && count > 0 ? '오늘 새 공고 $count건 보기' : '복지 공고 보러 가기'),
            ),
            const SizedBox(height: 16),
            const Center(
              child: Text('재미로 보는 운세입니다',
                  style: TextStyle(fontSize: SeniorTheme.fontCaption, color: SeniorTheme.textSecond)),
            ),
            if (widget.adsEnabled) ...[
              const SizedBox(height: 12),
              const BannerAdCard(),
            ],
          ],
        );
      },
    );
  }
}

/// 등급·총운·건강·가족·재물·행운 (홈 카드와 같은 데이터)
class _FortuneBody extends StatelessWidget {
  final FortuneEntry entry;
  const _FortuneBody({required this.entry});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: SeniorTheme.surface,
        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
        border: Border.all(color: SeniorTheme.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(entry.label,
              style: const TextStyle(
                fontSize: SeniorTheme.fontXL, fontWeight: FontWeight.bold, color: SeniorTheme.orangeAccent)),
          const SizedBox(height: 10),
          Text(entry.headline,
              style: const TextStyle(
                fontSize: SeniorTheme.fontLG, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary, height: 1.4)),
          const Divider(height: 28),
          _AreaRow(label: '건강', text: entry.health),
          _AreaRow(label: '가족', text: entry.family),
          _AreaRow(label: '재물', text: entry.money),
          const SizedBox(height: 6),
          Text('행운의 색 ${entry.color} · 숫자 ${entry.number}',
              style: const TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond)),
        ],
      ),
    );
  }
}

class _AreaRow extends StatelessWidget {
  final String label;
  final String text;
  const _AreaRow({required this.label, required this.text});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$label  ',
              style: const TextStyle(
                fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.primary)),
          Expanded(
            child: Text(text,
                style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textPrimary, height: 1.4)),
          ),
        ],
      ),
    );
  }
}

class _NotifQuestion extends StatelessWidget {
  final ValueChanged<bool> onAnswer;
  const _NotifQuestion({required this.onAnswer});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: SeniorTheme.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
        border: Border.all(color: SeniorTheme.primary.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('내일 아침 7시에도 운세를 알려 드릴까요?',
              style: TextStyle(
                fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary, height: 1.4)),
          const SizedBox(height: 12),
          ElevatedButton(onPressed: () => onAnswer(true), child: const Text('네, 받을게요')),
          const SizedBox(height: 8),
          TextButton(
            onPressed: () => onAnswer(false),
            child: const Text('괜찮아요', style: TextStyle(fontSize: SeniorTheme.fontMD)),
          ),
        ],
      ),
    );
  }
}

class _PickTile extends StatelessWidget {
  final String top;
  final String label;
  final VoidCallback onTap;
  const _PickTile({required this.top, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: SeniorTheme.surface,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onTap,
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: SeniorTheme.divider, width: 1.5),
            ),
            padding: const EdgeInsets.all(6),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                FittedBox(fit: BoxFit.scaleDown, child: Text(top, style: const TextStyle(fontSize: 34))),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Text(label,
                      style: const TextStyle(
                        fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Preparing extends StatelessWidget {
  final bool failed;
  final VoidCallback onRetry;
  const _Preparing({required this.failed, required this.onRetry});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(failed ? Icons.wifi_off : Icons.wb_twilight, size: 72, color: SeniorTheme.textSecond),
            const SizedBox(height: 16),
            Text(
              failed ? '운세를 불러오지 못했어요.\n인터넷 연결을 확인해 주세요.' : '오늘 운세를 준비하고 있어요.\n잠시 뒤 다시 봐 주세요.',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond, height: 1.5),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: 220,
              child: ElevatedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh, size: 26),
                label: const Text('다시 시도'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
