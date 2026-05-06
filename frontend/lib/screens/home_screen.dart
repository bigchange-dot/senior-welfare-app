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
  // 필터 칩 목록 — sources 복수 지정 시 whereIn 쿼리로 구청+복지관 통합 표시
  static const List<_FilterChipData> _filters = [
    _FilterChipData(label: '전체',    sources: []),
    _FilterChipData(label: '복지로',  sources: ['복지로']),
    _FilterChipData(label: '노원구청', sources: ['노원구청', '수락노인복지관']),
    _FilterChipData(label: '도봉구청', sources: ['도봉구청', '도봉노인복지관']),
    _FilterChipData(label: '중랑구청', sources: ['중랑구청']),
    _FilterChipData(label: '마포구청', sources: ['마포구청', '마포노인복지관']),
    _FilterChipData(label: '은평구청', sources: ['은평구청', '은평노인복지관']),
    _FilterChipData(label: '성동구청', sources: ['성동구청', '성동구 어르신일자리']),
    _FilterChipData(label: '강북구청', sources: ['강북구청']),
    _FilterChipData(label: '종로구청', sources: ['종로구청', '종로노인복지관']),
    _FilterChipData(label: '중구청',   sources: ['중구청', '약수노인복지관']),
    _FilterChipData(label: '용산구청', sources: ['용산구청', '용산노인복지관']),
    _FilterChipData(label: '서대문구청', sources: ['서대문구청', '서대문노인복지관']),
    _FilterChipData(label: '강서구청', sources: ['강서구청']),
    _FilterChipData(label: '동작구청', sources: ['동작구청']),
    _FilterChipData(label: '관악구청', sources: ['관악구청']),
    _FilterChipData(label: '양천구청', sources: ['양천구청']),
  ];

  int _selectedFilterIdx = 0;
  List<String> get _selectedSources => _filters[_selectedFilterIdx].sources;

  Set<String> _bookmarkedIds = {};
  late Future<QuerySnapshot> _noticeFuture;

  @override
  void initState() {
    super.initState();
    _loadBookmarks();
    _noticeFuture = _query.get();
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

  List<WelfareNotice> get _filteredMock => _selectedSources.isEmpty
      ? _mockNotices
      : _mockNotices.where((n) => _selectedSources.contains(n.source)).toList();

  // ── Firestore 쿼리 ────────────────────────────
  Query<Map<String, dynamic>> get _query {
    if (_selectedSources.isNotEmpty) {
      // 단일 source는 isEqualTo, 복수(구청+복지관)는 whereIn 사용
      final query = _selectedSources.length == 1
          ? FirebaseFirestore.instance
              .collection('welfare_notices')
              .where('source', isEqualTo: _selectedSources[0])
          : FirebaseFirestore.instance
              .collection('welfare_notices')
              .where('source', whereIn: _selectedSources);
      return query.orderBy('timestamp', descending: true).limit(20);
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
            onSelected: (idx) => setState(() {
              _selectedFilterIdx = idx;
              _noticeFuture = _query.get();
            }),
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
          '${_filters[_selectedFilterIdx].label} 공고가 없습니다.',
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

  // ── Firestore 1회 조회 리스트 (비용 최적화) ───────────────────
  Widget _buildFirestoreList() {
    return RefreshIndicator(
      color: SeniorTheme.primary,
      onRefresh: () async {
        final newFuture = _query.get();
        setState(() => _noticeFuture = newFuture);
        await newFuture;
      },
      child: FutureBuilder<QuerySnapshot>(
        future: _noticeFuture,
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
            return LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                child: SizedBox(
                  height: constraints.maxHeight,
                  child: Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.inbox_outlined, size: 80, color: SeniorTheme.textSecond),
                        const SizedBox(height: 20),
                        Text(
                          _selectedSources.isEmpty ? '아직 등록된 공고가 없습니다.' : '${_filters[_selectedFilterIdx].label} 공고가 없습니다.',
                          style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }

          final notices = snapshot.data!.docs
              .map((doc) => WelfareNotice.fromFirestore(doc))
              .toList();
          final itemCount = notices.length + (notices.length ~/ 5);

          return ListView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
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
      ),
    );
  }
}

// ── 필터 칩 데이터 모델 ──────────────────────────
class _FilterChipData {
  final String label;
  final List<String> sources;
  const _FilterChipData({required this.label, required this.sources});
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
      color: SeniorTheme.background,
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
                    color: selected ? SeniorTheme.primary : Colors.transparent,
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
