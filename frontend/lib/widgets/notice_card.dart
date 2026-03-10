import 'package:flutter/material.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../models/welfare_notice.dart';
import '../theme.dart';

/// 공고 카드 위젯 (Senior-Friendly)
/// - 상하 20px 넉넉한 터치 영역
/// - ai_summary → 초대형 굵은 폰트
/// - 출처 배지 (색상 구분)
/// - 원본 제목 서브텍스트
/// - 찜 버튼 (onBookmark 제공 시 표시)
class NoticeCard extends StatelessWidget {
  final WelfareNotice  notice;
  final VoidCallback   onTap;
  final bool           isBookmarked;
  final VoidCallback?  onBookmark;

  const NoticeCard({
    super.key,
    required this.notice,
    required this.onTap,
    this.isBookmarked = false,
    this.onBookmark,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            vertical:   SeniorTheme.touchPaddingV,
            horizontal: SeniorTheme.touchPaddingH,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 출처 배지 + 시간 + 찜 버튼
              Row(
                children: [
                  _SourceBadge(source: notice.source),
                  const Spacer(),
                  Text(
                    timeago.format(notice.timestamp, locale: 'ko'),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (onBookmark != null) ...[
                    const SizedBox(width: 8),
                    GestureDetector(
                      onTap: onBookmark,
                      child: Icon(
                        isBookmarked ? Icons.favorite : Icons.favorite_border,
                        color: isBookmarked ? Colors.redAccent : SeniorTheme.textSecond,
                        size: 28,
                      ),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 12),

              // AI 속보 요약 — 메인 텍스트 (대형 굵은 폰트)
              Text(
                notice.aiSummary,
                style: const TextStyle(
                  fontSize:   SeniorTheme.fontLG,
                  fontWeight: FontWeight.w800,
                  color:      SeniorTheme.textPrimary,
                  height:     1.4,
                ),
              ),
              const SizedBox(height: 8),

              // 원본 제목 — 서브텍스트
              Text(
                notice.title,
                style: Theme.of(context).textTheme.bodyMedium,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 12),

              // 신청하기 힌트
              Row(
                children: [
                  const Spacer(),
                  Text(
                    '자세히 보기 →',
                    style: TextStyle(
                      fontSize:   SeniorTheme.fontSM,
                      color:      SeniorTheme.primary,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 출처 배지 위젯
class _SourceBadge extends StatelessWidget {
  final String source;
  const _SourceBadge({required this.source});

  @override
  Widget build(BuildContext context) {
    final color = SeniorTheme.sourceColor(source);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        source,
        style: TextStyle(
          fontSize:   SeniorTheme.fontXS,
          color:      color,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}

/// 광고 플레이스홀더 카드 (AdMob 배너 대체)
class AdPlaceholderCard extends StatelessWidget {
  const AdPlaceholderCard({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      height: 60,
      decoration: BoxDecoration(
        color: const Color(0xFFEEEEEE),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFFCCCCCC)),
      ),
      child: const Center(
        child: Text(
          '광고',
          style: TextStyle(
            fontSize: SeniorTheme.fontXS,
            color:    SeniorTheme.textSecond,
          ),
        ),
      ),
    );
  }
}
