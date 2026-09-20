import 'envelope.dart';

class GuentherResultDto {
  const GuentherResultDto({
    required this.envelope,
    required this.ok,
    required this.capability,
    this.suggestion = const {},
    this.fallbackReason = '',
    this.providerStatus = '',
    this.modelId = '',
    this.validated = false,
    this.safetyNotes = const [],
  });

  final ContractEnvelope envelope;
  final bool ok;
  final String capability;
  final Map<String, dynamic> suggestion;
  final String fallbackReason;
  final String providerStatus;
  final String modelId;
  final bool validated;
  final List<String> safetyNotes;

  static const schemaId = 'karrierekrake.guenther_result';

  /// Fail-closed: only show suggestion when ok && validated.
  bool get isConsumable => ok && validated;

  factory GuentherResultDto.fromJson(Map<String, dynamic> json) {
    return GuentherResultDto(
      envelope: ContractEnvelope.fromJson(json),
      ok: readBool(json, 'ok'),
      capability: readString(json, 'capability'),
      suggestion: readMap(json, 'suggestion'),
      fallbackReason: readString(json, 'fallback_reason'),
      providerStatus: readString(json, 'provider_status'),
      modelId: readString(json, 'model_id'),
      validated: readBool(json, 'validated'),
      safetyNotes: readStringList(json, 'safety_notes'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'ok': ok,
        'capability': capability,
        'suggestion': suggestion,
        'fallback_reason': fallbackReason,
        'provider_status': providerStatus,
        'model_id': modelId,
        'validated': validated,
        'safety_notes': safetyNotes,
      };
}
