import 'envelope.dart';

const kLifecycleEventTypes = <String>{
  'APPLICATION_CREATED',
  'APPLICATION_SENT',
  'APPLICATION_RECEIVED',
  'UNDER_REVIEW',
  'DOCUMENT_REQUESTED',
  'ASSESSMENT_RECEIVED',
  'INTERVIEW_REQUESTED',
  'INTERVIEW_SCHEDULED',
  'INTERVIEW_RESCHEDULED',
  'INTERVIEW_CANCELLED',
  'INTERVIEW_COMPLETED',
  'OFFER_RECEIVED',
  'REJECTION_RECEIVED',
  'FOLLOWUP_SENT',
  'WITHDRAWN',
  'GHOSTED',
  'ARCHIVED',
  'MANUAL_OVERRIDE',
};

class LifecycleEventDto {
  const LifecycleEventDto({
    required this.envelope,
    required this.eventType,
    this.id = '',
    this.caseId = '',
    this.occurredAt = '',
    this.recordedAt = '',
    this.idempotencyKey = '',
    this.payload = const {},
    this.source = '',
    this.confidence,
  });

  final ContractEnvelope envelope;
  final String eventType;
  final String id;
  final String caseId;
  final String occurredAt;
  final String recordedAt;
  final String idempotencyKey;
  final Map<String, dynamic> payload;
  final String source;
  final double? confidence;

  static const schemaId = 'karrierekrake.lifecycle_event';

  bool get isKnownType => kLifecycleEventTypes.contains(eventType);

  factory LifecycleEventDto.fromJson(Map<String, dynamic> json) {
    return LifecycleEventDto(
      envelope: ContractEnvelope.fromJson(json),
      eventType: readString(json, 'event_type'),
      id: readString(json, 'id'),
      caseId: readString(json, 'case_id'),
      occurredAt: readString(json, 'occurred_at'),
      recordedAt: readString(json, 'recorded_at'),
      idempotencyKey: readString(json, 'idempotency_key'),
      payload: readMap(json, 'payload'),
      source: readString(json, 'source'),
      confidence: readDouble(json, 'confidence'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'event_type': eventType,
        'id': id,
        'case_id': caseId,
        'occurred_at': occurredAt,
        'recorded_at': recordedAt,
        'idempotency_key': idempotencyKey,
        'payload': payload,
        'source': source,
        'confidence': confidence,
      };
}
