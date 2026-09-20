import 'envelope.dart';

class RankedSlotDto {
  const RankedSlotDto({
    required this.start,
    required this.end,
    this.score,
    this.rank,
    this.explanations = const [],
    this.modality = '',
    this.timezone = '',
  });

  final String start;
  final String end;
  final double? score;
  final int? rank;
  final List<String> explanations;
  final String modality;
  final String timezone;

  factory RankedSlotDto.fromJson(Map<String, dynamic> json) {
    return RankedSlotDto(
      start: readString(json, 'start'),
      end: readString(json, 'end'),
      score: readDouble(json, 'score'),
      rank: readInt(json, 'rank'),
      explanations: readStringList(json, 'explanations'),
      modality: readString(json, 'modality'),
      timezone: readString(json, 'timezone'),
    );
  }

  Map<String, dynamic> toJson() => {
        'start': start,
        'end': end,
        'score': score,
        'rank': rank,
        'explanations': explanations,
        'modality': modality,
        'timezone': timezone,
      };
}

class CalendarProposalDto {
  const CalendarProposalDto({
    required this.envelope,
    required this.caseId,
    required this.timezone,
    required this.rankingVersion,
    required this.prefsSchemaVersion,
    this.proposalText = '',
    this.modality = '',
    this.rankedSlots = const [],
    this.selectedSlotIndex,
    this.status = 'proposed',
    this.createdAt = '',
  });

  final ContractEnvelope envelope;
  final String caseId;
  final String timezone;
  final int rankingVersion;
  final int prefsSchemaVersion;
  final String proposalText;
  final String modality;
  final List<RankedSlotDto> rankedSlots;
  final int? selectedSlotIndex;
  final String status;
  final String createdAt;

  static const schemaId = 'karrierekrake.calendar_proposal';

  factory CalendarProposalDto.fromJson(Map<String, dynamic> json) {
    final slotsRaw = json['ranked_slots'];
    final slots = <RankedSlotDto>[];
    if (slotsRaw is List) {
      for (final item in slotsRaw) {
        if (item is Map<String, dynamic>) {
          slots.add(RankedSlotDto.fromJson(item));
        } else if (item is Map) {
          slots.add(RankedSlotDto.fromJson(Map<String, dynamic>.from(item)));
        }
      }
    }
    return CalendarProposalDto(
      envelope: ContractEnvelope.fromJson(json),
      caseId: readString(json, 'case_id'),
      timezone: readString(json, 'timezone'),
      rankingVersion: readInt(json, 'ranking_version') ?? 1,
      prefsSchemaVersion: readInt(json, 'prefs_schema_version') ?? 1,
      proposalText: readString(json, 'proposal_text'),
      modality: readString(json, 'modality'),
      rankedSlots: slots,
      selectedSlotIndex: readInt(json, 'selected_slot_index'),
      status: readString(json, 'status', 'proposed'),
      createdAt: readString(json, 'created_at'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'case_id': caseId,
        'timezone': timezone,
        'ranking_version': rankingVersion,
        'prefs_schema_version': prefsSchemaVersion,
        'proposal_text': proposalText,
        'modality': modality,
        'ranked_slots': rankedSlots.map((s) => s.toJson()).toList(),
        'selected_slot_index': selectedSlotIndex,
        'status': status,
        'created_at': createdAt,
      };

  CalendarProposalDto selectSlot(int index) {
    if (index < 0 || index >= rankedSlots.length) {
      throw ArgumentError('slot index out of range: $index');
    }
    return CalendarProposalDto(
      envelope: envelope,
      caseId: caseId,
      timezone: timezone,
      rankingVersion: rankingVersion,
      prefsSchemaVersion: prefsSchemaVersion,
      proposalText: proposalText,
      modality: modality,
      rankedSlots: rankedSlots,
      selectedSlotIndex: index,
      status: 'selected',
      createdAt: createdAt,
    );
  }
}
