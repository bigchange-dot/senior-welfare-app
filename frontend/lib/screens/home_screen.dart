import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/welfare_notice.dart';
import '../widgets/notice_card.dart';
import '../theme.dart';
import 'webview_screen.dart';

/// 홈 탭 - 최신 속보 목록 (실시간 스트림 + 출처 필터 칩)
/// figma.md: 필터 칩 ["전체", "성동구청", "강북구청", "복지로"]
/// kIsWeb == true 시 목 데이터로 UI 테스트
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  // 필터 칩 목록 (figma.md 순서)
  static const List<_FilterChipData> _filters = [
    _FilterChipData(label: '전체',    source: ''),
    _FilterChipData(label: '성동구청', source: '성동구청'),
    _FilterChipData(label: '강북구청', source: '강북구청'),
    _FilterChipData(label: '복지로',  source: '복지로'),
  ];

  int _selectedFilterIdx = 0;
  String get _selectedSource => _filters[_selectedFilterIdx].source;

  Set<String> _bookmarkedIds = {};

  @override
  void initState() {
    super.initState();
    _loadBookmarks();
  }

  Future<void> _loadBookmarks() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _bookmarkedIds = Set<String>.from(prefs.getStringList('bookmarked_ids') ?? []);
    });
  }

  Future<void> _toggleBookmark(String id) async {
    final prefs = await SharedPreferences.getInstance();
    final ids   = List<String>.from(prefs.getStringList('bookmarked_ids') ?? []);
    if (ids.contains(id)) {
      ids.remove(id);
    } else {
      ids.add(id);
    }
    await prefs.setStringList('bookmarked_ids', ids);
    setState(() => _bookmarkedIds = Set<String>.from(ids));
  }

  // ── 웹 테스트용 목 데이터 ─────────────────────
  static final List<WelfareNotice> _mockNotices = [
    WelfareNotice(id: 'm0', title: '2026년 어르신 공공일자리 사업 참여자 모집 공고',   aiSummary: '📢 어르신 공공일자리 모집 시작!',    source: '성동구청', url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 1)),  isNotified: true),
    WelfareNotice(id: 'm1', title: '강북구 65세 이상 무료 건강검진 안내',              aiSummary: '🏥 강북구 무료 건강검진 접수 오픈!',  source: '강북구청', url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 4)),  isNotified: true),
    WelfareNotice(id: 'm2', title: '중앙정부 기초연금 수급자격 완화 발표',             aiSummary: '💰 기초연금 수급 범위 확대 확정!',    source: '복지로',   url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 7)),  isNotified: true),
    WelfareNotice(id: 'm3', title: '성동구 시니어클럽 단기일자리 100명 모집',         aiSummary: '👷 시니어클럽 단기일자리 100명!',    source: '성동구청', url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 10)), isNotified: true),
    WelfareNotice(id: 'm4', title: '복지로 노인맞춤돌봄서비스 신청 접수',             aiSummary: '🤝 노인맞춤돌봄 신청 받습니다!',     source: '복지로',   url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 13)), isNotified: true),
    WelfareNotice(id: 'm5', title: '강북구 어르신 무료 치과 진료 지원',               aiSummary: '🦷 어르신 무료 치과 진료 신청!',     source: '강북구청', url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 16)), isNotified: true),
  ];

  List<WelfareNotice> get _filteredMock => _selectedSource.isEmpty
      ? _mockNotices
      : _mockNotices.where((n) => n.source == _selectedSource).toList();

  // ── Firestore 쿼리 ────────────────────────────
  Query<Map<String, dynamic>> get _query {
    if (_selectedSource.isNotEmpty) {
      return FirebaseFirestore.instance
          .collection('welfare_notices')
          .where('source', isEqualTo: _selectedSource)
          .orderBy('timestamp', descending: true)
          .limit(20);
    }
    return FirebaseFirestore.instance
        .collection('welfare_notices')
        .orderBy('timestamp', descending: true)
        .limit(20);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SeniorTheme.background,
      body: Column(
        children: [
          // ── 필터 칩 바
          _FilterChipBar(
            filters:     _filters,
            selectedIdx: _selectedFilterIdx,
            onSelected:  (idx) => setState(() => _selectedFilterIdx = idx),
          ),

          // ── 공고 리스트
          Expanded(
            child: kIsWeb ? _buildMockList() : _buildFirestoreList(),
          ),
        ],
      ),
    );
  }

  // ── 웹 목 데이터 리스트 ───────────────────────
  Widget _buildMockList() {
    final notices = _filteredMock;
    if (notices.isEmpty) {
      return Center(
        child: Text(
          '$_selectedSource 공고가 없습니다.',
          style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond),
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.only(top: 8, bottom: 80),
      itemCount: notices.length,
      itemBuilder: (context, idx) => NoticeCard(
        notice:       notices[idx],
        isBookmarked: _bookmarkedIds.contains(notices[idx].id),
        onBookmark:   () => _toggleBookmark(notices[idx].id),
        onTap: () {
          launchUrl(
            Uri.parse(notices[idx].url),
            mode: LaunchMode.externalApplication,
          );
        },
      ),
    );
  }

  // ── Firestore 실시간 리스트 ───────────────────
  Widget _buildFirestoreList() {
    return StreamBuilder<QuerySnapshot>(
      stream: _query.snapshots(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircularProgressIndicator(color: SeniorTheme.primary),
                SizedBox(height: 20),
                Text(
                  '최신 복지 소식을 불러오는 중...',
                  style: TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond),
                ),
              ],
            ),
          );
        }

        if (snapshot.hasError) {
          return const Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.error_outline, size: 64, color: Colors.red),
                SizedBox(height: 16),
                Text(
                  '잠시 후 다시 시도해 주세요.',
                  style: TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond),
                ),
              ],
            ),
          );
        }

        if (!snapshot.hasData || snapshot.data!.docs.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.inbox_outlined, size: 80, color: SeniorTheme.textSecond),
                const SizedBox(height: 20),
                Text(
                  _selectedSource.isEmpty ? '아직 등록된 공고가 없습니다.' : '$_selectedSource 공고가 없습니다.',
                  style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond),
                ),
              ],
            ),
          );
        }

        final notices = snapshot.data!.docs
            .map((doc) => WelfareNotice.fromFirestore(doc))
            .toList();
        final itemCount = notices.length + (notices.length ~/ 5);

        return ListView.builder(
          padding: const EdgeInsets.only(top: 8, bottom: 80),
          itemCount: itemCount,
          itemBuilder: (context, idx) {
            if ((idx + 1) % 6 == 0) return const AdPlaceholderCard();
            final noticeIdx = idx - (idx ~/ 6);
            if (noticeIdx >= notices.length) return const SizedBox.shrink();
            final notice = notices[noticeIdx];
            return NoticeCard(
              notice:       notice,
              isBookmarked: _bookmarkedIds.contains(notice.id),
              onBookmark:   () => _toggleBookmark(notice.id),
              onTap: () => Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (_) => WebViewScreen(
                    url:   notice.url,
                    title: notice.aiSummary,
                    docId: notice.id,
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }
}

// ── 필터 칩 데이터 모델 ──────────────────────────
class _FilterChipData {
  final String label;
  final String source;
  const _FilterChipData({required this.label, required this.source});
}

// ── 필터 칩 바 위젯 ─────────────────────────────
class _FilterChipBar extends StatelessWidget {
  final List<_FilterChipData> filters;
  final int        selectedIdx;
  final ValueChanged<int> onSelected;

  const _FilterChipBar({
    required this.filters,
    required this.selectedIdx,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: SeniorTheme.surface,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: List.generate(filters.length, (idx) {
            final selected = idx == selectedIdx;
            return Padding(
              padding: const EdgeInsets.only(right: 8),
              child: GestureDetector(
                onTap: () => onSelected(idx),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                  decoration: BoxDecoration(
                    color: selected ? SeniorTheme.primary : SeniorTheme.background,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: selected ? SeniorTheme.primary : SeniorTheme.divider,
                      width: 1.5,
                    ),
                  ),
                  child: Text(
                    filters[idx].label,
                    style: TextStyle(
                      fontSize:   SeniorTheme.fontSM,
                      fontWeight: FontWeight.bold,
                      color: selected ? Colors.white : SeniorTheme.textPrimary,
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
