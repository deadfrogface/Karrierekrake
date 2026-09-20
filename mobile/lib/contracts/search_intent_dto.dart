/// Dart mirrors of shared JSON contracts (PR37).
///
/// Source of truth: `contracts/schemas/v1/*.schema.json`
/// These are plain data types — not generated from PySide models.
library;

/// Wire envelope fields present on every shared contract document.
class ContractEnvelope {
  const ContractEnvelope({
    required this.contractVersion,
    required this.schemaId,
  });

  final String contractVersion;
  final String schemaId;

  factory ContractEnvelope.fromJson(Map<String, dynamic> json) {
    return ContractEnvelope(
      contractVersion: json['contract_version'] as String? ?? '',
      schemaId: json['schema_id'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'contract_version': contractVersion,
        'schema_id': schemaId,
      };
}

/// Minimal SearchIntent DTO — expand field-by-field against the schema.
class SearchIntentDto {
  const SearchIntentDto({
    required this.envelope,
    required this.schemaVersion,
    this.targetRoles = const [],
    this.mandatorySkills = const [],
    this.strictness,
  });

  final ContractEnvelope envelope;
  final int schemaVersion;
  final List<String> targetRoles;
  final List<String> mandatorySkills;
  final String? strictness;

  static const schemaId = 'karrierekrake.search_intent';

  factory SearchIntentDto.fromJson(Map<String, dynamic> json) {
    return SearchIntentDto(
      envelope: ContractEnvelope.fromJson(json),
      schemaVersion: json['schema_version'] as int? ?? 1,
      targetRoles: List<String>.from(json['target_roles'] as List? ?? const []),
      mandatorySkills:
          List<String>.from(json['mandatory_skills'] as List? ?? const []),
      strictness: json['strictness'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'schema_version': schemaVersion,
        'target_roles': targetRoles,
        'mandatory_skills': mandatorySkills,
        'strictness': strictness,
      };
}

/// Schema IDs expected by the companion — keep in sync with contracts/VERSION bundle.
const kKnownSchemaIds = <String>{
  'karrierekrake.profile',
  'karrierekrake.search_intent',
  'karrierekrake.job',
  'karrierekrake.application_case',
  'karrierekrake.lifecycle_event',
  'karrierekrake.calendar_proposal',
  'karrierekrake.reply_draft',
  'karrierekrake.guenther_result',
};
