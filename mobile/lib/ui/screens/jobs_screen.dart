import 'package:flutter/material.dart';

import '../widgets/state_views.dart';
import 'shell.dart';

class JobsScreen extends StatelessWidget {
  const JobsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final jobs = CompanionScope.of(context).repo.jobs;
    if (jobs.isEmpty) {
      return const EmptyStateView(
        title: 'Keine Jobs',
        message:
            'Jobs kommen von Desktop/Agents als Contract-Snapshots. Mobile scrapet nicht.',
        icon: Icons.work_off_outlined,
      );
    }
    return ListView.separated(
      itemCount: jobs.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, i) {
        final j = jobs[i];
        return Semantics(
          button: true,
          label: '${j.title}, ${j.company}, Score ${j.matchScore}',
          child: ListTile(
          title: Text(j.title.isEmpty ? j.id : j.title),
          subtitle: Text('${j.company} · ${j.city} · Score ${j.matchScore}'),
          isThreeLine: j.matchReasons.isNotEmpty,
          trailing: Text('${j.matchScore}'),
          onTap: () {
            showModalBottomSheet<void>(
              context: context,
              builder: (_) => Padding(
                padding: const EdgeInsets.all(16),
                child: ListView(
                  children: [
                    Text(j.title, style: Theme.of(context).textTheme.titleLarge),
                    Text('${j.company} · ${j.remoteType} · ${j.employmentType}'),
                    const SizedBox(height: 12),
                    Text('Passend', style: Theme.of(context).textTheme.titleSmall),
                    ...j.matchReasons.map((r) => Text('• $r')),
                    if (j.rejectionReasons.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      Text('Abzüge', style: Theme.of(context).textTheme.titleSmall),
                      ...j.rejectionReasons.map((r) => Text('• $r')),
                    ],
                  ],
                ),
              ),
            );
          },
        ),
        );
      },
    );
  }
}
