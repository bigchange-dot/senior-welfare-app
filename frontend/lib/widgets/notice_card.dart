import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_mobile_ads/google_mobile_ads.dart';
import 'package:timeago/timeago.dart' as timeago;
import '../models/welfare_notice.dart';
import '../services/ad_service.dart';
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
              // 출처 배지 + 찜 버튼 (시간은 아래 '자세히 보기' 줄로 옮김 — 글자를 2배로 키운 폰에서
              // 배지·시간·찜 버튼이 한 줄에 다 들어가지 않아 출처가 "도봉노…"로 잘렸음, 2026-11-17)
              Row(
                children: [
                  // 남는 폭만 쓰고 그래도 넘치면 말줄임
                  Expanded(
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: _SourceBadge(source: notice.source),
                    ),
                  ),
                  if (onBookmark != null)
                    // 터치 영역 48 이상 (예전 28px 아이콘만 눌려서 빗나가면 카드가 눌렸음)
                    IconButton(
                      onPressed:   onBookmark,
                      tooltip:     isBookmarked ? '찜 해제' : '찜하기',
                      constraints: const BoxConstraints(minWidth: 52, minHeight: 52),
                      icon: Icon(
                        isBookmarked ? Icons.favorite : Icons.favorite_border,
                        color: isBookmarked ? Colors.redAccent : SeniorTheme.textSecond,
                        size: 30,
                      ),
                    ),
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

              // 등록 시각 + 자세히 보기
              Row(
                children: [
                  Flexible(
                    child: Text(
                      timeago.format(notice.timestamp, locale: 'ko'),
                      style: const TextStyle(
                        fontSize: SeniorTheme.fontCaption,
                        color:    SeniorTheme.textSecond,
                      ),
                    ),
                  ),
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
        // 글자를 2배로 키운 좁은 폰에선 "서대문노인복지관"도 한 줄에 안 들어가 잘렸음 → 두 줄까지 허용
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize:   SeniorTheme.fontCaption,
          color:      color,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}

/// 목록 인라인 배너 광고 카드 (AdMob BannerAd)
///
/// ListView.builder 안에서 스크롤로 벗어나도 광고 객체를 유지하기 위해
/// AutomaticKeepAliveClientMixin 사용 → 재진입 시 광고 재요청 없음.
/// 로드 실패 시 빈 공간 대신 아무것도 그리지 않음.
class BannerAdCard extends StatefulWidget {
  const BannerAdCard({super.key});

  @override
  State<BannerAdCard> createState() => _BannerAdCardState();
}

class _BannerAdCardState extends State<BannerAdCard>
    with AutomaticKeepAliveClientMixin {
  BannerAd? _ad;
  bool _loaded = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    if (kIsWeb) return; // 웹 UI 테스트 모드에서는 광고 없음
    _ad = BannerAd(
      adUnitId: AdService.bannerAdUnitId,
      size:     AdSize.largeBanner, // 320x100 — 노인 사용자 가독성 고려
      request:  const AdRequest(),
      listener: BannerAdListener(
        onAdLoaded: (_) {
          if (mounted) setState(() => _loaded = true);
        },
        onAdFailedToLoad: (ad, error) {
          debugPrint('배너 광고 로드 실패: ${error.message}');
          ad.dispose();
          _ad = null; // 위젯이 이미 dispose된 뒤 콜백이 와도 이중 dispose 방지
          if (mounted) setState(() {});
        },
      ),
    )..load();
  }

  @override
  void dispose() {
    _ad?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final ad = _ad;
    if (ad == null || !_loaded) return const SizedBox.shrink();
    // ListView는 자식에 화면 폭을 강제하므로 Center + SizedBox로 광고 규격(320×100)을 고정.
    // 공고 카드 사이에 같은 폭으로 끼므로 어르신이 공고로 착각하지 않게 '광고' 표시를 붙인다 (2026-11-17)
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Center(
        child: SizedBox(
          width: ad.size.width.toDouble(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize:       MainAxisSize.min,
            children: [
              const Padding(
                padding: EdgeInsets.only(bottom: 4),
                child: Text(
                  '광고',
                  style: TextStyle(
                    fontSize:   SeniorTheme.fontCaption,
                    fontWeight: FontWeight.bold,
                    color:      SeniorTheme.textSecond,
                  ),
                ),
              ),
              SizedBox(
                height: ad.size.height.toDouble(),
                child:  AdWidget(ad: ad),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
