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
  final Future<FortuneDay?> Function()? loadTomorrow;
  final Future<int> Function()? loadNoticeCount;
  final Future<bool> Function()? requestPermission;
  final bool adsEnabled;

  const FortuneScreen({
    super.key,
    this.source = 'home_card',
    this.loadToday,
    this.loadTomorrow,
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

  Future<FortuneDay?>? _tomorrowFuture;   // [내일 운세 미리 보기]를 누른 뒤에만 읽는다

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
    final result = granted
        ? '내일 아침 7시에 알려 드릴게요.'
        : '휴대폰 설정에서 알림을 허용해 주세요. 그다음 설정 탭에서 운세 알림을 켤 수 있어요.';
    setState(() {
      _showQuestion = false;
      _questionResult = result;
    });
    // 질문 상자가 접히면 그 자리 글이 화면 위로 밀려 안 보일 수 있어, 화면 아래에도 잠깐 띄운다
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      duration: const Duration(seconds: 5),
      content: Text(result, style: const TextStyle(fontSize: SeniorTheme.fontSM, height: 1.4)),
    ));
  }

  void _goToNotices() {
    AnalyticsService.fortuneToNotices();
    _withInterstitial(() {
      if (mounted) Navigator.of(context).pop();
    });
  }

  void _peekTomorrow() {
    AnalyticsService.fortuneTomorrow();
    setState(() {
      _tomorrowFuture = (widget.loadTomorrow ?? FortuneRepo.tomorrow)().catchError((_) => null);
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
            // 중괄호 본문이어야 한다 — 화살표로 쓰면 setState가 Future를 돌려받아 디버그에서 오류가 난다
            onRetry: () => setState(() {
              _dayFuture = (widget.loadToday ?? FortuneRepo.today)();
            }),
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
            _ScoreCard(entry: entry),
            if (_showQuestion) ...[
              const SizedBox(height: 16),
              _NotifQuestion(onAnswer: _answerQuestion),
            ],
            if (_questionResult != null) ...[
              const SizedBox(height: 16),
              Text(_questionResult!,
                  style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.primary, height: 1.4)),
            ],
            const SizedBox(height: 12),
            _AreasCard(entry: entry),
            const SizedBox(height: 12),
            _LuckyCard(entry: entry),
            if (day.ranking.isNotEmpty) ...[
              const SizedBox(height: 12),
              _RankingCard(rows: day.ranking, myBranch: zodiacOf(year).branch),
            ],
            const SizedBox(height: 12),
            _TomorrowCard(future: _tomorrowFuture, year: year, onPeek: _peekTomorrow),
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

/// 흰 카드 한 장 (운세 화면의 묶음마다 하나)
class _Section extends StatelessWidget {
  final String? title;
  final List<Widget> children;
  const _Section({this.title, required this.children});

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
          if (title != null) ...[
            Text(title!,
                style: const TextStyle(
                  fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.primary)),
            const SizedBox(height: 12),
          ],
          ...children,
        ],
      ),
    );
  }
}

/// 등급 + 총운 점수 + 총운 (첫 문장은 굵게, 이어지는 문장은 한 문단)
class _ScoreCard extends StatelessWidget {
  final FortuneEntry entry;
  const _ScoreCard({required this.entry});

  @override
  Widget build(BuildContext context) {
    return _Section(
      children: [
        Wrap(
          spacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(entry.label,
                style: const TextStyle(
                  fontSize: SeniorTheme.fontXL, fontWeight: FontWeight.bold, color: SeniorTheme.orangeAccent)),
            if (entry.score > 0)
              Text('${entry.score}점',
                  style: const TextStyle(
                    fontSize: SeniorTheme.fontXXL, fontWeight: FontWeight.w900, color: SeniorTheme.primary)),
          ],
        ),
        if (entry.rank > 0)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text('오늘 띠 순위 ${entry.rank}위',
                style: const TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond)),
          ),
        const SizedBox(height: 12),
        Text(entry.headline,
            style: const TextStyle(
              fontSize: SeniorTheme.fontLG, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary, height: 1.4)),
        if (entry.detail.isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(entry.detail.join(' '),
              style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textPrimary, height: 1.6)),
        ],
      ],
    );
  }
}

/// 분야별 운세 — 건강·가족·재물·마음, 별점과 한 줄
class _AreasCard extends StatelessWidget {
  final FortuneEntry entry;
  const _AreasCard({required this.entry});

  @override
  Widget build(BuildContext context) {
    final rows = [
      ('건강', 'health', entry.health),
      ('가족', 'family', entry.family),
      ('재물', 'money', entry.money),
      ('마음', 'mind', entry.mind),
    ].where((r) => r.$3.isNotEmpty).toList();
    return _Section(
      title: '분야별 운세',
      children: [
        for (var i = 0; i < rows.length; i++)
          Padding(
            padding: EdgeInsets.only(bottom: i == rows.length - 1 ? 0 : 14),
            child: _AreaRow(label: rows[i].$1, stars: entry.stars[rows[i].$2] ?? 0, text: rows[i].$3),
          ),
      ],
    );
  }
}

class _AreaRow extends StatelessWidget {
  final String label;
  final int stars;      // 0이면 별을 그리지 않는다 (예전 문서)
  final String text;
  const _AreaRow({required this.label, required this.stars, required this.text});

  @override
  Widget build(BuildContext context) {
    final starSize = 22.0 * MediaQuery.textScalerOf(context).scale(1.0).clamp(1.0, 1.5);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 10,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(label,
                style: const TextStyle(
                  fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary)),
            if (stars > 0)
              Semantics(
                label: '별 다섯 개 중 $stars개',
                excludeSemantics: true,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (var i = 0; i < 5; i++)
                      Icon(i < stars ? Icons.star_rounded : Icons.star_outline_rounded,
                          size: starSize, color: i < stars ? SeniorTheme.orangeAccent : SeniorTheme.divider),
                  ],
                ),
              ),
          ],
        ),
        const SizedBox(height: 2),
        Text(text, style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textPrimary, height: 1.4)),
      ],
    );
  }
}

/// 오늘의 행운 — 색·숫자·방향·시간·음식 + 잘 맞는 띠
class _LuckyCard extends StatelessWidget {
  final FortuneEntry entry;
  const _LuckyCard({required this.entry});

  static String _zodiacText(int branch) => '${zodiacs[branch].emoji} ${zodiacs[branch].name}띠';

  @override
  Widget build(BuildContext context) {
    final items = <(String, String)>[
      ('색', entry.color),
      ('숫자', entry.number > 0 ? '${entry.number}' : ''),
      ('방향', entry.direction),
      ('시간', entry.time),
      ('음식', entry.food),
      if (entry.goodWith != null) ('잘 맞는 띠', _zodiacText(entry.goodWith!)),
      if (entry.careWith != null) ('양보하면 좋은 띠', _zodiacText(entry.careWith!)),
    ].where((e) => e.$2.isNotEmpty).toList();
    return _Section(
      title: '오늘의 행운',
      children: [
        for (var i = 0; i < items.length; i++)
          Padding(
            padding: EdgeInsets.only(bottom: i == items.length - 1 ? 0 : 8),
            child: Wrap(
              spacing: 10,
              children: [
                Text(items[i].$1,
                    style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond)),
                Text(items[i].$2,
                    style: const TextStyle(
                      fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary)),
              ],
            ),
          ),
      ],
    );
  }
}

/// 오늘의 띠 순위 1~12위. 지금 보고 있는 띠 줄을 강조한다
class _RankingCard extends StatelessWidget {
  final List<RankRow> rows;
  final int myBranch;
  const _RankingCard({required this.rows, required this.myBranch});

  @override
  Widget build(BuildContext context) {
    return _Section(
      title: '오늘의 띠 순위',
      children: [
        for (var i = 0; i < rows.length; i++) _row(i + 1, rows[i]),
      ],
    );
  }

  Widget _row(int rank, RankRow row) {
    final mine = row.branch == myBranch;
    final z = zodiacs[row.branch];
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: mine ? SeniorTheme.primary.withValues(alpha: 0.08) : null,
        borderRadius: BorderRadius.circular(10),
        border: mine ? Border.all(color: SeniorTheme.primary, width: 1.5) : null,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('$rank위  ',
              style: TextStyle(
                fontSize: SeniorTheme.fontMD,
                fontWeight: FontWeight.bold,
                color: rank <= 3 ? SeniorTheme.orangeAccent : SeniorTheme.textSecond)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${z.emoji} ${z.name}띠${mine ? '  ← 내 띠' : ''}',
                    style: const TextStyle(
                      fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary)),
                if (row.comment.isNotEmpty)
                  Text(row.comment,
                      style: const TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// 내일 운세 미리 보기 — 누르면 내일 문서를 읽어 등급·점수·총운 첫 문장을 보여 준다
class _TomorrowCard extends StatelessWidget {
  final Future<FortuneDay?>? future;
  final int year;
  final VoidCallback onPeek;
  const _TomorrowCard({required this.future, required this.year, required this.onPeek});

  @override
  Widget build(BuildContext context) {
    if (future == null) {
      return OutlinedButton(
        onPressed: onPeek,
        style: OutlinedButton.styleFrom(
          minimumSize: const Size.fromHeight(60),
          backgroundColor: SeniorTheme.surface,
          side: const BorderSide(color: SeniorTheme.divider, width: 1.5),
          foregroundColor: SeniorTheme.textPrimary,
          textStyle: const TextStyle(fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(SeniorTheme.cardRadius)),
        ),
        child: const Text('🌙 내일 운세 미리 보기'),
      );
    }
    return FutureBuilder<FortuneDay?>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const _Section(
            title: '내일 운세',
            children: [Center(child: CircularProgressIndicator(color: SeniorTheme.primary))],
          );
        }
        final day = snapshot.data;
        final entry = day?.entryFor(year);
        if (day == null || entry == null) {
          return const _Section(
            title: '내일 운세',
            children: [
              Text('내일 운세는 아침 7시에 준비돼요.',
                  style: TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond)),
            ],
          );
        }
        return _Section(
          title: '내일 운세 · ${day.dateLabel}',
          children: [
            Text('${entry.label}${entry.score > 0 ? ' · ${entry.score}점' : ''}',
                style: const TextStyle(
                  fontSize: SeniorTheme.fontLG, fontWeight: FontWeight.bold, color: SeniorTheme.orangeAccent)),
            const SizedBox(height: 8),
            Text(entry.headline,
                style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textPrimary, height: 1.4)),
            const SizedBox(height: 8),
            const Text('자세한 내용은 내일 아침에 볼 수 있어요.',
                style: TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond)),
          ],
        );
      },
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
