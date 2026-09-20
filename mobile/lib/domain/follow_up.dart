import '../contracts/application_case_dto.dart';
import '../contracts/lifecycle_event_dto.dart';
import '../contracts/reply_draft_dto.dart';

/// Local follow-up hint — never auto-sends.
class FollowUpHint {
  const FollowUpHint({
    required this.caseId,
    required this.severity,
    required this.message,
    this.suggestedAction = 'FOLLOWUP',
  });

  final String caseId;
  final String severity; // info | warn | urgent
  final String message;
  final String suggestedAction;
}

DateTime? tryParseIso(String raw) {
  if (raw.trim().isEmpty) return null;
  return DateTime.tryParse(raw);
}

/// Derive follow-up hints from local contract snapshots only.
List<FollowUpHint> deriveFollowUpHints({
  required List<ApplicationCaseDto> cases,
  required List<LifecycleEventDto> events,
  required List<ReplyDraftDto> drafts,
  DateTime? now,
}) {
  final clock = now ?? DateTime.now().toUtc();
  final hints = <FollowUpHint>[];
  final draftsByCase = <String, List<ReplyDraftDto>>{};
  for (final d in drafts) {
    draftsByCase.putIfAbsent(d.caseId, () => []).add(d);
  }
  final eventsByCase = <String, List<LifecycleEventDto>>{};
  for (final e in events) {
    eventsByCase.putIfAbsent(e.caseId, () => []).add(e);
  }

  for (final c in cases) {
    if (c.status == 'rejected' ||
        c.status == 'withdrawn' ||
        c.status == 'closed' ||
        c.status == 'offer') {
      continue;
    }

    final caseEvents = eventsByCase[c.id] ?? const [];
    final hasFollowUpSent =
        caseEvents.any((e) => e.eventType == 'FOLLOWUP_SENT');
    final hasGhosted = caseEvents.any((e) => e.eventType == 'GHOSTED') ||
        c.status == 'ghosted';

    final applied = tryParseIso(c.appliedAt) ?? tryParseIso(c.createdAt);
    if (applied != null) {
      final days = clock.difference(applied.toUtc()).inDays;
      if (days >= 14 &&
          !hasFollowUpSent &&
          (c.status == 'applied' || c.status == 'confirmation')) {
        hints.add(FollowUpHint(
          caseId: c.id,
          severity: days >= 21 ? 'urgent' : 'warn',
          message:
              'Keine Reaktion seit $days Tagen — Follow-up Entwurf prüfen.',
        ));
      }
    }

    if (hasGhosted) {
      hints.add(FollowUpHint(
        caseId: c.id,
        severity: 'warn',
        message: 'Fall als ghosted markiert — manuellen Follow-up erwägen.',
      ));
    }

    final pendingDrafts = (draftsByCase[c.id] ?? const [])
        .where((d) => !d.sent && d.action == 'FOLLOWUP');
    for (final d in pendingDrafts) {
      if (!d.approved) {
        hints.add(FollowUpHint(
          caseId: c.id,
          severity: 'info',
          message: 'Follow-up Entwurf wartet auf Freigabe: ${d.subject}',
        ));
      }
    }

    if (c.status == 'interview') {
      final scheduled = caseEvents
          .any((e) => e.eventType == 'INTERVIEW_SCHEDULED');
      if (!scheduled) {
        hints.add(FollowUpHint(
          caseId: c.id,
          severity: 'info',
          message: 'Interview-Status ohne Termin — Kalender-Vorschlag prüfen.',
          suggestedAction: 'PROPOSE_SLOTS',
        ));
      }
    }
  }

  return hints;
}
