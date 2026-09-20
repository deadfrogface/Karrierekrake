import 'envelope.dart';

class JobDto {
  const JobDto({
    required this.envelope,
    required this.id,
    this.source = '',
    this.title = '',
    this.company = '',
    this.city = '',
    this.countryCode = '',
    this.remoteType = '',
    this.employmentType = '',
    this.distanceKm,
    this.matchScore = 0,
    this.matchReasons = const [],
    this.rejectionReasons = const [],
    this.status = '',
    this.salaryText = '',
    this.url = '',
  });

  final ContractEnvelope envelope;
  final String id;
  final String source;
  final String title;
  final String company;
  final String city;
  final String countryCode;
  final String remoteType;
  final String employmentType;
  final double? distanceKm;
  final int matchScore;
  final List<String> matchReasons;
  final List<String> rejectionReasons;
  final String status;
  final String salaryText;
  final String url;

  static const schemaId = 'karrierekrake.job';

  factory JobDto.fromJson(Map<String, dynamic> json) {
    return JobDto(
      envelope: ContractEnvelope.fromJson(json),
      id: readString(json, 'id'),
      source: readString(json, 'source'),
      title: readString(json, 'title'),
      company: readString(json, 'company'),
      city: readString(json, 'city'),
      countryCode: readString(json, 'country_code'),
      remoteType: readString(json, 'remote_type'),
      employmentType: readString(json, 'employment_type'),
      distanceKm: readDouble(json, 'distance_km'),
      matchScore: readInt(json, 'match_score') ?? 0,
      matchReasons: readStringList(json, 'match_reasons'),
      rejectionReasons: readStringList(json, 'rejection_reasons'),
      status: readString(json, 'status'),
      salaryText: readString(json, 'salary_text'),
      url: readString(json, 'url'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'id': id,
        'source': source,
        'title': title,
        'company': company,
        'city': city,
        'country_code': countryCode,
        'remote_type': remoteType,
        'employment_type': employmentType,
        'distance_km': distanceKm,
        'match_score': matchScore,
        'match_reasons': matchReasons,
        'rejection_reasons': rejectionReasons,
        'status': status,
        'salary_text': salaryText,
        'url': url,
      };
}
