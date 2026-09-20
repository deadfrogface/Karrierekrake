import 'package:flutter/material.dart';

import '../widgets/state_views.dart';
import 'shell.dart';

class ApplicationsScreen extends StatelessWidget {
  const ApplicationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final repo = CompanionScope.of(context).repo;
    final cases = repo.cases;
    if (cases.isEmpty) {
      return const EmptyStateView(
        title: 'Keine Bewerbungen',
        message: 'Fälle werden als ApplicationCase-Contracts lokal gelesen.',
      );
    }
    return ListView.separated(
      itemCount: cases.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, i) {
        final c = cases[i];
        return Semantics(
          button: true,
          label: 'Bewerbung ${c.position} bei ${c.company}, Status ${c.status}',
          child: ListTile(
          title: Text(c.position.isEmpty ? c.id : c.position),
          subtitle: Text('${c.company} · ${c.status}'),
          trailing: const Icon(Icons.chevron_right),
          onTap: () async {
            final controller = TextEditingController(text: c.notes);
            final note = await showDialog<String>(
              context: context,
              builder: (ctx) => AlertDialog(
                title: const Text('Notiz (limited write)'),
                content: TextField(
                  controller: controller,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    hintText: 'Lokale Notiz — kein Status-Rewrite',
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(ctx),
                    child: const Text('Abbrechen'),
                  ),
                  FilledButton(
                    onPressed: () => Navigator.pop(ctx, controller.text),
                    child: const Text('Speichern'),
                  ),
                ],
              ),
            );
            if (note != null && context.mounted) {
              await repo.saveCaseNotes(c.copyWithNotes(note));
              await CompanionScope.of(context).refresh();
            }
          },
        ),
        );
      },
    );
  }
}
