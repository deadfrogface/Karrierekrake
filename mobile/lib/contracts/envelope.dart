/// Shared helpers for contract JSON decoding.
library;

String readString(Map<String, dynamic> json, String key, [String fallback = '']) {
  final v = json[key];
  if (v == null) return fallback;
  return v.toString();
}

int? readInt(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v == null) return null;
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString());
}

double? readDouble(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v == null) return null;
  if (v is double) return v;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString());
}

bool readBool(Map<String, dynamic> json, String key, [bool fallback = false]) {
  final v = json[key];
  if (v is bool) return v;
  return fallback;
}

List<String> readStringList(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is! List) return const [];
  return v.map((e) => e.toString()).toList();
}

Map<String, dynamic> readMap(Map<String, dynamic> json, String key) {
  final v = json[key];
  if (v is Map<String, dynamic>) return v;
  if (v is Map) return Map<String, dynamic>.from(v);
  return {};
}

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
      contractVersion: readString(json, 'contract_version'),
      schemaId: readString(json, 'schema_id'),
    );
  }

  Map<String, dynamic> toJson() => {
        'contract_version': contractVersion,
        'schema_id': schemaId,
      };

  bool get isV1 => contractVersion.startsWith('1.');
}

/// Known schema IDs from contracts/VERSION bundle 1.0.0.
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

const kContractBundleVersion = '1.0.0';
