import '../contracts/calendar_proposal_dto.dart';
import '../contracts/reply_draft_dto.dart';
import 'permissions.dart';

enum ApprovalKind { replyDraft, calendarSlot, blockedExternal }

class ApprovalItem {
  const ApprovalItem({
    required this.id,
    required this.kind,
    required this.title,
    required this.subtitle,
    required this.canApproveLocally,
    this.blockedReason,
  });

  final String id;
  final ApprovalKind kind;
  final String title;
  final String subtitle;
  final bool canApproveLocally;
  final String? blockedReason;
}

/// Build approval queue from local drafts/proposals.
/// Approving a draft locally does NOT send mail (transport UNSPECIFIED).
List<ApprovalItem> buildApprovalQueue({
  required List<ReplyDraftDto> drafts,
  required List<CalendarProposalDto> proposals,
}) {
  final items = <ApprovalItem>[];

  for (final d in drafts) {
    if (d.sent) continue;
    if (d.approved && d.bindingReviewApproved) {
      items.add(ApprovalItem(
        id: 'draft-send-${d.caseId}-${d.action}',
        kind: ApprovalKind.blockedExternal,
        title: 'Senden blockiert: ${d.subject}',
        subtitle: 'Freigabe lokal — Versand braucht genehmigten Sync-Transport.',
        canApproveLocally: false,
        blockedReason: 'send_email',
      ));
      continue;
    }
    items.add(ApprovalItem(
      id: 'draft-${d.caseId}-${d.action}',
      kind: ApprovalKind.replyDraft,
      title: d.subject.isEmpty ? d.action : d.subject,
      subtitle: 'Antwortentwurf · ${d.action} · auto_send=false',
      canApproveLocally: true,
    ));
  }

  for (final p in proposals) {
    if (p.status == 'selected' || p.status == 'rejected') continue;
    if (p.rankedSlots.isEmpty) continue;
    items.add(ApprovalItem(
      id: 'cal-${p.caseId}',
      kind: ApprovalKind.calendarSlot,
      title: 'Terminvorschlag wählen',
      subtitle: '${p.rankedSlots.length} Slots · ${p.timezone}',
      canApproveLocally: true,
    ));
  }

  // Explicit blocked external actions (never offer as approvable).
  for (final action in ['send_email', 'calendar_write', 'cloud_sync']) {
    assert(isExternalActionBlocked(action));
  }

  return items;
}
