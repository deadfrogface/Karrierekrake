import 'package:flutter/material.dart';

import '../widgets/state_views.dart';
import 'shell.dart';

class TimelineScreen extends StatelessWidget {
  const TimelineScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final events = [...CompanionScope.of(context).repo.events]
      ..sort((a, b) => b.occurredAt.compareTo(a.occurredAt));
    if (events.isEmpty) {
      return const EmptyStateView(
        title: 'Timeline leer',
        message: 'LifecycleEvents sind append-only.',
        icon: Icons.timeline,
      );
    }
    return ListView.builder(
      itemCount: events.length,
      itemBuilder: (context, i) {
        final e = events[i];
        return Semantics(
          label: 'Ereignis ${e.eventType} für Fall ${e.caseId}',
          child: ListTile(
            leading: const Icon(Icons.circle, size: 12),
            title: Text(e.eventType),
            subtitle: Text('${e.caseId} · ${e.occurredAt}'),
            isThreeLine: e.payload.isNotEmpty,
            trailing: e.source.isEmpty ? null : Text(e.source),
          ),
        );
      },
    );
  }
}
