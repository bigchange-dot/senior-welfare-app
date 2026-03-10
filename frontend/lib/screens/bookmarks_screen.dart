import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/welfare_notice.dart';
import '../widgets/notice_card.dart';
import '../theme.dart';
import 'webview_screen.dart';

/// 찜 탭 - SharedPreferences에 저장된 공고 ID 목록을 Firestore에서 불러와 표시
class BookmarksScreen extends StatefulWidget {
  const BookmarksScreen({super.key});

  @override
  State<BookmarksScreen> createState() => BookmarksScreenState();
}

// GlobalKey 접근을 위해 public State 클래스
class BookmarksScreenState extends State<BookmarksScreen> {
  List<WelfareNotice> _notices = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    refresh();
  }

  /// 외부(MainScaffold)에서 탭 전환 시 호출해 목록 갱신
  Future<void> refresh() async {
    setState(() => _isLoading = true);

    final prefs = await SharedPreferences.getInstance();
    final ids = prefs.getStringList('bookmarked_ids') ?? [];

    if (ids.isEmpty) {
      setState(() {
        _notices   = [];
        _isLoading = false;
      });
      return;
    }

    try {
      // Firestore whereIn — 한 번에 최대 30개
      final snapshot = await FirebaseFirestore.instance
          .collection('welfare_notices')
          .where(FieldPath.documentId, whereIn: ids.take(30).toList())
          .get();

      final notices = snapshot.docs
          .map((d) => WelfareNotice.fromFirestore(d))
          .toList()
        ..sort((a, b) => b.timestamp.compareTo(a.timestamp));

      setState(() {
        _notices   = notices;
        _isLoading = false;
      });
    } catch (e) {
      debugPrint('찜 목록 로드 오류: $e');
      setState(() => _isLoading = false);
    }
  }

  Future<void> _removeBookmark(String id) async {
    final prefs = await SharedPreferences.getInstance();
    final ids   = List<String>.from(prefs.getStringList('bookmarked_ids') ?? []);
    ids.remove(id);
    await prefs.setStringList('bookmarked_ids', ids);
    setState(() => _notices.removeWhere((n) => n.id == id));
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(color: SeniorTheme.primary),
      );
    }

    if (_notices.isEmpty) {
      return Center(
        child: const Padding(
          padding: EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.favorite_outline,
                  size: 80, color: SeniorTheme.textSecond),
              SizedBox(height: 24),
              Text(
                '아직 찜한 공고가 없어요',
                style: TextStyle(
                  fontSize:   SeniorTheme.fontXL,
                  fontWeight: FontWeight.bold,
                  color:      SeniorTheme.textPrimary,
                ),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: 12),
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
        ),
      );
    }

    return Column(
      children: [
        // 헤더 배너
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
          color: Colors.redAccent.withValues(alpha: 0.08),
          child: Row(
            children: [
              const Icon(Icons.favorite, color: Colors.redAccent, size: 22),
              const SizedBox(width: 8),
              Text(
                '찜한 공고 ${_notices.length}건',
                style: const TextStyle(
                  fontSize:   SeniorTheme.fontMD,
                  fontWeight: FontWeight.bold,
                  color:      Colors.redAccent,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.only(top: 4, bottom: 80),
            itemCount: _notices.length,
            itemBuilder: (context, idx) {
              final notice = _notices[idx];
              return NoticeCard(
                notice:       notice,
                isBookmarked: true,
                onBookmark:   () => _removeBookmark(notice.id),
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
          ),
        ),
      ],
    );
  }
}
