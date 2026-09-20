import 'envelope.dart';

const kReplyActions = <String>{
  'CONFIRM_INTERVIEW',
  'PROPOSE_SLOTS',
  'RESCHEDULE',
  'DOCUMENT_REPLY',
  'THANK_YOU',
  'FOLLOWUP',
  'WITHDRAW',
  'DECLINE_OFFER',
  'GENERAL_REPLY',
};

class ReplyDraftDto {
  const ReplyDraftDto({
    required this.envelope,
    required this.caseId,
    required this.action,
    required this.subject,
    required this.body,
    this.toAddress = '',
    this.createdAt = '',
    this.approved = false,
    this.bindingReviewApproved = false,
    this.sent = false,
    this.sendError = '',
    this.draftOnly = true,
    this.autoSend = false,
    this.requiresExplicitReview = false,
    this.blockingReasons = const [],
  });

  final ContractEnvelope envelope;
  final String caseId;
  final String action;
  final String subject;
  final String body;
  final String toAddress;
  final String createdAt;
  final bool approved;
  final bool bindingReviewApproved;
  final bool sent;
  final String sendError;
  final bool draftOnly;
  final bool autoSend;
  final bool requiresExplicitReview;
  final List<String> blockingReasons;

  static const schemaId = 'karrierekrake.reply_draft';

  /// Contract invariant: auto_send must always be false on mobile.
  bool get respectsAutoSendBan => autoSend == false;

  factory ReplyDraftDto.fromJson(Map<String, dynamic> json) {
    return ReplyDraftDto(
      envelope: ContractEnvelope.fromJson(json),
      caseId: readString(json, 'case_id'),
      action: readString(json, 'action'),
      subject: readString(json, 'subject'),
      body: readString(json, 'body'),
      toAddress: readString(json, 'to_address'),
      createdAt: readString(json, 'created_at'),
      approved: readBool(json, 'approved'),
      bindingReviewApproved: readBool(json, 'binding_review_approved'),
      sent: readBool(json, 'sent'),
      sendError: readString(json, 'send_error'),
      draftOnly: readBool(json, 'draft_only', true),
      autoSend: readBool(json, 'auto_send'),
      requiresExplicitReview: readBool(json, 'requires_explicit_review'),
      blockingReasons: readStringList(json, 'blocking_reasons'),
    );
  }

  Map<String, dynamic> toJson() => {
        ...envelope.toJson(),
        'case_id': caseId,
        'action': action,
        'subject': subject,
        'body': body,
        'to_address': toAddress,
        'created_at': createdAt,
        'approved': approved,
        'binding_review_approved': bindingReviewApproved,
        'sent': sent,
        'send_error': sendError,
        'draft_only': draftOnly,
        'auto_send': false, // hard invariant
        'requires_explicit_review': requiresExplicitReview,
        'blocking_reasons': blockingReasons,
      };

  ReplyDraftDto markApprovedLocally() {
    return ReplyDraftDto(
      envelope: envelope,
      caseId: caseId,
      action: action,
      subject: subject,
      body: body,
      toAddress: toAddress,
      createdAt: createdAt,
      approved: true,
      bindingReviewApproved: true,
      sent: false,
      sendError: sendError,
      draftOnly: true,
      autoSend: false,
      requiresExplicitReview: requiresExplicitReview,
      blockingReasons: blockingReasons,
    );
  }
}
