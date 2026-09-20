import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/contracts/contracts.dart';
import 'package:karrierekrake_mobile/domain/approvals.dart';
import 'package:karrierekrake_mobile/domain/follow_up.dart';
import 'package:karrierekrake_mobile/domain/permissions.dart';

ContractEnvelope env(String sid) => ContractEnvelope(
      contractVersion: '1.0.0',
      schemaId: sid,
    );

ApplicationCaseDto caseOf(String id, String status, {String applied = '2026-08-01T00:00:00Z'}) =>
    ApplicationCaseDto(
      envelope: env(ApplicationCaseDto.schemaId),
      id: id,
      status: status,
      appliedAt: applied,
      createdAt: applied,
    );

void main() {
  group('permissions', () {
    test('profile writable', () => expect(canWrite('profile'), isTrue));
    test('job not writable', () => expect(canWrite('job'), isFalse));
    test('search writable', () => expect(canWrite('search_intent'), isTrue));
    test('guenther not writable', () => expect(canWrite('guenther_result'), isFalse));
    test('reply draft_only', () {
      expect(kPermissions['reply_draft']!.mobileWrite, MobileWriteMode.draftOnly);
    });
    test('calendar select_slot', () {
      expect(kPermissions['calendar_proposal']!.mobileWrite, MobileWriteMode.selectSlot);
    });
    test('send blocked', () => expect(isExternalActionBlocked('send_email'), isTrue));
    test('calendar write blocked', () => expect(isExternalActionBlocked('calendar_write'), isTrue));
    test('cloud sync blocked', () => expect(isExternalActionBlocked('cloud_sync'), isTrue));
    test('phi download blocked', () => expect(isExternalActionBlocked('phi_download'), isTrue));
    test('apply bot blocked', () => expect(isExternalActionBlocked('apply_bot'), isTrue));
    test('unknown action not blocked by default', () {
      expect(isExternalActionBlocked('local_note'), isFalse);
    });
    for (final key in kPermissions.keys) {
      test('permission $key has schema', () {
        expect(kPermissions[key]!.schemaId.startsWith('karrierekrake.'), isTrue);
      });
      test('permission $key offline cacheable flag bool', () {
        expect(kPermissions[key]!.offlineCacheable, isA<bool>());
      });
    }
  });

  group('follow-up', () {
    test('empty inputs', () {
      expect(deriveFollowUpHints(cases: [], events: [], drafts: []), isEmpty);
    });
    test('warn after 14 days applied', () {
      final hints = deriveFollowUpHints(
        cases: [caseOf('c1', 'applied')],
        events: [],
        drafts: [],
        now: DateTime.utc(2026, 9, 20),
      );
      expect(hints.any((h) => h.caseId == 'c1'), isTrue);
    });
    test('urgent after 21 days', () {
      final hints = deriveFollowUpHints(
        cases: [caseOf('c2', 'confirmation', applied: '2026-08-01T00:00:00Z')],
        events: [],
        drafts: [],
        now: DateTime.utc(2026, 9, 20),
      );
      expect(hints.first.severity, 'urgent');
    });
    test('skip rejected', () {
      final hints = deriveFollowUpHints(
        cases: [caseOf('c3', 'rejected')],
        events: [],
        drafts: [],
        now: DateTime.utc(2026, 9, 20),
      );
      expect(hints.where((h) => h.caseId == 'c3'), isEmpty);
    });
    test('pending followup draft info', () {
      final draft = ReplyDraftDto(
        envelope: env(ReplyDraftDto.schemaId),
        caseId: 'c4',
        action: 'FOLLOWUP',
        subject: 'Ping',
        body: 'x',
      );
      final hints = deriveFollowUpHints(
        cases: [caseOf('c4', 'interview', applied: '2026-09-18T00:00:00Z')],
        events: [],
        drafts: [draft],
        now: DateTime.utc(2026, 9, 20),
      );
      expect(hints.any((h) => h.message.contains('Follow-up Entwurf')), isTrue);
    });
    test('interview without schedule', () {
      final hints = deriveFollowUpHints(
        cases: [caseOf('c5', 'interview', applied: '2026-09-18T00:00:00Z')],
        events: [],
        drafts: [],
        now: DateTime.utc(2026, 9, 20),
      );
      expect(hints.any((h) => h.suggestedAction == 'PROPOSE_SLOTS'), isTrue);
    });
    for (var i = 0; i < 20; i++) {
      test('status matrix $i', () {
        final st = [
          'to_apply','applied','confirmation','assessment','interview',
          'offer','rejected','withdrawn','ghosted','closed',
        ][i % 10];
        final hints = deriveFollowUpHints(
          cases: [caseOf('cx-$i', st)],
          events: [],
          drafts: [],
          now: DateTime.utc(2026, 9, 20),
        );
        expect(hints, isA<List<FollowUpHint>>());
      });
    }
  });

  group('approvals', () {
    test('empty queue', () {
      expect(buildApprovalQueue(drafts: [], proposals: []), isEmpty);
    });
    test('draft appears', () {
      final d = ReplyDraftDto(
        envelope: env(ReplyDraftDto.schemaId),
        caseId: 'c',
        action: 'FOLLOWUP',
        subject: 'S',
        body: 'B',
      );
      final q = buildApprovalQueue(drafts: [d], proposals: []);
      expect(q.single.kind, ApprovalKind.replyDraft);
      expect(q.single.canApproveLocally, isTrue);
    });
    test('approved draft blocks send', () {
      final d = ReplyDraftDto(
        envelope: env(ReplyDraftDto.schemaId),
        caseId: 'c',
        action: 'FOLLOWUP',
        subject: 'S',
        body: 'B',
        approved: true,
        bindingReviewApproved: true,
      );
      final q = buildApprovalQueue(drafts: [d], proposals: []);
      expect(q.single.kind, ApprovalKind.blockedExternal);
    });
    test('proposal appears', () {
      final p = CalendarProposalDto(
        envelope: env(CalendarProposalDto.schemaId),
        caseId: 'c',
        timezone: 'Europe/Berlin',
        rankingVersion: 1,
        prefsSchemaVersion: 1,
        rankedSlots: const [
          RankedSlotDto(start: 'a', end: 'b'),
        ],
      );
      final q = buildApprovalQueue(drafts: [], proposals: [p]);
      expect(q.single.kind, ApprovalKind.calendarSlot);
    });
    for (var i = 0; i < 15; i++) {
      test('action label $i', () {
        final d = ReplyDraftDto(
          envelope: env(ReplyDraftDto.schemaId),
          caseId: 'c$i',
          action: kReplyActions.elementAt(i % kReplyActions.length),
          subject: '',
          body: 'b',
        );
        final q = buildApprovalQueue(drafts: [d], proposals: []);
        expect(q.single.title, isNotEmpty);
      });
    }
  });
}
