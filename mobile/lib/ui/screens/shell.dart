import 'package:flutter/material.dart';

import '../../data/companion_repository.dart';
import '../../domain/approvals.dart';
import '../../domain/follow_up.dart';
import '../widgets/state_views.dart';
import 'approvals_screen.dart';
import 'applications_screen.dart';
import 'calendar_screen.dart';
import 'dashboard_screen.dart';
import 'drafts_screen.dart';
import 'jobs_screen.dart';
import 'profile_screen.dart';
import 'search_intent_screen.dart';
import 'timeline_screen.dart';

class CompanionScope extends InheritedWidget {
  const CompanionScope({
    super.key,
    required this.repo,
    required this.refresh,
    required super.child,
  });

  final CompanionRepository repo;
  final Future<void> Function() refresh;

  static CompanionScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<CompanionScope>();
    assert(scope != null, 'CompanionScope missing');
    return scope!;
  }

  @override
  bool updateShouldNotify(CompanionScope oldWidget) =>
      repo != oldWidget.repo;
}

class CompanionShell extends StatefulWidget {
  const CompanionShell({super.key, required this.repo});

  final CompanionRepository repo;

  @override
  State<CompanionShell> createState() => _CompanionShellState();
}

class _CompanionShellState extends State<CompanionShell> {
  int _index = 0;

  Future<void> _refresh() async {
    await widget.repo.loadFromDb();
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final repo = widget.repo;
    final hints = deriveFollowUpHints(
      cases: repo.cases,
      events: repo.events,
      drafts: repo.drafts,
    );
    final approvals = buildApprovalQueue(
      drafts: repo.drafts,
      proposals: repo.proposals,
    );

    final pages = <Widget>[
      DashboardScreen(hints: hints, approvalCount: approvals.length),
      const JobsScreen(),
      const ApplicationsScreen(),
      const TimelineScreen(),
      DraftsScreen(drafts: repo.drafts),
      CalendarScreen(proposals: repo.proposals),
      ApprovalsScreen(items: approvals),
      ProfileScreen(profile: repo.profile),
      SearchIntentScreen(intent: repo.searchIntent),
    ];

    return CompanionScope(
      repo: repo,
      refresh: _refresh,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Karrierekrake'),
          actions: [
            IconButton(
              tooltip: 'Aktualisieren',
              onPressed: _refresh,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        body: Column(
          children: [
            OfflineBanner(offline: repo.offline),
            if (repo.lastError != null)
              ErrorStateView(message: repo.lastError!, onRetry: _refresh),
            Expanded(child: pages[_index]),
          ],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _index.clamp(0, 4),
          onDestinationSelected: (i) => setState(() => _index = i),
          destinations: const [
            NavigationDestination(
              icon: Icon(Icons.dashboard_outlined),
              selectedIcon: Icon(Icons.dashboard),
              label: 'Home',
            ),
            NavigationDestination(
              icon: Icon(Icons.work_outline),
              selectedIcon: Icon(Icons.work),
              label: 'Jobs',
            ),
            NavigationDestination(
              icon: Icon(Icons.folder_open),
              selectedIcon: Icon(Icons.folder),
              label: 'Fälle',
            ),
            NavigationDestination(
              icon: Icon(Icons.timeline_outlined),
              selectedIcon: Icon(Icons.timeline),
              label: 'Timeline',
            ),
            NavigationDestination(
              icon: Icon(Icons.more_horiz),
              selectedIcon: Icon(Icons.more_horiz),
              label: 'Mehr',
            ),
          ],
        ),
        drawer: Drawer(
          child: SafeArea(
            child: ListView(
              children: [
                const DrawerHeader(
                  child: Text(
                    'Karrierekrake Companion',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
                  ),
                ),
                _drawerItem(0, 'Dashboard', Icons.dashboard),
                _drawerItem(1, 'Jobs', Icons.work),
                _drawerItem(2, 'Bewerbungen', Icons.folder),
                _drawerItem(3, 'Timeline', Icons.timeline),
                _drawerItem(4, 'Antwortentwürfe', Icons.mail_outline),
                _drawerItem(5, 'Kalender-Vorschläge', Icons.event),
                _drawerItem(6, 'Freigaben', Icons.verified_user),
                _drawerItem(7, 'Profil', Icons.person),
                _drawerItem(8, 'SearchIntent', Icons.search),
                const Divider(),
                const ListTile(
                  dense: true,
                  title: Text(
                    'Kein Cloud-Backend · Kein Phi-Download · Kein Desktop-Port',
                    style: TextStyle(fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _drawerItem(int i, String label, IconData icon) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label),
      selected: _index == i,
      onTap: () {
        setState(() => _index = i);
        Navigator.pop(context);
      },
    );
  }
}
