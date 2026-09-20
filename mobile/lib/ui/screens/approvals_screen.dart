import 'package:flutter/material.dart';

import '../../contracts/reply_draft_dto.dart';
import '../../domain/approvals.dart';
import '../widgets/state_views.dart';
import 'shell.dart';

class ApprovalsScreen extends StatelessWidget {
  const ApprovalsScreen({super.key, required this.items});

  final List<ApprovalItem> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const EmptyStateView(
        title: 'Keine Freigaben',
        message: 'Entwürfe und Terminvorschläge erscheinen hier zur Prüfung.',
        icon: Icons.verified_user_outlined,
      );
    }
    final repo = CompanionScope.of(context).repo;
    return ListView.separated(
      itemCount: items.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, i) {
        final item = items[i];
        return ListTile(
          leading: Icon(
            item.kind == ApprovalKind.blockedExternal
                ? Icons.block
                : Icons.rule,
          ),
          title: Text(item.title),
          subtitle: Text(item.subtitle),
          trailing: item.canApproveLocally
              ? FilledButton(
                  onPressed: () async {
                    if (item.kind == ApprovalKind.replyDraft) {
                      ReplyDraftDto? match;
                      for (final d in repo.drafts) {
                        if (item.id == 'draft-${d.caseId}-${d.action}') {
                          match = d;
                          break;
                        }
                      }
                      if (match != null && context.mounted) {
                        await repo.saveDraft(match.markApprovedLocally());
                        await CompanionScope.of(context).refresh();
                      }
                    }
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(
                            item.kind == ApprovalKind.calendarSlot
                                ? 'Bitte Slot unter Kalender wählen.'
                                : 'Lokal freigegeben — Versand weiterhin blockiert.',
                          ),
                        ),
                      );
                    }
                  },
                  child: const Text('Freigeben'),
                )
              : const Text('Blockiert'),
        );
      },
    );
  }
}
