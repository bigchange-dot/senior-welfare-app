import 'package:flutter/material.dart';

import '../regions.dart';
import '../services/region_prefs.dart';
import '../theme.dart';

/// 내 지역 고르기 (v1.5, 2026-11-18)
///
/// 예전 홈 칩(13개 가로 스크롤)과 설정의 긴 체크 목록을 대신한다.
/// 1단계 시·도(큰 버튼 2개) → 2단계 시·군·구(큰 타일 격자). 고르는 즉시 저장되고 알림 구독도 바뀐다.
/// 드롭다운 메뉴는 글자가 작고 2단 메뉴가 헷갈려 쓰지 않았다.
class RegionPickerScreen extends StatefulWidget {
  const RegionPickerScreen({super.key});

  @override
  State<RegionPickerScreen> createState() => _RegionPickerScreenState();
}

class _RegionPickerScreenState extends State<RegionPickerScreen> {
  late List<String> _picked;
  late Province _province;

  @override
  void initState() {
    super.initState();
    _picked = List.of(RegionPrefs.selected.value);
    final first = _picked.isEmpty ? null : regionById(_picked.first);
    _province = provinces.firstWhere((p) => p.id == first?.provinceId, orElse: () => seoul);
  }

  void _showMessage(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: Text(text, style: const TextStyle(fontSize: SeniorTheme.fontSM)),
        duration: const Duration(seconds: 3),
      ));
  }

  void _toggle(Region region) {
    if (!region.available) {
      _showMessage('${region.name} 공고는 아직 준비 중이에요.');
      return;
    }
    final next = List.of(_picked);
    if (next.contains(region.id)) {
      next.remove(region.id);
    } else if (next.length >= RegionPrefs.maxRegions) {
      _showMessage('최대 ${RegionPrefs.maxRegions}곳까지 고를 수 있어요. 위에서 고른 지역의 ✕를 눌러 빼 주세요.');
      return;
    } else {
      next.add(region.id);
    }
    setState(() => _picked = next);
    RegionPrefs.setRegions(next);
  }

  void _remove(String id) {
    final next = List.of(_picked)..remove(id);
    setState(() => _picked = next);
    RegionPrefs.setRegions(next);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SeniorTheme.background,
      appBar: AppBar(title: const Text('내 지역 고르기')),
      // 안내·고른 지역·시도 버튼·격자를 한 스크롤로 — 작은 폰에서 글자를 키우면 위쪽만으로 화면이 차서
      // 격자가 들어갈 자리가 없었음 (위젯 테스트로 확인)
      body: LayoutBuilder(
        builder: (context, constraints) => CustomScrollView(
          slivers: [
            const SliverToBoxAdapter(
              child: Padding(
                padding: EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Text(
                  '공고를 모아 보고 알림을 받을 지역을 골라 주세요. 최대 ${RegionPrefs.maxRegions}곳까지 고를 수 있어요.',
                  style: TextStyle(fontSize: SeniorTheme.fontMD, color: SeniorTheme.textSecond, height: 1.4),
                ),
              ),
            ),
            SliverToBoxAdapter(child: _PickedRow(picked: _picked, onRemove: _remove)),
            SliverToBoxAdapter(
              child: _ProvinceTabs(
                selected: _province,
                onSelected: (p) => setState(() => _province = p),
              ),
            ),
            _RegionGrid(
              width:   constraints.maxWidth,
              regions: _province.regions,
              picked:  _picked,
              onTap:   _toggle,
            ),
          ],
        ),
      ),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: ElevatedButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(_picked.isEmpty ? '완료' : '완료 (${_picked.length}곳)'),
          ),
        ),
      ),
    );
  }
}

/// 고른 지역 — 누르면 뺀다
class _PickedRow extends StatelessWidget {
  final List<String> picked;
  final ValueChanged<String> onRemove;

  const _PickedRow({required this.picked, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
      child: picked.isEmpty
          ? const Text(
              '아직 고른 지역이 없어요. 고르지 않으면 서울·경기의 모든 공고를 보고 알림도 모두 받아요.',
              style: TextStyle(fontSize: SeniorTheme.fontSM, color: SeniorTheme.textSecond, height: 1.4),
            )
          : Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final id in picked)
                  Semantics(
                    button: true,
                    label: '${regionById(id)?.name ?? id} 빼기',
                    excludeSemantics: true,
                    child: Material(
                      color: SeniorTheme.primary,
                      borderRadius: BorderRadius.circular(24),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(24),
                        onTap: () => onRemove(id),
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(minHeight: 48),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  regionById(id)?.name ?? id,
                                  style: const TextStyle(
                                    fontSize: SeniorTheme.fontSM,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                const Icon(Icons.close, color: Colors.white, size: 22),
                              ],
                            ),
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

/// 1단계: 시·도 (큰 버튼 2개)
class _ProvinceTabs extends StatelessWidget {
  final Province selected;
  final ValueChanged<Province> onSelected;

  const _ProvinceTabs({required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Row(
        children: [
          for (final p in provinces) ...[
            if (p != provinces.first) const SizedBox(width: 10),
            Expanded(
              child: Semantics(
                selected: p == selected,
                button: true,
                child: Material(
                  color: p == selected ? SeniorTheme.primary : SeniorTheme.surface,
                  borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
                    onTap: () => onSelected(p),
                    child: Container(
                      constraints: const BoxConstraints(minHeight: 60),
                      alignment: Alignment.center,
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(SeniorTheme.cardRadius),
                        border: Border.all(
                          color: p == selected ? SeniorTheme.primary : SeniorTheme.divider,
                          width: 2,
                        ),
                      ),
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          p.name,
                          style: TextStyle(
                            fontSize: SeniorTheme.fontLG,
                            fontWeight: FontWeight.bold,
                            color: p == selected ? Colors.white : SeniorTheme.textPrimary,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// 2단계: 시·군·구 격자. 글자 크기를 키우면 열 수를 줄인다 (어르신 폰은 글자 크기 확대가 흔함)
class _RegionGrid extends StatelessWidget {
  final double width;
  final List<Region> regions;
  final List<String> picked;
  final ValueChanged<Region> onTap;

  const _RegionGrid({required this.width, required this.regions, required this.picked, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.textScalerOf(context).scale(1.0).clamp(1.0, 2.5);
    final columns = ((width - 32) / (104 * scale)).floor().clamp(2, 4);
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      sliver: SliverGrid(
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount:   columns,
          mainAxisSpacing:  10,
          crossAxisSpacing: 10,
          mainAxisExtent:   72 * scale,
        ),
        delegate: SliverChildBuilderDelegate(
          (context, i) => _RegionTile(
            region:   regions[i],
            selected: picked.contains(regions[i].id),
            onTap:    () => onTap(regions[i]),
          ),
          childCount: regions.length,
        ),
      ),
    );
  }
}

class _RegionTile extends StatelessWidget {
  final Region region;
  final bool selected;
  final VoidCallback onTap;

  const _RegionTile({required this.region, required this.selected, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final available = region.available;
    final bg = selected
        ? SeniorTheme.primary
        : available ? SeniorTheme.surface : const Color(0xFFEEEEEE);
    final fg = selected
        ? Colors.white
        : available ? SeniorTheme.textPrimary : const Color(0xFF8A8A8A);
    return Semantics(
      button: true,
      selected: selected,
      label: available ? region.name : '${region.name}, 준비 중',
      excludeSemantics: true,
      child: Material(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onTap,
          child: Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: selected ? SeniorTheme.primary : SeniorTheme.divider,
                width: selected ? 2 : 1.5,
              ),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                FittedBox(
                  fit: BoxFit.scaleDown,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (selected) ...[
                        const Icon(Icons.check, color: Colors.white, size: 22),
                        const SizedBox(width: 4),
                      ],
                      Text(
                        region.name,
                        maxLines: 1,
                        style: TextStyle(
                          fontSize: SeniorTheme.fontMD,
                          fontWeight: FontWeight.bold,
                          color: fg,
                        ),
                      ),
                    ],
                  ),
                ),
                if (!available)
                  FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(
                      '준비 중',
                      style: TextStyle(fontSize: SeniorTheme.fontCaption, color: fg),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
