import 'package:flutter/material.dart';

import '../../domain/follow_up.dart';
import '../widgets/state_views.dart';
import 'shell.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    required this.hints,
    required this.approvalCount,
  });

  final List<FollowUpHint> hints;
  final int approvalCount;

  @override
  Widget build(BuildContext context) {
    final repo = CompanionScope.of(context).repo;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Dashboard',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 4),
        Text(
          'Companion MVP — lokal, ohne Feature-Parität zur Desktop-App.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _StatChip(label: 'Jobs', value: '${repo.jobs.length}'),
            _StatChip(label: 'Fälle', value: '${repo.cases.length}'),
            _StatChip(label: 'Freigaben', value: '$approvalCount'),
            _StatChip(label: 'Hinweise', value: '${hints.length}'),
          ],
        ),
        const SizedBox(height: 24),
        Text('Follow-up Hinweise', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (hints.isEmpty)
          const EmptyStateView(
            title: 'Keine Hinweise',
            message: 'Sobald Fälle länger ohne Reaktion bleiben, erscheinen Tipps hier.',
            icon: Icons.notifications_none,
          )
        else
          ...hints.map(
            (h) => ListTile(
              leading: Icon(
                h.severity == 'urgent'
                    ? Icons.priority_high
                    : h.severity == 'warn'
                        ? Icons.warning_amber
                        : Icons.info_outline,
              ),
              title: Text(h.message),
              subtitle: Text('Fall ${h.caseId} · ${h.suggestedAction}'),
            ),
          ),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  const _StatChip({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '$label: $value',
      child: Chip(label: Text('$label · $value')),
    );
  }
}
