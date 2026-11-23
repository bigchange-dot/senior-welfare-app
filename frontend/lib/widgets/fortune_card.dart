import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/fortune.dart';
import '../screens/fortune_screen.dart';
import '../services/fortune_prefs.dart';
import '../theme.dart';

/// 홈 위쪽 운세 카드 (v1.6). 띠를 안 골랐으면 "내 띠 운세 보기", 골랐으면 오늘 등급과 핵심어.
/// 누르면 운세 화면으로 간다.
///
/// 앱을 끄지 않고 두었다가 다음 날 다시 열면 어제 운세가 그대로 보이던 문제(1.6.0(12)에서 발견) →
/// 앱이 다시 앞으로 올 때 날짜가 바뀌었으면 오늘 문서를 다시 읽는다.
class FortuneCard extends StatefulWidget {
  /// 테스트에서 Firestore 대신 쓰는 구멍
  final Future<FortuneDay?> Function()? loadToday;

  /// 테스트에서 날짜를 바꿔 보는 구멍 (기본: 지금 시각)
  final DateTime Function()? now;

  const FortuneCard({super.key, this.loadToday, this.now});

  @override
  State<FortuneCard> createState() => _FortuneCardState();
}

class _FortuneCardState extends State<FortuneCard> with WidgetsBindingObserver {
  Future<FortuneDay?>? _future;
  String? _loadedFor;   // 마지막으로 읽은 날짜 (fortunes 문서 id)
  bool _got = false;    // 읽기에 성공했는지 — 실패(오프라인 등)했으면 다시 열 때 한 번 더 읽는다

  String _todayId() => fortuneDocId(widget.now?.call());

  Future<FortuneDay?> _load() {
    _loadedFor = _todayId();
    _got = false;
    if (kIsWeb && widget.loadToday == null) return Future.value(null);
    return (widget.loadToday ?? FortuneRepo.today)().then<FortuneDay?>((day) {
      _got = day != null;
      return day;
    }).catchError((_) => null);
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _future != null && (_loadedFor != _todayId() || !_got)) {
      setState(() {
        _future = _load();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<int?>(
      valueListenable: FortunePrefs.birthYear,
      builder: (context, year, _) {
        if (year == null) {
          return _CardShell(
            emoji: '🔮',
            title: '오늘의 운세',
            subtitle: '내 띠 운세 보기',
            onTap: () => _open(context),
          );
        }
        // 띠를 처음 고른 뒤에 읽기 시작. 같은 날은 다시 읽지 않는다 (띠를 바꿔도 같은 날 문서에 다 있음)
        _future ??= _load();
        return FutureBuilder<FortuneDay?>(
          future: _future,
          builder: (context, snapshot) {
            final entry = snapshot.data?.entryFor(year);
            return _CardShell(
              emoji: zodiacOf(year).emoji,
              title: '오늘의 운세 · ${birthLabel(year)}',
              subtitle: entry == null
                  ? '오늘 운세 보기'
                  : '${entry.label} · ${entry.keyword}${entry.score > 0 ? ' · ${entry.score}점' : ''}',
              onTap: () => _open(context),
            );
          },
        );
      },
    );
  }

  void _open(BuildContext context) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => const FortuneScreen(source: 'home_card')));
  }
}

class _CardShell extends StatelessWidget {
  final String emoji;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _CardShell({required this.emoji, required this.title, required this.subtitle, required this.onTap});

  /// 지역 줄과 같은 흰 바탕의 한 줄 (예전 노란 상자는 홈 맨 위에서 혼자 튀었음, v1.6 다듬기)
  @override
  Widget build(BuildContext context) {
    return Material(
      color: SeniorTheme.surface,
      child: InkWell(
        onTap: onTap,
        child: Container(
          constraints: const BoxConstraints(minHeight: 60),
          padding: const EdgeInsets.fromLTRB(16, 10, 8, 10),
          decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: SeniorTheme.divider))),
          child: Row(
            children: [
              Text(emoji, style: const TextStyle(fontSize: 26)),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: const TextStyle(fontSize: SeniorTheme.fontCaption, color: SeniorTheme.textSecond)),
                    Text(subtitle,
                        style: const TextStyle(
                          fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, size: 30, color: SeniorTheme.textSecond),
            ],
          ),
        ),
      ),
    );
  }
}
