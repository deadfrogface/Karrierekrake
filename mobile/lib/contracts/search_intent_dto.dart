import 'envelope.dart';

class SearchIntentDto {
  const SearchIntentDto({
    required this.envelope,
    required this.schemaVersion,
    this.targetRoles = const [],
    this.requiredRoles = const [],
    this.excludedRoles = const [],
    this.mandatorySkills = const [],
    this.preferredSkills = const [],
    this.excludedSkills = const [],
    this.requiredKeywords = const [],
    this.excludedKeywords = const [],
    this.preferredIndustries = const [],
    this.excludedIndustries = const [],
    this.strictness,
    this.remoteMode,
    this.employmentTypes = const [],
    this.workingTime = const [],
    this.salaryMin,
    this.countries = const [],
    this.radiusKm,
    this.needsUserReview = const [],
  });

  final ContractEnvelope envelope;
  final int schemaVersion;
  final List<String> targetRoles;
  final List<String> requiredRoles;
  final List<String> excludedRoles;
  final List<String> mandatorySkills;
  final List<String> preferredSkills;
  final List<String> excludedSkills;
  final List<String> requiredKeywords;
  final List<String> excludedKeywords;
  final List<String> preferredIndustries;
  final List<String> excludedIndustries;
  final String? strictness;
  final String? remoteMode;
  final List<String> employmentTypes;
  final List<String> workingTime;
  final double? salaryMin;
  final List<String> countries;
  final double? radiusKm;
  final List<String> needsUserReview;

  static const schemaId = 'karrierekrake.search_intent';
  static const allowedStrictness = {'strict', 'balanced', 'explore'};

  factory SearchIntentDto.fromJson(Map<String, dynamic> json) {
    return SearchIntentDto(
      envelope: ContractEnvelope.fromJson(json),
      schemaVersion: readInt(json, 'schema_version') ?? 1,
      targetRoles: readStringList(json, 'target_roles'),
      requiredRoles: readStringList(json, 'required_roles'),
      excludedRoles: readStringList(json, 'excluded_roles'),
      mandatorySkills: readStringList(json, 'mandatory_skills'),
      preferredSkills: readStringList(json, 'preferred_skills'),
      excludedSkills: readStringList(json, 'excluded_skills'),
      requiredKeywords: readStringList(json, 'required_keywords'),
      excludedKeywords: readStringList(json, 'excluded_keywords'),
      preferredIndustries: readStringList(json, 'preferred_industries'),
      excludedIndustries: readStringList(json, 'excluded_industries'),
      strictness: json['strictness'] as String?,
      remoteMode: json['remote_mode'] as String?,
      employmentTypes: readStringList(json, 'employment_types'),
      workingTime: readStringList(json, 'working_time'),
      salaryMin: readDouble(json, 'salary_min'),
      countries: readStringList(json, 'countries'),
      radiusKm: readDouble(json, 'radius_km'),
      needsUserReview: readStringList(json, 'needs_user_review'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'schema_version': schemaVersion,
        'target_roles': targetRoles,
        'required_roles': requiredRoles,
        'excluded_roles': excludedRoles,
        'mandatory_skills': mandatorySkills,
        'preferred_skills': preferredSkills,
        'excluded_skills': excludedSkills,
        'required_keywords': requiredKeywords,
        'excluded_keywords': excludedKeywords,
        'preferred_industries': preferredIndustries,
        'excluded_industries': excludedIndustries,
        'strictness': strictness,
        'remote_mode': remoteMode,
        'employment_types': employmentTypes,
        'working_time': workingTime,
        'salary_min': salaryMin,
        'countries': countries,
        'radius_km': radiusKm,
        'needs_user_review': needsUserReview,
      };

  SearchIntentDto copyWith({
    List<String>? targetRoles,
    List<String>? mandatorySkills,
    String? strictness,
    List<String>? countries,
    double? radiusKm,
    bool clearStrictness = false,
  }) {
    return SearchIntentDto(
      envelope: envelope,
      schemaVersion: schemaVersion,
      targetRoles: targetRoles ?? this.targetRoles,
      requiredRoles: requiredRoles,
      excludedRoles: excludedRoles,
      mandatorySkills: mandatorySkills ?? this.mandatorySkills,
      preferredSkills: preferredSkills,
      excludedSkills: excludedSkills,
      requiredKeywords: requiredKeywords,
      excludedKeywords: excludedKeywords,
      preferredIndustries: preferredIndustries,
      excludedIndustries: excludedIndustries,
      strictness: clearStrictness ? null : (strictness ?? this.strictness),
      remoteMode: remoteMode,
      employmentTypes: employmentTypes,
      workingTime: workingTime,
      salaryMin: salaryMin,
      countries: countries ?? this.countries,
      radiusKm: radiusKm ?? this.radiusKm,
      needsUserReview: needsUserReview,
    );
  }

  /// Never silently upgrade to STRICT — caller must set explicitly.
  bool wouldSilentStrictExpand(String? next) {
    if (strictness == 'strict') return false;
    return next == 'strict';
  }
}
