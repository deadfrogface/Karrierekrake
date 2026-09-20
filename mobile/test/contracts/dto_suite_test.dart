import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/contracts/contracts.dart';

void main() {
  group('envelope helpers', () {
    test('readString fallback 0', () {
      expect(readString({}, 'k', 'f0'), 'f0');
    });
    test('readString fallback 1', () {
      expect(readString({}, 'k', 'f1'), 'f1');
    });
    test('readString fallback 2', () {
      expect(readString({}, 'k', 'f2'), 'f2');
    });
    test('readString fallback 3', () {
      expect(readString({}, 'k', 'f3'), 'f3');
    });
    test('readString fallback 4', () {
      expect(readString({}, 'k', 'f4'), 'f4');
    });
    test('readString fallback 5', () {
      expect(readString({}, 'k', 'f5'), 'f5');
    });
    test('readString fallback 6', () {
      expect(readString({}, 'k', 'f6'), 'f6');
    });
    test('readString fallback 7', () {
      expect(readString({}, 'k', 'f7'), 'f7');
    });
    test('readString fallback 8', () {
      expect(readString({}, 'k', 'f8'), 'f8');
    });
    test('readString fallback 9', () {
      expect(readString({}, 'k', 'f9'), 'f9');
    });
    test('readString fallback 10', () {
      expect(readString({}, 'k', 'f10'), 'f10');
    });
    test('readString fallback 11', () {
      expect(readString({}, 'k', 'f11'), 'f11');
    });
    test('readString fallback 12', () {
      expect(readString({}, 'k', 'f12'), 'f12');
    });
    test('readString fallback 13', () {
      expect(readString({}, 'k', 'f13'), 'f13');
    });
    test('readString fallback 14', () {
      expect(readString({}, 'k', 'f14'), 'f14');
    });
    test('readString fallback 15', () {
      expect(readString({}, 'k', 'f15'), 'f15');
    });
    test('readString fallback 16', () {
      expect(readString({}, 'k', 'f16'), 'f16');
    });
    test('readString fallback 17', () {
      expect(readString({}, 'k', 'f17'), 'f17');
    });
    test('readString fallback 18', () {
      expect(readString({}, 'k', 'f18'), 'f18');
    });
    test('readString fallback 19', () {
      expect(readString({}, 'k', 'f19'), 'f19');
    });
    test('readString fallback 20', () {
      expect(readString({}, 'k', 'f20'), 'f20');
    });
    test('readString fallback 21', () {
      expect(readString({}, 'k', 'f21'), 'f21');
    });
    test('readString fallback 22', () {
      expect(readString({}, 'k', 'f22'), 'f22');
    });
    test('readString fallback 23', () {
      expect(readString({}, 'k', 'f23'), 'f23');
    });
    test('readString fallback 24', () {
      expect(readString({}, 'k', 'f24'), 'f24');
    });
    test('readInt 0', () {
      expect(readInt({'n': 0}, 'n'), 0);
    });
    test('readInt 1', () {
      expect(readInt({'n': 1}, 'n'), 1);
    });
    test('readInt 2', () {
      expect(readInt({'n': 2}, 'n'), 2);
    });
    test('readInt 3', () {
      expect(readInt({'n': 3}, 'n'), 3);
    });
    test('readInt 4', () {
      expect(readInt({'n': 4}, 'n'), 4);
    });
    test('readInt 5', () {
      expect(readInt({'n': 5}, 'n'), 5);
    });
    test('readInt 6', () {
      expect(readInt({'n': 6}, 'n'), 6);
    });
    test('readInt 7', () {
      expect(readInt({'n': 7}, 'n'), 7);
    });
    test('readInt 8', () {
      expect(readInt({'n': 8}, 'n'), 8);
    });
    test('readInt 9', () {
      expect(readInt({'n': 9}, 'n'), 9);
    });
    test('readInt 10', () {
      expect(readInt({'n': 10}, 'n'), 10);
    });
    test('readInt 11', () {
      expect(readInt({'n': 11}, 'n'), 11);
    });
    test('readInt 12', () {
      expect(readInt({'n': 12}, 'n'), 12);
    });
    test('readInt 13', () {
      expect(readInt({'n': 13}, 'n'), 13);
    });
    test('readInt 14', () {
      expect(readInt({'n': 14}, 'n'), 14);
    });
    test('readBool 0', () {
      expect(readBool({'b': true}, 'b'), true);
    });
    test('readBool 1', () {
      expect(readBool({'b': false}, 'b'), false);
    });
    test('readBool 2', () {
      expect(readBool({'b': true}, 'b'), true);
    });
    test('readBool 3', () {
      expect(readBool({'b': false}, 'b'), false);
    });
    test('readBool 4', () {
      expect(readBool({'b': true}, 'b'), true);
    });
    test('readBool 5', () {
      expect(readBool({'b': false}, 'b'), false);
    });
    test('readBool 6', () {
      expect(readBool({'b': true}, 'b'), true);
    });
    test('readBool 7', () {
      expect(readBool({'b': false}, 'b'), false);
    });
    test('readBool 8', () {
      expect(readBool({'b': true}, 'b'), true);
    });
    test('readBool 9', () {
      expect(readBool({'b': false}, 'b'), false);
    });
  });
  group('job dto', () {
    test('job roundtrip 0', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j0', title: 'T0', company: 'C', matchScore: 0,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j0');
      expect(again.matchScore, 0);
    });
    test('job roundtrip 1', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j1', title: 'T1', company: 'C', matchScore: 1,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j1');
      expect(again.matchScore, 1);
    });
    test('job roundtrip 2', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j2', title: 'T2', company: 'C', matchScore: 2,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j2');
      expect(again.matchScore, 2);
    });
    test('job roundtrip 3', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j3', title: 'T3', company: 'C', matchScore: 3,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j3');
      expect(again.matchScore, 3);
    });
    test('job roundtrip 4', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j4', title: 'T4', company: 'C', matchScore: 4,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j4');
      expect(again.matchScore, 4);
    });
    test('job roundtrip 5', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j5', title: 'T5', company: 'C', matchScore: 5,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j5');
      expect(again.matchScore, 5);
    });
    test('job roundtrip 6', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j6', title: 'T6', company: 'C', matchScore: 6,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j6');
      expect(again.matchScore, 6);
    });
    test('job roundtrip 7', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j7', title: 'T7', company: 'C', matchScore: 7,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j7');
      expect(again.matchScore, 7);
    });
    test('job roundtrip 8', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j8', title: 'T8', company: 'C', matchScore: 8,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j8');
      expect(again.matchScore, 8);
    });
    test('job roundtrip 9', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j9', title: 'T9', company: 'C', matchScore: 9,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j9');
      expect(again.matchScore, 9);
    });
    test('job roundtrip 10', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j10', title: 'T10', company: 'C', matchScore: 10,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j10');
      expect(again.matchScore, 10);
    });
    test('job roundtrip 11', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j11', title: 'T11', company: 'C', matchScore: 11,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j11');
      expect(again.matchScore, 11);
    });
    test('job roundtrip 12', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j12', title: 'T12', company: 'C', matchScore: 12,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j12');
      expect(again.matchScore, 12);
    });
    test('job roundtrip 13', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j13', title: 'T13', company: 'C', matchScore: 13,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j13');
      expect(again.matchScore, 13);
    });
    test('job roundtrip 14', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j14', title: 'T14', company: 'C', matchScore: 14,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j14');
      expect(again.matchScore, 14);
    });
    test('job roundtrip 15', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j15', title: 'T15', company: 'C', matchScore: 15,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j15');
      expect(again.matchScore, 15);
    });
    test('job roundtrip 16', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j16', title: 'T16', company: 'C', matchScore: 16,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j16');
      expect(again.matchScore, 16);
    });
    test('job roundtrip 17', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j17', title: 'T17', company: 'C', matchScore: 17,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j17');
      expect(again.matchScore, 17);
    });
    test('job roundtrip 18', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j18', title: 'T18', company: 'C', matchScore: 18,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j18');
      expect(again.matchScore, 18);
    });
    test('job roundtrip 19', () {
      final j = JobDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),
        id: 'j19', title: 'T19', company: 'C', matchScore: 19,
      );
      final again = JobDto.fromJson(j.toJson());
      expect(again.id, 'j19');
      expect(again.matchScore, 19);
    });
  });
  group('search intent', () {
    test('strictness parse 0', () {
      final dto = SearchIntentDto.fromJson({
        'contract_version': '1.0.0',
        'schema_id': 'karrierekrake.search_intent',
        'schema_version': 1,
        'strictness': 'strict',
        'target_roles': ['R'],
      });
      expect(dto.strictness, 'strict');
    });
    test('strictness parse 1', () {
      final dto = SearchIntentDto.fromJson({
        'contract_version': '1.0.0',
        'schema_id': 'karrierekrake.search_intent',
        'schema_version': 1,
        'strictness': 'balanced',
        'target_roles': ['R'],
      });
      expect(dto.strictness, 'balanced');
    });
    test('strictness parse 2', () {
      final dto = SearchIntentDto.fromJson({
        'contract_version': '1.0.0',
        'schema_id': 'karrierekrake.search_intent',
        'schema_version': 1,
        'strictness': 'explore',
        'target_roles': ['R'],
      });
      expect(dto.strictness, 'explore');
    });
    test('strictness parse 3', () {
      final dto = SearchIntentDto.fromJson({
        'contract_version': '1.0.0',
        'schema_id': 'karrierekrake.search_intent',
        'schema_version': 1,
        'strictness': null,
        'target_roles': ['R'],
      });
      expect(dto.strictness, null);
    });
    test('strictness parse 4', () {
      final dto = SearchIntentDto.fromJson({
        'contract_version': '1.0.0',
        'schema_id': 'karrierekrake.search_intent',
        'schema_version': 1,
        'strictness': 'strict',
        'target_roles': ['R'],
      });
      expect(dto.strictness, 'strict');
    });
    test('silent strict expand detect', () {
      final dto = SearchIntentDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: SearchIntentDto.schemaId),
        schemaVersion: 1,
        strictness: 'balanced',
      );
      expect(dto.wouldSilentStrictExpand('strict'), isTrue);
      expect(dto.wouldSilentStrictExpand('balanced'), isFalse);
    });
  });
  group('reply draft invariant', () {
    test('auto_send forced false 0', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c0', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 1', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c1', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 2', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c2', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 3', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c3', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 4', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c4', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 5', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c5', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 6', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c6', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 7', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c7', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 8', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c8', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 9', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c9', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 10', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c10', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
    test('auto_send forced false 11', () {
      final d = ReplyDraftDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
        caseId: 'c11', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,
      );
      expect(d.toJson()['auto_send'], isFalse);
      expect(d.markApprovedLocally().sent, isFalse);
      expect(d.markApprovedLocally().autoSend, isFalse);
    });
  });
  group('calendar select', () {
    test('select slot 0', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c0', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select slot 1', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c1', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select slot 2', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c2', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select slot 3', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c3', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select slot 4', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c4', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select slot 5', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c5', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select slot 6', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c6', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select slot 7', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c7', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],
      );
      final s = p.selectSlot(0);
      expect(s.status, 'selected');
      expect(s.selectedSlotIndex, 0);
    });
    test('select out of range throws', () {
      final p = CalendarProposalDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),
        caseId: 'c', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,
      );
      expect(() => p.selectSlot(0), throwsArgumentError);
    });
  });
  group('guenther fail-closed', () {
    test('consumable ok=True val=True', () {
      final g = GuentherResultDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: GuentherResultDto.schemaId),
        ok: true, capability: 'x', validated: true,
      );
      expect(g.isConsumable, true);
    });
    test('consumable ok=True val=False', () {
      final g = GuentherResultDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: GuentherResultDto.schemaId),
        ok: true, capability: 'x', validated: false,
      );
      expect(g.isConsumable, false);
    });
    test('consumable ok=False val=True', () {
      final g = GuentherResultDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: GuentherResultDto.schemaId),
        ok: false, capability: 'x', validated: true,
      );
      expect(g.isConsumable, false);
    });
    test('consumable ok=False val=False', () {
      final g = GuentherResultDto(
        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: GuentherResultDto.schemaId),
        ok: false, capability: 'x', validated: false,
      );
      expect(g.isConsumable, false);
    });
  });
}
