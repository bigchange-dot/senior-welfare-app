import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/welfare_notice.dart';
import '../widgets/notice_card.dart';
import '../theme.dart';
import 'webview_screen.dart';

/// 찜 탭
/// 상단: 찜한 공고 목록
/// 하단: 설정에서 선택한 내 지역 공고 목록
class BookmarksScreen extends StatefulWidget {
  const BookmarksScreen({super.key});

  @override
  State<BookmarksScreen> createState() => BookmarksScreenState();
}

class BookmarksScreenState extends State<BookmarksScreen> {
  List<WelfareNotice> _bookmarkedNotices = [];
  List<WelfareNotice> _regionNotices     = [];
  List<String>        _selectedSources   = [];
  bool                _isLoading         = true;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  /// 외부(MainScaffold)에서 탭 전환 시 호출
  Future<void> refresh() async {
    setState(() => _isLoading = true);
    await Future.wait([_loadBookmarks(), _loadRegionNotices()]);
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _loadBookmarks() async {
    final prefs = await SharedPreferences.getInstance();
    final ids   = prefs.getStringList('bookmarked_ids') ?? [];

    if (ids.isEmpty) {
      _bookmarkedNotices = [];
      return;
    }

    try {
      final snapshot = await FirebaseFirestore.instance
          .collection('welfare_notices')
          .where(FieldPath.documentId, whereIn: ids.take(30).toList())
          .get();

      _bookmarkedNotices = snapshot.docs
          .map((d) => WelfareNotice.fromFirestore(d))
          .toList()
        ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
    } catch (e) {
      debugPrint('찜 목록 로드 오류: $e');
      _bookmarkedNotices = [];
    }
  }

  Future<void> _loadRegionNotices() async {
    final prefs = await SharedPreferences.getInstance();
    _selectedSources = prefs.getStringList('selected_sources') ?? [];

    // 빈 문자열('전체') 제거 — whereIn에 빈 값 전달 방지
    final sources = _selectedSources.where((s) => s.isNotEmpty).toList();

    if (sources.isEmpty) {
      _regionNotices = [];
      return;
    }

    try {
      final snapshot = await FirebaseFirestore.instance
          .collection('welfare_notices')
          .where('source', whereIn: sources)
          .orderBy('timestamp', descending: true)
          .limit(30)
          .get();

      _regionNotices = snapshot.docs
          .map((d) => WelfareNotice.fromFirestore(d))
          .toList();
    } catch (e) {
      debugPrint('지역 공고 로드 오류: $e');
      _regionNotices = [];
    }
  }

  Future<void> _removeBookmark(String id) async {
    final prefs = await SharedPreferences.getInstance();
    final ids   = List<String>.from(prefs.getStringList('bookmarked_ids') ?? []);
    ids.remove(id);
    await prefs.setStringList('bookmarked_ids', ids);
    setState(() => _bookmarkedNotices.removeWhere((n) => n.id == id));
  }

  void _openNotice(BuildContext context, WelfareNotice notice) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => WebViewScreen(
          url:   notice.url,
          title: notice.aiSummary,
          docId: notice.id,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(color: SeniorTheme.primary),
      );
    }

    return RefreshIndicator(
      color: SeniorTheme.primary,
      onRefresh: refresh,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          // ── 찜한 공고 섹션 ──────────────────────────
          _SectionHeader(
            icon:  Icons.favorite,
            color: Colors.redAccent,
            title: '찜한 공고',
            count: _bookmarkedNotices.length,
          ),

          if (_bookmarkedNotices.isEmpty)
            const SliverToBoxAdapter(child: _EmptyBookmarks())
          else
            SliverList(
              delegate: SliverChildBuilderDelegate(
                (context, idx) {
                  final notice = _bookmarkedNotices[idx];
                  return NoticeCard(
                    notice:       notice,
                    isBookmarked: true,
                    onBookmark:   () => _removeBookmark(notice.id),
                    onTap:        () => _openNotice(context, notice),
                  );
                },
                childCount: _bookmarkedNotices.length,
              ),
            ),

          // ── 내 지역 공고 섹션 ────────────────────────
          if (_selectedSources.where((s) => s.isNotEmpty).isNotEmpty) ...[
            const SliverToBoxAdapter(
              child: Divider(height: 32, thickness: 6, color: Color(0xFFEEEEEE)),
            ),
            _SectionHeader(
              icon:  Icons.location_on,
              color: SeniorTheme.primary,
              title: '${_selectedSources.where((s) => s.isNotEmpty).join(' · ')} 공고',
              count: _regionNotices.length,
            ),
            if (_regionNotices.isEmpty)
              SliverToBoxAdapter(
                child: _EmptyRegion(
                  sources: _selectedSources.where((s) => s.isNotEmpty).toList(),
                ),
              )
            else
              SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, idx) {
                    final notice = _regionNotices[idx];
                    return NoticeCard(
                      notice:       notice,
                      isBookmarked: false,
                      onTap:        () => _openNotice(context, notice),
                    );
                  },
                  childCount: _regionNotices.length,
                ),
              ),
          ],

          if (_selectedSources.where((s) => s.isNotEmpty).isEmpty)
            const SliverToBoxAdapter(child: _NoRegionBanner()),

          // 하단 여백 (BottomNavigationBar 가림 방지)
          const SliverToBoxAdapter(child: SizedBox(height: 80)),
        ],
      ),
    );
  }
}

// ── 섹션 헤더 ────────────────────────────────
class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final Color    color;
  final String   title;
  final int      count;

  const _SectionHeader({
    required this.icon,
    required this.color,
    required this.title,
    required this.count,
  });

  @override
  Widget build(BuildContext context) {
    return SliverToBoxAdapter(
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
        color: color.withValues(alpha: 0.08),
        child: Row(
          children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(width: 8),
            Text(
              count > 0 ? '$title  $count건' : title,
              style: TextStyle(
                fontSize:   SeniorTheme.fontMD,
                fontWeight: FontWeight.bold,
                color:      color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── 찜 비어있을 때 ───────────────────────────
class _EmptyBookmarks extends StatelessWidget {
  const _EmptyBookmarks();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.symmetric(vertical: 36, horizontal: 32),
      child: Column(
        children: [
          Icon(Icons.favorite_outline, size: 64, color: SeniorTheme.textSecond),
          SizedBox(height: 16),
          Text(
            '아직 찜한 공고가 없어요',
            style: TextStyle(
              fontSize:   SeniorTheme.fontLG,
              fontWeight: FontWeight.bold,
              color:      SeniorTheme.textPrimary,
            ),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: 8),
          Text(
            '홈에서 공고 카드의 ♥ 버튼을 누르면\n여기에 저장돼요.',
            style: TextStyle(
              fontSize: SeniorTheme.fontMD,
              color:    SeniorTheme.textSecond,
              height:   1.6,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

// ── 지역 공고 없을 때 ───────────────────────
class _EmptyRegion extends StatelessWidget {
  final List<String> sources;
  const _EmptyRegion({required this.sources});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 32),
      child: Text(
        '${sources.join(' · ')} 최신 공고가 없습니다.\n아래로 당겨 새로고침 해보세요.',
        style: const TextStyle(
          fontSize: SeniorTheme.fontMD,
          color:    SeniorTheme.textSecond,
          height:   1.6,
        ),
        textAlign: TextAlign.center,
      ),
    );
  }
}

// ── 지역 미설정 안내 배너 ────────────────────
class _NoRegionBanner extends StatelessWidget {
  const _NoRegionBanner();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color:        SeniorTheme.primary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
        border:       Border.all(color: SeniorTheme.primary.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.location_city_outlined,
              size: 36, color: SeniorTheme.primary),
          const SizedBox(width: 14),
          const Expanded(
            child: Text(
              '설정 탭에서 내 지역을 선택하면\n지역 공고를 여기서 바로 볼 수 있어요.',
              style: TextStyle(
                fontSize: SeniorTheme.fontMD,
                color:    SeniorTheme.textPrimary,
                height:   1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
