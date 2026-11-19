import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/welfare_notice.dart';
import '../regions.dart';
import '../services/region_prefs.dart';
import '../widgets/fortune_card.dart';
import '../widgets/notice_card.dart';
import '../theme.dart';
import 'region_picker_screen.dart';
import 'webview_screen.dart';

/// 홈 탭 보기 — 내 지역 / 전체 / 복지로
enum _HomeView { mine, all, bokjiro }

/// 홈 탭 - 최신 공고 목록
///
/// v1.5 (2026-11-18): 구청 칩 13개 가로 스크롤 → 위에 '내 지역' 표시 + [지역 바꾸기] 버튼,
/// 칩은 [내 지역] [전체] [복지로] 세 개. 지역은 공고 문서의 `region` 필드로 찾는다 (출처 이름 목록 대신).
/// kIsWeb == true 시 목 데이터로 UI 테스트
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => HomeScreenState();
}

class HomeScreenState extends State<HomeScreen> {
  List<String> _myRegions = RegionPrefs.selected.value;
  _HomeView _view = RegionPrefs.selected.value.isEmpty ? _HomeView.all : _HomeView.mine;

  Set<String> _bookmarkedIds = {};
  late Future<QuerySnapshot> _noticeFuture;

  @override
  void initState() {
    super.initState();
    _loadBookmarks();
    _noticeFuture = _query.get();
    RegionPrefs.selected.addListener(_onRegionsChanged);
  }

  @override
  void dispose() {
    RegionPrefs.selected.removeListener(_onRegionsChanged);
    super.dispose();
  }

  /// 지역 선택 화면(홈·설정 어디서 열었든)에서 내 지역이 바뀌면 목록을 다시 받는다
  void _onRegionsChanged() {
    final regions = RegionPrefs.selected.value;
    setState(() {
      // 처음 고르면 바로 내 지역을 보여 주고, 다 빼면 전체로
      if (_myRegions.isEmpty && regions.isNotEmpty) _view = _HomeView.mine;
      if (regions.isEmpty && _view == _HomeView.mine) _view = _HomeView.all;
      _myRegions = regions;
      _noticeFuture = _query.get();
    });
  }

  void _setView(_HomeView view) {
    setState(() {
      _view = view;
      _noticeFuture = _query.get();
    });
  }

  void _openPicker() {
    Navigator.push(context, MaterialPageRoute(builder: (_) => const RegionPickerScreen()));
  }

  String get _viewLabel => switch (_view) {
        _HomeView.mine    => regionNames(_myRegions),
        _HomeView.all     => '전체',
        _HomeView.bokjiro => '복지로',
      };

  /// 앱바 새로고침 버튼·당겨서 새로고침·다시 시도 버튼에서 호출. 서버에서 다시 받는다
  /// (기본 get()은 연결이 막 돌아온 직후 캐시를 돌려줄 수 있어 화면이 회복되지 않았음)
  Future<void> refresh() async {
    final future = _query.get(const GetOptions(source: Source.server));
    // 화살표 함수로 쓰면 대입값(Future)을 돌려줘 setState가 예외를 던진다.
    // 출시본(v1.4.0)의 당겨서 새로고침이 이 때문에 동작하지 않았음 (2026-11-17 앱 점검)
    setState(() {
      _noticeFuture = future;
    });
    try {
      await future;
    } catch (_) {
      // 오류는 FutureBuilder가 화면에 표시
    }
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
    WelfareNotice(id: 'm0', title: '2026년 어르신 공공일자리 사업 참여자 모집 공고',   aiSummary: '📢 어르신 공공일자리 모집 시작!',    source: '성동구청', region: 'seongdong', url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 1)),  isNotified: true),
    WelfareNotice(id: 'm1', title: '노원구 65세 이상 무료 건강검진 안내',              aiSummary: '🏥 노원구 무료 건강검진 접수 오픈!',  source: '노원구청', region: 'nowon',     url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 4)),  isNotified: true),
    WelfareNotice(id: 'm2', title: '중앙정부 기초연금 수급자격 완화 발표',             aiSummary: '💰 기초연금 수급 범위 확대 확정!',    source: '복지로',   region: 'bokjiro',   url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 7)),  isNotified: true),
    WelfareNotice(id: 'm3', title: '성동구 시니어클럽 단기일자리 100명 모집',         aiSummary: '👷 시니어클럽 단기일자리 100명!',    source: '성동구청', region: 'seongdong', url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 10)), isNotified: true),
    WelfareNotice(id: 'm4', title: '복지로 노인맞춤돌봄서비스 신청 접수',             aiSummary: '🤝 노인맞춤돌봄 신청 받습니다!',     source: '복지로',   region: 'bokjiro',   url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 13)), isNotified: true),
    WelfareNotice(id: 'm5', title: '노원구 어르신 무료 치과 진료 지원',               aiSummary: '🦷 어르신 무료 치과 진료 신청!',     source: '수락노인복지관', region: 'nowon', url: 'https://www.bokjiro.go.kr', timestamp: DateTime.now().subtract(const Duration(hours: 16)), isNotified: true),
  ];

  List<WelfareNotice> get _filteredMock => switch (_view) {
        _HomeView.all     => _mockNotices,
        _HomeView.bokjiro => _mockNotices.where((n) => n.source == '복지로').toList(),
        _HomeView.mine    => _mockNotices.where((n) => _myRegions.contains(n.region)).toList(),
      };

  // ── Firestore 쿼리 ────────────────────────────
  Query<Map<String, dynamic>> get _query {
    final notices = FirebaseFirestore.instance.collection('welfare_notices');
    final Query<Map<String, dynamic>> filtered = switch (_view) {
      // 지역은 최대 3곳 → whereIn 한도(30) 안. 색인: region + timestamp (firestore.indexes.json)
      _HomeView.mine    => _myRegions.length == 1
          ? notices.where('region', isEqualTo: _myRegions.first)
          : notices.where('region', whereIn: _myRegions),
      _HomeView.bokjiro => notices.where('source', isEqualTo: '복지로'),
      _HomeView.all     => notices,
    };
    return filtered.orderBy('timestamp', descending: true).limit(20);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SeniorTheme.background,
      body: Column(
        children: [
          // ── 오늘의 운세 카드 (v1.6)
          const FortuneCard(),

          // ── 내 지역 + 지역 바꾸기
          _RegionHeader(regions: _myRegions, onChange: _openPicker),

          // ── 보기 칩 (내 지역 / 전체 / 복지로)
          _ViewChipBar(
            hasRegions: _myRegions.isNotEmpty,
            selected:   _view,
            onSelected: _setView,
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
          '$_viewLabel 공고가 없습니다.',
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
      onRefresh: refresh,
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
            return _MessageView(
              icon:    Icons.wifi_off,
              message: '공고를 불러오지 못했어요.\n인터넷 연결을 확인해 주세요.',
              onRetry: refresh,
            );
          }

          final data = snapshot.data;
          // 인터넷 없이 처음 열면 Firestore가 오류 대신 '캐시의 빈 결과'를 준다 →
          // "공고가 없습니다"로 보이면 어르신은 정말 공고가 없다고 여김 (2026-11-17 앱 점검)
          if (data != null && data.docs.isEmpty && data.metadata.isFromCache) {
            return _MessageView(
              icon:    Icons.wifi_off,
              message: '인터넷에 연결되어 있지 않아요.\n연결한 뒤 다시 시도해 주세요.',
              onRetry: refresh,
            );
          }

          if (data == null || data.docs.isEmpty) {
            return _MessageView(
              icon:    Icons.inbox_outlined,
              message: _view == _HomeView.all
                  ? '아직 등록된 공고가 없습니다.'
                  : '$_viewLabel 공고가 아직 없어요.',
            );
          }

          final notices = data.docs
              .map((doc) => WelfareNotice.fromFirestore(doc))
              .toList();
          // 인터넷이 끊겨 저장된 공고를 보여 줄 때는 맨 위에 안내 한 줄
          final offline   = data.metadata.isFromCache;
          final head      = offline ? 1 : 0;
          final itemCount = head + notices.length + (notices.length ~/ 5);

          return ListView.builder(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.only(top: 8, bottom: 80),
            itemCount: itemCount,
            itemBuilder: (context, i) {
              if (offline && i == 0) return const _OfflineNotice();
              final idx = i - head;
              if ((idx + 1) % 6 == 0) return const BannerAdCard();
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

// ── 안내 화면 (빈 목록·오류·오프라인) ──────────────
/// 당겨서 새로고침이 되도록 스크롤 가능하게 만들고, onRetry가 있으면 '다시 시도' 버튼을 보인다.
/// 예전 오류 화면은 스크롤이 안 돼 당겨서 새로고침도, 버튼도 없어 빠져나갈 수 없었음.
class _MessageView extends StatelessWidget {
  final IconData icon;
  final String   message;
  final Future<void> Function()? onRetry;

  const _MessageView({required this.icon, required this.message, this.onRetry});

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 80, color: SeniorTheme.textSecond),
                const SizedBox(height: 20),
                Text(
                  message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond, height: 1.5),
                ),
                if (onRetry != null) ...[
                  const SizedBox(height: 28),
                  SizedBox(
                    width: 220,
                    child: ElevatedButton.icon(
                      onPressed: onRetry,
                      icon:  const Icon(Icons.refresh, size: 26),
                      label: const Text('다시 시도'),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// 인터넷이 끊겨 저장된 공고를 보여 줄 때 목록 맨 위 안내
class _OfflineNotice extends StatelessWidget {
  const _OfflineNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      margin:  const EdgeInsets.fromLTRB(16, 4, 16, 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color:        const Color(0xFFFFF3E0),
        borderRadius: BorderRadius.circular(12),
      ),
      child: const Row(
        children: [
          Icon(Icons.wifi_off, color: SeniorTheme.orangeAccent, size: 26),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              '인터넷에 연결되어 있지 않아 저장된 공고를 보여 드려요. 아래로 당기면 새로고침돼요.',
              style: TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textPrimary, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

// ── 내 지역 표시 + 지역 바꾸기 버튼 ─────────────────
class _RegionHeader extends StatelessWidget {
  final List<String> regions;
  final VoidCallback onChange;

  const _RegionHeader({required this.regions, required this.onChange});

  @override
  Widget build(BuildContext context) {
    final none = regions.isEmpty;
    return Container(
      color: SeniorTheme.surface,
      padding: const EdgeInsets.fromLTRB(16, 12, 12, 12),
      child: Row(
        children: [
          const Icon(Icons.location_on, color: SeniorTheme.primary, size: 28),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              none ? '내 지역을 고르면 우리 동네 공고만 모아 볼 수 있어요' : regionNames(regions),
              style: TextStyle(
                fontSize:   none ? SeniorTheme.fontSM : SeniorTheme.fontMD,
                fontWeight: none ? FontWeight.normal : FontWeight.bold,
                color:      none ? SeniorTheme.textSecond : SeniorTheme.textPrimary,
                height:     1.3,
              ),
            ),
          ),
          const SizedBox(width: 8),
          OutlinedButton(
            onPressed: onChange,
            style: OutlinedButton.styleFrom(
              minimumSize:     const Size(0, 52),
              padding:         const EdgeInsets.symmetric(horizontal: 14),
              side:            const BorderSide(color: SeniorTheme.primary, width: 2),
              foregroundColor: SeniorTheme.primary,
              textStyle:       const TextStyle(fontSize: SeniorTheme.fontSM, fontWeight: FontWeight.bold),
              shape:           RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            child: Text(none ? '지역 고르기' : '지역 바꾸기'),
          ),
        ],
      ),
    );
  }
}

// ── 보기 칩 (내 지역 / 전체 / 복지로) — 세 개라 스크롤 없이 한 줄에 들어간다 ──
class _ViewChipBar extends StatelessWidget {
  final bool hasRegions;
  final _HomeView selected;
  final ValueChanged<_HomeView> onSelected;

  const _ViewChipBar({required this.hasRegions, required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    final chips = [
      if (hasRegions) (_HomeView.mine, '내 지역'),
      (_HomeView.all, '전체'),
      (_HomeView.bokjiro, '복지로'),
    ];
    return Container(
      width: double.infinity,   // 칩을 위 '내 지역' 줄과 같은 왼쪽에 맞춤 (태블릿에서 가운데로 몰렸음)
      color: SeniorTheme.background,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final (view, label) in chips)
            Semantics(
              button: true,
              selected: view == selected,
              child: GestureDetector(
                onTap: () => onSelected(view),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  constraints: const BoxConstraints(minHeight: 48),
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                  decoration: BoxDecoration(
                    color: view == selected ? SeniorTheme.primary : Colors.transparent,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: view == selected ? SeniorTheme.primary : SeniorTheme.divider,
                      width: 1.5,
                    ),
                  ),
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize:   SeniorTheme.fontSM,
                      fontWeight: FontWeight.bold,
                      color: view == selected ? Colors.white : SeniorTheme.textPrimary,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
