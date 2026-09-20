/// Local calendar **approval** — selects a slot and records intent.
/// Actual OS calendar write stays gated until transport + permission approved.
library;

import '../contracts/calendar_proposal_dto.dart';
import '../security/feature_flags.dart';

enum CalendarApprovalStatus {
  pending,
  slotSelected,
  rejected,
  writeBlocked,
  permissionDenied,
  conflict,
}

class CalendarApprovalResult {
  const CalendarApprovalResult({
    required this.status,
    this.proposal,
    this.message = '',
    this.conflictWith,
  });

  final CalendarApprovalStatus status;
  final CalendarProposalDto? proposal;
  final String message;
  final String? conflictWith;
}

class CalendarApprovalService {
  CalendarApprovalService({
    this.flags = MobileFeatureFlags.commercialSafe,
    this.existingBusyRanges = const [],
  });

  MobileFeatureFlags flags;

  /// Local busy intervals as ISO start|end pairs for conflict detection.
  List<({String start, String end})> existingBusyRanges;

  CalendarApprovalResult selectSlot(
    CalendarProposalDto proposal,
    int index,
  ) {
    if (proposal.rankedSlots.isEmpty) {
      return const CalendarApprovalResult(
        status: CalendarApprovalStatus.rejected,
        message: 'no slots',
      );
    }
    if (index < 0 || index >= proposal.rankedSlots.length) {
      return const CalendarApprovalResult(
        status: CalendarApprovalStatus.rejected,
        message: 'index out of range',
      );
    }
    final slot = proposal.rankedSlots[index];
    final conflict = _findConflict(slot.start, slot.end);
    if (conflict != null) {
      return CalendarApprovalResult(
        status: CalendarApprovalStatus.conflict,
        message: 'slot conflicts with local busy range',
        conflictWith: conflict,
      );
    }
    final selected = proposal.selectSlot(index);
    return CalendarApprovalResult(
      status: CalendarApprovalStatus.slotSelected,
      proposal: selected,
      message: 'slot selected locally — calendar write not performed',
    );
  }

  /// Attempt OS calendar write — blocked unless flag + permission.
  CalendarApprovalResult attemptWrite({
    required CalendarProposalDto proposal,
    required bool calendarPermissionGranted,
  }) {
    if (!flags.calendarWriteEnabled) {
      return CalendarApprovalResult(
        status: CalendarApprovalStatus.writeBlocked,
        proposal: proposal,
        message:
            'calendar write disabled — sync/transport UNSPECIFIED (see sync_decision.md)',
      );
    }
    if (!calendarPermissionGranted) {
      return CalendarApprovalResult(
        status: CalendarApprovalStatus.permissionDenied,
        proposal: proposal,
        message: 'calendar permission denied',
      );
    }
    if (proposal.selectedSlotIndex == null) {
      return const CalendarApprovalResult(
        status: CalendarApprovalStatus.rejected,
        message: 'no selected slot',
      );
    }
    // Even with flag on, we do not invent a cloud calendar API here.
    return CalendarApprovalResult(
      status: CalendarApprovalStatus.writeBlocked,
      proposal: proposal,
      message:
          'OS calendar provider integration stub — enable only after privacy review',
    );
  }

  String? _findConflict(String start, String end) {
    final a0 = DateTime.tryParse(start);
    final a1 = DateTime.tryParse(end);
    if (a0 == null || a1 == null) return null;
    for (final busy in existingBusyRanges) {
      final b0 = DateTime.tryParse(busy.start);
      final b1 = DateTime.tryParse(busy.end);
      if (b0 == null || b1 == null) continue;
      final overlaps = a0.isBefore(b1) && b0.isBefore(a1);
      if (overlaps) return '${busy.start}/${busy.end}';
    }
    return null;
  }
}
