import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/contracts/contracts.dart';
import 'package:karrierekrake_mobile/integrations/calendar_approval.dart';
import 'package:karrierekrake_mobile/integrations/push_policy.dart';
import 'package:karrierekrake_mobile/security/feature_flags.dart';

void main() {
  group('calendar approval', () {
    CalendarProposalDto proposal() => CalendarProposalDto(
          envelope: const ContractEnvelope(
            contractVersion: '1.0.0',
            schemaId: CalendarProposalDto.schemaId,
          ),
          caseId: 'c1',
          timezone: 'Europe/Berlin',
          rankingVersion: 1,
          prefsSchemaVersion: 1,
          rankedSlots: const [
            RankedSlotDto(
              start: '2026-09-22T09:00:00Z',
              end: '2026-09-22T10:00:00Z',
            ),
            RankedSlotDto(
              start: '2026-09-23T09:00:00Z',
              end: '2026-09-23T10:00:00Z',
            ),
          ],
        );

    test('select slot success', () {
      final svc = CalendarApprovalService();
      final r = svc.selectSlot(proposal(), 0);
      expect(r.status, CalendarApprovalStatus.slotSelected);
      expect(r.proposal!.selectedSlotIndex, 0);
    });

    test('conflict detection', () {
      final svc = CalendarApprovalService(
        existingBusyRanges: const [
          (start: '2026-09-22T09:30:00Z', end: '2026-09-22T11:00:00Z'),
        ],
      );
      final r = svc.selectSlot(proposal(), 0);
      expect(r.status, CalendarApprovalStatus.conflict);
    });

    test('write blocked by default flag', () {
      final svc = CalendarApprovalService();
      final selected = svc.selectSlot(proposal(), 1).proposal!;
      final w = svc.attemptWrite(
        proposal: selected,
        calendarPermissionGranted: true,
      );
      expect(w.status, CalendarApprovalStatus.writeBlocked);
    });

    test('permission denied when write flag on', () {
      final svc = CalendarApprovalService(
        flags: const MobileFeatureFlags(calendarWriteEnabled: true),
      );
      final selected = svc.selectSlot(proposal(), 1).proposal!;
      final w = svc.attemptWrite(
        proposal: selected,
        calendarPermissionGranted: false,
      );
      expect(w.status, CalendarApprovalStatus.permissionDenied);
    });

    test('write still stubbed even with permission', () {
      final svc = CalendarApprovalService(
        flags: const MobileFeatureFlags(calendarWriteEnabled: true),
      );
      final selected = svc.selectSlot(proposal(), 1).proposal!;
      final w = svc.attemptWrite(
        proposal: selected,
        calendarPermissionGranted: true,
      );
      expect(w.status, CalendarApprovalStatus.writeBlocked);
    });

    test('bad index', () {
      final r = CalendarApprovalService().selectSlot(proposal(), 99);
      expect(r.status, CalendarApprovalStatus.rejected);
    });
  });

  group('push policy', () {
    test('remote push blocked', () {
      final v = const PushPolicy().validatePayload({'remote': true, 'title': 'Hi'});
      expect(v.allowed, isFalse);
    });

    test('sensitive keys blocked', () {
      final v = const PushPolicy().validatePayload({
        'title': 'Reminder',
        'email': 'a@b.c',
      });
      expect(v.allowed, isFalse);
    });

    test('pii body blocked', () {
      final v = const PushPolicy().validatePayload({
        'title': 'x',
        'body': 'Schreib an hr@firma.de bitte',
      });
      expect(v.allowed, isFalse);
    });

    test('safe local payload', () {
      final v = const PushPolicy().validatePayload({
        'title': 'Follow-up fällig',
        'body': 'Fall prüfen',
      });
      expect(v.allowed, isTrue);
    });

    test('future work doc non-empty', () {
      expect(kPushFutureWork.contains('Future Work'), isTrue);
      expect(kPushFutureWork.contains('sync_decision'), isTrue);
    });
  });
}
