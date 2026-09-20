import 'envelope.dart';

const kCaseStatuses = <String>{
  'to_apply',
  'applied',
  'confirmation',
  'assessment',
  'interview',
  'offer',
  'rejected',
  'withdrawn',
  'ghosted',
  'closed',
};

class ApplicationCaseDto {
  const ApplicationCaseDto({
    required this.envelope,
    required this.id,
    required this.status,
    this.jobId = '',
    this.company = '',
    this.position = '',
    this.contactEmail = '',
    this.appliedAt = '',
    this.updatedAt = '',
    this.createdAt = '',
    this.notes = '',
  });

  final ContractEnvelope envelope;
  final String id;
  final String status;
  final String jobId;
  final String company;
  final String position;
  final String contactEmail;
  final String appliedAt;
  final String updatedAt;
  final String createdAt;
  final String notes;

  static const schemaId = 'karrierekrake.application_case';

  bool get hasValidStatus => kCaseStatuses.contains(status);

  factory ApplicationCaseDto.fromJson(Map<String, dynamic> json) {
    return ApplicationCaseDto(
      envelope: ContractEnvelope.fromJson(json),
      id: readString(json, 'id'),
      status: readString(json, 'status'),
      jobId: readString(json, 'job_id'),
      company: readString(json, 'company'),
      position: readString(json, 'position'),
      contactEmail: readString(json, 'contact_email'),
      appliedAt: readString(json, 'applied_at'),
      updatedAt: readString(json, 'updated_at'),
      createdAt: readString(json, 'created_at'),
      notes: readString(json, 'notes'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'id': id,
        'status': status,
        'job_id': jobId,
        'company': company,
        'position': position,
        'contact_email': contactEmail,
        'applied_at': appliedAt,
        'updated_at': updatedAt,
        'created_at': createdAt,
        'notes': notes,
      };

  ApplicationCaseDto copyWithNotes(String notes) {
    return ApplicationCaseDto(
      envelope: envelope,
      id: id,
      status: status,
      jobId: jobId,
      company: company,
      position: position,
      contactEmail: contactEmail,
      appliedAt: appliedAt,
      updatedAt: updatedAt,
      createdAt: createdAt,
      notes: notes,
    );
  }
}
