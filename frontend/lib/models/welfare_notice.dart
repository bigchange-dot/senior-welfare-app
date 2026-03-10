import 'package:cloud_firestore/cloud_firestore.dart';

/// Firestore welfare_notices 컬렉션 데이터 모델
class WelfareNotice {
  final String   id;
  final String   title;
  final String   aiSummary;
  final String   source;
  final String   url;
  final DateTime timestamp;
  final bool     isNotified;

  const WelfareNotice({
    required this.id,
    required this.title,
    required this.aiSummary,
    required this.source,
    required this.url,
    required this.timestamp,
    required this.isNotified,
  });

  /// Firestore DocumentSnapshot → WelfareNotice
  factory WelfareNotice.fromFirestore(DocumentSnapshot doc) {
    final data = doc.data() as Map<String, dynamic>;
    return WelfareNotice(
      id:          doc.id,
      title:       data['title']       as String?  ?? '',
      aiSummary:   data['ai_summary']  as String?  ?? '',
      source:      data['source']      as String?  ?? '',
      url:         data['url']         as String?  ?? '',
      timestamp:   (data['timestamp']  as Timestamp?)?.toDate() ?? DateTime.now(),
      isNotified:  data['is_notified'] as bool?    ?? false,
    );
  }

  /// WelfareNotice → Map (필요 시 역직렬화)
  Map<String, dynamic> toMap() => {
    'title':       title,
    'ai_summary':  aiSummary,
    'source':      source,
    'url':         url,
    'timestamp':   Timestamp.fromDate(timestamp),
    'is_notified': isNotified,
  };

  @override
  String toString() => 'WelfareNotice(id: $id, source: $source, summary: $aiSummary)';
}
