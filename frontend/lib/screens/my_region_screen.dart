import 'package:flutter/material.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/welfare_notice.dart';
import '../widgets/notice_card.dart';
import '../theme.dart';
import 'webview_screen.dart';

/// 내 지역 탭 - 설정한 구청 공고만 필터링
/// architecture.md 5.1: SharedPreferences에서 지역 설정 읽어 Firestore where 쿼리 적용
class MyRegionScreen extends StatefulWidget {
  const MyRegionScreen({super.key});

  @override
  State<MyRegionScreen> createState() => _MyRegionScreenState();
}

class _MyRegionScreenState extends State<MyRegionScreen> {
  String? _selectedSource;

  @override
  void initState() {
    super.initState();
    _loadRegion();
  }

  Future<void> _loadRegion() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _selectedSource = prefs.getString('selected_source');
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_selectedSource == null || _selectedSource!.isEmpty) {
      return _buildNoRegionSelected();
    }

    return StreamBuilder<QuerySnapshot>(
      stream: FirebaseFirestore.instance
          .collection('welfare_notices')
          .where('source', isEqualTo: _selectedSource!)
          .orderBy('timestamp', descending: true)
          .limit(30)
          .snapshots(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(
            child: CircularProgressIndicator(color: SeniorTheme.primary),
          );
        }
        if (!snapshot.hasData || snapshot.data!.docs.isEmpty) {
          return Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.location_off_outlined,
                    size: 80, color: SeniorTheme.textSecond),
                const SizedBox(height: 20),
                Text(
                  '$_selectedSource 공고가 없습니다.',
                  style: const TextStyle(
                    fontSize: SeniorTheme.fontMD,
                    color:    SeniorTheme.textSecond,
                  ),
                ),
              ],
            ),
          );
        }

        final notices = snapshot.data!.docs
            .map((doc) => WelfareNotice.fromFirestore(doc))
            .toList();

        return Column(
          children: [
            // 지역 헤더 배너
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
              color: SeniorTheme.sourceColor(_selectedSource!).withValues(alpha: 0.1),
              child: Row(
                children: [
                  Icon(Icons.location_on,
                      color: SeniorTheme.sourceColor(_selectedSource!), size: 24),
                  const SizedBox(width: 8),
                  Text(
                    '$_selectedSource 공고 (${notices.length}건)',
                    style: TextStyle(
                      fontSize:   SeniorTheme.fontMD,
                      fontWeight: FontWeight.bold,
                      color:      SeniorTheme.sourceColor(_selectedSource!),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.only(top: 4, bottom: 80),
                itemCount: notices.length,
                itemBuilder: (context, idx) => NoticeCard(
                  notice: notices[idx],
                  onTap: () => Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (_) => WebViewScreen(
                        url:   notices[idx].url,
                        title: notices[idx].aiSummary,
                        docId: notices[idx].id,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildNoRegionSelected() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.location_city_outlined,
                size: 80, color: SeniorTheme.textSecond),
            const SizedBox(height: 24),
            const Text(
              '내 지역을 선택해 주세요',
              style: TextStyle(
                fontSize:   SeniorTheme.fontXL,
                fontWeight: FontWeight.bold,
                color:      SeniorTheme.textPrimary,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            const Text(
              '아래 설정 탭에서 구청을 선택하면\n해당 지역 공고만 모아볼 수 있어요.',
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
}
