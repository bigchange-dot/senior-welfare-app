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
  static const List<Map<String, String>> _regions = [
    {'label': '전체',               'source': '',         'topic': ''},
    {'label': '복지로 (중앙정부)',   'source': '복지로',   'topic': 'bokjiro'},
    {'label': '성동구청',           'source': '성동구청', 'topic': 'seongdong'},
    {'label': '강북구청',           'source': '강북구청', 'topic': 'gangbuk'},
  ];

  String _selectedSource = '';
  String _selectedTopic  = '';
  bool   _notifEnabled   = true;

  @override
  void initState() {
    super.initState();
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _selectedSource = prefs.getString('selected_source') ?? '';
      _selectedTopic  = prefs.getString('selected_topic')  ?? '';
      _notifEnabled   = prefs.getBool('notif_enabled')     ?? true;
    });
  }

  Future<void> _saveRegion(Map<String, String> region) async {
    final prefs = await SharedPreferences.getInstance();
    final newSource = region['source'] ?? '';
    final newTopic  = region['topic']  ?? '';

    // FCM 토픽 변경
    await FcmService.instance.updateRegionTopic(
      oldTopic: _selectedTopic.isNotEmpty ? _selectedTopic : null,
      newTopic: newTopic.isNotEmpty       ? newTopic        : null,
    );

    await prefs.setString('selected_source', newSource);
    await prefs.setString('selected_topic',  newTopic);

    setState(() {
      _selectedSource = newSource;
      _selectedTopic  = newTopic;
    });

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            newSource.isEmpty ? '전체 지역으로 설정했습니다.' : '$newSource 공고만 받습니다.',
            style: const TextStyle(fontSize: SeniorTheme.fontSM),
          ),
          backgroundColor: SeniorTheme.primary,
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  Future<void> _toggleNotif(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('notif_enabled', value);

    if (value) {
      await FcmService.instance.updateRegionTopic(newTopic: 'all');
      if (_selectedTopic.isNotEmpty) {
        await FcmService.instance.updateRegionTopic(newTopic: _selectedTopic);
      }
    } else {
      await FcmService.instance.unsubscribeAll();
    }

    setState(() => _notifEnabled = value);
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
          const Text(
            '선택한 지역의 복지 공고만 모아볼 수 있어요.',
            style: TextStyle(
              fontSize: SeniorTheme.fontMD,
              color:    SeniorTheme.textSecond,
            ),
          ),
          const SizedBox(height: 20),

          // 지역 선택 버튼 목록
          ..._regions.map((region) {
            final isSelected = _selectedSource == region['source'];
            return _RegionOptionTile(
              label:      region['label']!,
              isSelected: isSelected,
              onTap:      () => _saveRegion(region),
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
          _InfoRow(label: '버전',   value: '1.0.0'),
          _InfoRow(label: '데이터', value: '복지로 · 성동구청 · 강북구청'),
          _InfoRow(label: 'AI 요약', value: 'Google Gemini 2.5 Flash'),
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
    return GestureDetector(
      onTap: onTap,
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
              isSelected ? Icons.radio_button_checked : Icons.radio_button_off,
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
