import 'package:flutter/material.dart';

import '../../contracts/calendar_proposal_dto.dart';
import '../../integrations/calendar_approval.dart';
import '../widgets/state_views.dart';
import 'shell.dart';

class CalendarScreen extends StatelessWidget {
  const CalendarScreen({
    super.key,
    required this.proposals,
    this.approvalService,
  });

  final List<CalendarProposalDto> proposals;
  final CalendarApprovalService? approvalService;

  @override
  Widget build(BuildContext context) {
    if (proposals.isEmpty) {
      return const EmptyStateView(
        title: 'Keine Terminvorschläge',
        message: 'Slot wählen lokal OK — Kalender-Write ist blockiert (kein Sync).',
        icon: Icons.event_busy,
      );
    }
    final repo = CompanionScope.of(context).repo;
    final approval = approvalService ?? CalendarApprovalService();
    return ListView.builder(
      itemCount: proposals.length,
      itemBuilder: (context, i) {
        final p = proposals[i];
        return ExpansionTile(
          title: Text('Fall ${p.caseId}'),
          subtitle: Text('${p.status} · ${p.timezone} · ${p.modality}'),
          children: [
            for (var idx = 0; idx < p.rankedSlots.length; idx++)
              ListTile(
                title: Text(
                  '${p.rankedSlots[idx].start} → ${p.rankedSlots[idx].end}',
                ),
                subtitle: Text('Score ${p.rankedSlots[idx].score ?? '-'}'),
                trailing: p.selectedSlotIndex == idx
                    ? const Icon(Icons.check_circle)
                    : TextButton(
                        onPressed: () async {
                          final result = approval.selectSlot(p, idx);
                          if (result.status == CalendarApprovalStatus.conflict) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(
                                    'Konflikt: ${result.conflictWith ?? result.message}',
                                  ),
                                ),
                              );
                            }
                            return;
                          }
                          if (result.proposal == null) return;
                          await repo.saveProposal(result.proposal!);
                          // Explicit write attempt — always blocked until approved transport.
                          final write = approval.attemptWrite(
                            proposal: result.proposal!,
                            calendarPermissionGranted: false,
                          );
                          if (!context.mounted) return;
                          await CompanionScope.of(context).refresh();
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(
                                  '${result.message}. Write: ${write.status.name}',
                                ),
                              ),
                            );
                          }
                        },
                        child: const Text('Wählen'),
                      ),
              ),
          ],
        );
      },
    );
  }
}
