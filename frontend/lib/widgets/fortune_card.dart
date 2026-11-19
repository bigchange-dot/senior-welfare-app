import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/fortune.dart';
import '../screens/fortune_screen.dart';
import '../services/fortune_prefs.dart';
import '../theme.dart';

/// 홈 위쪽 운세 카드 (v1.6). 띠를 안 골랐으면 "내 띠 운세 보기", 골랐으면 오늘 등급과 핵심어.
/// 누르면 운세 화면으로 간다.
class FortuneCard extends StatelessWidget {
  /// 테스트에서 Firestore 대신 쓰는 구멍
  final Future<FortuneDay?> Function()? loadToday;

  const FortuneCard({super.key, this.loadToday});

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
        return FutureBuilder<FortuneDay?>(
          future: kIsWeb && loadToday == null ? Future.value(null) : (loadToday ?? FortuneRepo.today)().catchError((_) => null),
          builder: (context, snapshot) {
            final entry = snapshot.data?.entryFor(year);
            return _CardShell(
              emoji: zodiacOf(year).emoji,
              title: '오늘의 운세 · ${birthLabel(year)}',
              subtitle: entry == null ? '오늘 운세 보기' : '${entry.label} · ${entry.keyword}',
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
