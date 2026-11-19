import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../regions.dart';
import '../services/fcm_service.dart';
import '../services/fortune_prefs.dart';
import '../services/region_prefs.dart';
import '../theme.dart';
import 'fortune_screen.dart';
import 'region_picker_screen.dart';

/// 설정 탭 - 내 지역(지역 선택 화면) + 알림 ON/OFF
/// architecture.md 5.1: 직관적인 단순 UI, 초대형 터치 영역
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _notifEnabled = true;

  @override
  void initState() {
    super.initState();
    _loadPrefs();
  }

  Future<void> _loadPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() => _notifEnabled = prefs.getBool('notif_enabled') ?? true);
  }

  Future<void> _toggleNotif(bool value) async {
    // 즉시 UI 업데이트 (낙관적)
    setState(() => _notifEnabled = value);

    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('notif_enabled', value);

    // ON → 저장된 지역 설정대로 구독, OFF → 전체 토픽 해지
    await FcmService.instance.syncSubscriptions();
  }

  /// 운세 알림 스위치. 켤 때 휴대폰 알림 권한이 없으면 요청하고, 거부되면 꺼진 채로 안내
  Future<void> _toggleFortuneNotif(bool value) async {
    if (value && !await FcmService.instance.requestPermission()) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('휴대폰 설정에서 알림을 허용해 주세요.', style: TextStyle(fontSize: SeniorTheme.fontSM)),
      ));
      return;
    }
    await FortunePrefs.setNotif(value);
  }

  void _openPicker() {
    Navigator.push(context, MaterialPageRoute(builder: (_) => const RegionPickerScreen()));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SeniorTheme.background,
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          // ── 내 지역 섹션 ── (v1.5: 긴 체크 목록 대신 지역 선택 화면, 홈과 같은 설정)
          const Text(
            '📍 내 지역',
            style: TextStyle(
              fontSize:   SeniorTheme.fontXL,
              fontWeight: FontWeight.bold,
              color:      SeniorTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '고른 지역의 새 공고를 알림으로 받고, 홈과 찜 탭에서 모아 볼 수 있어요. '
            '고르지 않으면 서울·경기의 모든 공고 알림을 받아요.',
            style: TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond, height: 1.4),
          ),
          const SizedBox(height: 16),
          ValueListenableBuilder<List<String>>(
            valueListenable: RegionPrefs.selected,
            builder: (context, regions, _) => _MyRegionCard(regions: regions, onChange: _openPicker),
          ),
          ValueListenableBuilder<List<String>>(
            valueListenable: RegionPrefs.selected,
            builder: (context, regions, _) => regions.isEmpty
                ? const SizedBox.shrink()
                : Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: ValueListenableBuilder<bool>(
                      valueListenable: RegionPrefs.bokjiroNotif,
                      builder: (context, on, _) => _SwitchTile(
                        icon:     Icons.public,
                        title:    '전국 공고(복지로)도 알림 받기',
                        subtitle: on ? '받는 중' : '받지 않음',
                        value:    on,
                        onChanged: RegionPrefs.setBokjiroNotif,
                      ),
                    ),
                  ),
          ),

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
          const SizedBox(height: 12),
          // 운세 알림은 공고 알림과 따로 켜고 끈다 (v1.6)
          ValueListenableBuilder<bool>(
            valueListenable: FortunePrefs.notif,
            builder: (context, on, _) => _SwitchTile(
              icon:     Icons.wb_sunny_outlined,
              title:    '오늘의 운세 알림',
              subtitle: on ? '매일 아침 7시에 받는 중' : '받지 않음',
              value:    on,
              onChanged: _toggleFortuneNotif,
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const FortuneScreen(source: 'settings')),
            ),
            style: OutlinedButton.styleFrom(
              minimumSize:     const Size.fromHeight(56),
              side:            const BorderSide(color: SeniorTheme.primary, width: 2),
              foregroundColor: SeniorTheme.primary,
              textStyle:       const TextStyle(fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold),
              shape:           RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
            icon:  const Text('🔮', style: TextStyle(fontSize: 22)),
            label: const Text('오늘의 운세 보기'),
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
          const _InfoRow(label: '버전',    value: '1.6.0'),
          const _InfoRow(label: '지역',    value: '서울 · 경기'),
        ],
      ),
    );
  }
}

// ── 서브 위젯 ──

/// 고른 지역 + [지역 고르기/바꾸기] 버튼
class _MyRegionCard extends StatelessWidget {
  final List<String> regions;
  final VoidCallback onChange;

  const _MyRegionCard({required this.regions, required this.onChange});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: SeniorTheme.touchPaddingH),
      decoration: BoxDecoration(
        color:        SeniorTheme.surface,
        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
        border:       Border.all(color: SeniorTheme.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            regions.isEmpty ? '고른 지역 없음 (서울·경기 전체)' : regionNames(regions),
            style: TextStyle(
              fontSize:   SeniorTheme.fontLG,
              fontWeight: FontWeight.bold,
              color:      regions.isEmpty ? SeniorTheme.textSecond : SeniorTheme.textPrimary,
            ),
          ),
          const SizedBox(height: 14),
          ElevatedButton.icon(
            onPressed: onChange,
            icon:  const Icon(Icons.edit_location_alt, size: 26),
            label: Text(regions.isEmpty ? '내 지역 고르기' : '지역 바꾸기'),
          ),
        ],
      ),
    );
  }
}

class _SwitchTile extends StatelessWidget {
  final IconData icon;
  final String   title;
  final String   subtitle;
  final bool     value;
  final ValueChanged<bool> onChanged;

  const _SwitchTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: SeniorTheme.touchPaddingH),
      decoration: BoxDecoration(
        color:        SeniorTheme.surface,
        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
        border:       Border.all(color: SeniorTheme.divider),
      ),
      child: Row(
        children: [
          Icon(icon, size: 30, color: SeniorTheme.primary),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: SeniorTheme.fontMD, fontWeight: FontWeight.bold, color: SeniorTheme.textPrimary)),
                Text(subtitle, style: const TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond)),
              ],
            ),
          ),
          Switch(
            value:            value,
            onChanged:        onChanged,
            activeThumbColor: SeniorTheme.primary,
            trackOutlineColor: const WidgetStatePropertyAll(SeniorTheme.divider),
          ),
        ],
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
