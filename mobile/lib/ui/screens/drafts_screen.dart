import 'package:flutter/material.dart';

import '../../contracts/reply_draft_dto.dart';
import '../widgets/state_views.dart';

class DraftsScreen extends StatelessWidget {
  const DraftsScreen({super.key, required this.drafts});

  final List<ReplyDraftDto> drafts;

  @override
  Widget build(BuildContext context) {
    if (drafts.isEmpty) {
      return const EmptyStateView(
        title: 'Keine Entwürfe',
        message: 'ReplyDrafts sind draft_only — Senden braucht Sync-Transport.',
        icon: Icons.mail_outline,
      );
    }
    return ListView.separated(
      itemCount: drafts.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, i) {
        final d = drafts[i];
        return ListTile(
          title: Text(d.subject),
          subtitle: Text('${d.action} · auto_send=${d.autoSend} · approved=${d.approved}'),
          isThreeLine: true,
          onTap: () {
            showDialog<void>(
              context: context,
              builder: (ctx) => AlertDialog(
                title: Text(d.subject),
                content: SingleChildScrollView(child: Text(d.body)),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx),
                    child: const Text('Schließen'),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }
}
