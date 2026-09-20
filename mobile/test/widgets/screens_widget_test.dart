import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/contracts/contracts.dart';
import 'package:karrierekrake_mobile/data/app_database.dart';
import 'package:karrierekrake_mobile/data/companion_repository.dart';
import 'package:karrierekrake_mobile/domain/approvals.dart';
import 'package:karrierekrake_mobile/domain/follow_up.dart';
import 'package:karrierekrake_mobile/ui/screens/approvals_screen.dart';
import 'package:karrierekrake_mobile/ui/screens/calendar_screen.dart';
import 'package:karrierekrake_mobile/ui/screens/dashboard_screen.dart';
import 'package:karrierekrake_mobile/ui/screens/drafts_screen.dart';
import 'package:karrierekrake_mobile/ui/screens/jobs_screen.dart';
import 'package:karrierekrake_mobile/ui/screens/shell.dart';
import 'package:karrierekrake_mobile/ui/widgets/state_views.dart';

Widget wrap(CompanionRepository repo, Widget child) {
  return MaterialApp(
    home: CompanionScope(
      repo: repo,
      refresh: () async {},
      child: Scaffold(body: child),
    ),
  );
}

Future<CompanionRepository> repoWithJobs(int n) async {
  final db = openTestDatabase();
  final repo = CompanionRepository(db);
  final docs = <Map<String, dynamic>>[];
  for (var i = 0; i < n; i++) {
    docs.add({
      'contract_version': '1.0.0',
      'schema_id': JobDto.schemaId,
      'id': 'j$i',
      'title': 'Job $i',
      'company': 'Co',
      'city': 'Berlin',
      'match_score': i,
      'match_reasons': <String>[],
      'rejection_reasons': <String>[],
      'status': 'matched',
    });
  }
  await repo.seedFromJsonMaps(docs);
  return repo;
}

void main() {
  testWidgets('empty state semantics', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: EmptyStateView(title: 'Leer', message: 'Nichts da'),
    ));
    expect(find.text('Leer'), findsOneWidget);
  });

  testWidgets('error state retry', (tester) async {
    var tapped = false;
    await tester.pumpWidget(MaterialApp(
      home: ErrorStateView(message: 'Boom', onRetry: () => tapped = true),
    ));
    await tester.tap(find.text('Erneut versuchen'));
    expect(tapped, isTrue);
  });

  testWidgets('offline banner', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: OfflineBanner()));
    expect(find.textContaining('UNSPECIFIED'), findsOneWidget);
  });

  testWidgets('dashboard empty hints', (tester) async {
    final db = openTestDatabase();
    final repo = CompanionRepository(db);
    await tester.pumpWidget(wrap(repo, const DashboardScreen(hints: [], approvalCount: 0)));
    expect(find.text('Dashboard'), findsOneWidget);
    expect(find.text('Keine Hinweise'), findsOneWidget);
  });

  testWidgets('dashboard with hint', (tester) async {
    final db = openTestDatabase();
    final repo = CompanionRepository(db);
    await tester.pumpWidget(wrap(
      repo,
      DashboardScreen(
        hints: const [
          FollowUpHint(caseId: 'c1', severity: 'warn', message: 'Bitte nachfassen'),
        ],
        approvalCount: 2,
      ),
    ));
    expect(find.textContaining('nachfassen'), findsOneWidget);
  });

  testWidgets('jobs empty', (tester) async {
    final db = openTestDatabase();
    final repo = CompanionRepository(db);
    await tester.pumpWidget(wrap(repo, const JobsScreen()));
    expect(find.text('Keine Jobs'), findsOneWidget);
  });

  testWidgets('jobs list', (tester) async {
    final repo = await repoWithJobs(3);
    await tester.pumpWidget(wrap(repo, const JobsScreen()));
    expect(find.textContaining('Job'), findsWidgets);
  });

  testWidgets('drafts empty', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: DraftsScreen(drafts: [])));
    expect(find.text('Keine Entwürfe'), findsOneWidget);
  });

  testWidgets('drafts list', (tester) async {
    final d = ReplyDraftDto(
      envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),
      caseId: 'c',
      action: 'FOLLOWUP',
      subject: 'Betreff X',
      body: 'Body',
    );
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: DraftsScreen(drafts: [d]))));
    expect(find.text('Betreff X'), findsOneWidget);
  });

  testWidgets('calendar empty', (tester) async {
    final db = openTestDatabase();
    final repo = CompanionRepository(db);
    await tester.pumpWidget(wrap(repo, const CalendarScreen(proposals: [])));
    expect(find.text('Keine Terminvorschläge'), findsOneWidget);
  });

  testWidgets('approvals empty', (tester) async {
    final db = openTestDatabase();
    final repo = CompanionRepository(db);
    await tester.pumpWidget(wrap(repo, const ApprovalsScreen(items: [])));
    expect(find.text('Keine Freigaben'), findsOneWidget);
  });

  testWidgets('approvals item', (tester) async {
    final db = openTestDatabase();
    final repo = CompanionRepository(db);
    await tester.pumpWidget(wrap(
      repo,
      ApprovalsScreen(items: const [
        ApprovalItem(
          id: 'x',
          kind: ApprovalKind.replyDraft,
          title: 'Titel',
          subtitle: 'Sub',
          canApproveLocally: true,
        ),
      ]),
    ));
    expect(find.text('Titel'), findsOneWidget);
    expect(find.text('Freigeben'), findsOneWidget);
  });

  for (var i = 0; i < 20; i++) {
    testWidgets('stat chip dashboard $i', (tester) async {
      final db = openTestDatabase();
      final repo = CompanionRepository(db);
      await tester.pumpWidget(wrap(
        repo,
        DashboardScreen(hints: const [], approvalCount: i),
      ));
      expect(find.textContaining('Freigaben'), findsOneWidget);
    });
  }
}
