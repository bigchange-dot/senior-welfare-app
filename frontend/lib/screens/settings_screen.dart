import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/fcm_service.dart';
import '../theme.dart';

/// 설정 탭 - 지역 선택 + 알림 ON/OFF
/// architecture.md 5.1: 직관적인 단순 UI, 초대형 터치 영역
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  // 선택 가능한 지역 목록 (source 값 + 표시명 + FCM 토픽)
  // 강북(수집 제외)·강서·동작·관악(공고 0건)은 뺌 (2026-11-17). 되살릴 때 home_screen.dart _filters도 함께.
  // FcmService.allTopics에는 남겨 둔다 (예전에 구독한 토픽을 해지할 수 있게)
  static const List<Map<String, String>> _regions = [
    {'label': '전체',               'source': '',         'topic': ''},
    {'label': '복지로 (중앙정부)',   'source': '복지로',   'topic': 'bokjiro'},
    {'label': '노원구청',           'source': '노원구청', 'topic': 'nowon'},
    {'label': '도봉구청',           'source': '도봉구청', 'topic': 'dobong'},
    {'label': '중랑구청',           'source': '중랑구청', 'topic': 'jungnang'},
    {'label': '마포구청',           'source': '마포구청', 'topic': 'mapo'},
    {'label': '은평구청',           'source': '은평구청', 'topic': 'eunpyeong'},
    {'label': '성동구청',           'source': '성동구청', 'topic': 'seongdong'},
    {'label': '종로구청',           'source': '종로구청', 'topic': 'jongno'},
    {'label': '중구청',             'source': '중구청',   'topic': 'junggu'},
    {'label': '용산구청',           'source': '용산구청', 'topic': 'yongsan'},
    {'label': '서대문구청',         'source': '서대문구청','topic': 'seodaemun'},
    {'label': '양천구청',           'source': '양천구청', 'topic': 'yangcheon'},
  ];

  List<String> _selectedSources = [];
  List<String> _selectedTopics  = [];
  bool         _notifEnabled    = true;

  static const int _maxRegions = 3;

  @override
  void initState() {
    super.initState();
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final prefs   = await SharedPreferences.getInstance();
    final sources = prefs.getStringList('selected_sources') ?? [];
    final topics  = prefs.getStringList('selected_topics')  ?? [];

    // 목록에서 뺀 지역을 예전에 골라 둔 경우 정리 (화면에 없어 해제할 수 없고 3개 상한만 차지함)
    final validSources = _regions.map((r) => r['source']!).toSet();
    final validTopics  = _regions.map((r) => r['topic']!).toSet();
    final keptSources  = sources.where(validSources.contains).toList();
    final keptTopics   = topics.where(validTopics.contains).toList();
    if (keptSources.length != sources.length || keptTopics.length != topics.length) {
      await prefs.setStringList('selected_sources', keptSources);
      await prefs.setStringList('selected_topics',  keptTopics);
      await FcmService.instance.syncSubscriptions();
    }

    if (!mounted) return;
    setState(() {
      _selectedSources = keptSources;
      _selectedTopics  = keptTopics;
      _notifEnabled    = prefs.getBool('notif_enabled') ?? true;
    });
  }

  Future<void> _toggleRegion(Map<String, String> region) async {
    final source = region['source'] ?? '';
    final topic  = region['topic']  ?? '';

    final isSelected = _selectedSources.contains(source);

    // 최대 3개 초과 시 안내
    if (!isSelected && _selectedSources.length >= _maxRegions) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              '최대 3개까지 선택할 수 있어요.',
              style: TextStyle(fontSize: SeniorTheme.fontSM),
            ),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 2),
          ),
        );
      }
      return;
    }

    // 즉시 UI 업데이트
    final newSources = List<String>.from(_selectedSources);
    final newTopics  = List<String>.from(_selectedTopics);

    if (isSelected) {
      newSources.remove(source);
      newTopics.remove(topic);
    } else {
      newSources.add(source);
      if (topic.isNotEmpty) newTopics.add(topic);
    }

    setState(() {
      _selectedSources = newSources;
      _selectedTopics  = newTopics;
    });

    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList('selected_sources', newSources);
    await prefs.setStringList('selected_topics',  newTopics);

    // FCM 토픽 동기화 (지역 선택 여부에 따라 all ↔ 지역 토픽 전환, 중복 알림 방지)
    await FcmService.instance.syncSubscriptions();

    if (mounted) {
      final msg = isSelected
          ? '${region['label']} 선택 해제'
          : '${region['label']} 선택됨 (${newSources.length}/$_maxRegions)';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(msg, style: const TextStyle(fontSize: SeniorTheme.fontSM)),
          backgroundColor: SeniorTheme.primary,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  Future<void> _toggleNotif(bool value) async {
    // 즉시 UI 업데이트 (낙관적)
    setState(() => _notifEnabled = value);

    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('notif_enabled', value);

    // ON → 저장된 지역 설정대로 구독, OFF → 전체 토픽 해지
    await FcmService.instance.syncSubscriptions();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SeniorTheme.background,
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          // ── 지역 선택 섹션 ──
          const Text(
            '📍 내 지역 설정',
            style: TextStyle(
              fontSize:   SeniorTheme.fontXL,
              fontWeight: FontWeight.bold,
              color:      SeniorTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              const Expanded(
                child: Text(
                  '고른 지역의 새 공고를 알림으로 받고, 찜 탭에서 모아볼 수 있어요. 고르지 않으면 모든 지역 알림을 받아요.',
                  style: TextStyle(
                    fontSize: SeniorTheme.fontMD,
                    color:    SeniorTheme.textSecond,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color:        SeniorTheme.primary.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  '${_selectedSources.length}/$_maxRegions 선택',
                  style: const TextStyle(
                    fontSize:   SeniorTheme.fontSM,
                    fontWeight: FontWeight.bold,
                    color:      SeniorTheme.primary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // 지역 선택 버튼 목록
          ..._regions.map((region) {
            final isSelected = _selectedSources.contains(region['source']);
            return _RegionOptionTile(
              label:      region['label']!,
              isSelected: isSelected,
              onTap:      () => _toggleRegion(region),
            );
          }),

          const SizedBox(height: 36),
          const Divider(),
          const SizedBox(height: 24),

          // ── 알림 설정 섹션 ──
          const Text(
            '🔔 알림 설정',
            style: TextStyle(
              fontSize:   SeniorTheme.fontXL,
              fontWeight: FontWeight.bold,
              color:      SeniorTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 16),
          _NotifToggleTile(
            enabled:  _notifEnabled,
            onToggle: _toggleNotif,
          ),

          const SizedBox(height: 36),
          const Divider(),
          const SizedBox(height: 24),

          // ── 앱 정보 ──
          const Text(
            'ℹ️ 앱 정보',
            style: TextStyle(
              fontSize:   SeniorTheme.fontXL,
              fontWeight: FontWeight.bold,
              color:      SeniorTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 12),
          _InfoRow(label: '버전',    value: '1.1.0'),
          _InfoRow(label: 'AI 요약', value: 'Gemini'),
        ],
      ),
    );
  }
}

// ── 서브 위젯 ──

class _RegionOptionTile extends StatelessWidget {
  final String    label;
  final bool      isSelected;
  final VoidCallback onTap;

  const _RegionOptionTile({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(
          vertical:   SeniorTheme.touchPaddingV,
          horizontal: SeniorTheme.touchPaddingH,
        ),
        decoration: BoxDecoration(
          color:        isSelected ? SeniorTheme.primary : SeniorTheme.surface,
          borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
          border:       Border.all(
            color:     isSelected ? SeniorTheme.primary : SeniorTheme.divider,
            width:     2,
          ),
        ),
        child: Row(
          children: [
            Icon(
              isSelected ? Icons.check_box : Icons.check_box_outline_blank,
              color: isSelected ? Colors.white : SeniorTheme.textSecond,
              size:  28,
            ),
            const SizedBox(width: 14),
            Text(
              label,
              style: TextStyle(
                fontSize:   SeniorTheme.fontMD,
                fontWeight: FontWeight.bold,
                color:      isSelected ? Colors.white : SeniorTheme.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NotifToggleTile extends StatelessWidget {
  final bool     enabled;
  final Function(bool) onToggle;

  const _NotifToggleTile({required this.enabled, required this.onToggle});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        vertical:   SeniorTheme.touchPaddingV,
        horizontal: SeniorTheme.touchPaddingH,
      ),
      decoration: BoxDecoration(
        color:        SeniorTheme.surface,
        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
        border:       Border.all(color: SeniorTheme.divider),
      ),
      child: Row(
        children: [
          const Icon(Icons.notifications_outlined,
              size: 32, color: SeniorTheme.primary),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '새 공고 푸시 알림',
                  style: TextStyle(
                    fontSize:   SeniorTheme.fontMD,
                    fontWeight: FontWeight.bold,
                    color:      SeniorTheme.textPrimary,
                  ),
                ),
                Text(
                  enabled ? '알림 받는 중' : '알림 꺼짐',
                  style: const TextStyle(
                    fontSize: SeniorTheme.fontSM,
                    color:    SeniorTheme.textSecond,
                  ),
                ),
              ],
            ),
          ),
          Switch(
            value:           enabled,
            onChanged:       onToggle,
            activeThumbColor: SeniorTheme.primary,
            trackOutlineColor: WidgetStatePropertyAll(SeniorTheme.divider),
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          SizedBox(
            width: 80,
            child: Text(
              label,
              style: const TextStyle(
                fontSize: SeniorTheme.fontSM,
                color:    SeniorTheme.textSecond,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontSize:   SeniorTheme.fontSM,
                color:      SeniorTheme.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
