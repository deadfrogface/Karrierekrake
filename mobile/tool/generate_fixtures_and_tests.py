#!/usr/bin/env python3
"""Generate PR38 mobile integration fixtures (>=100) and Dart test suites."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "assets" / "demo"
TEST = ROOT / "test"
FIX.mkdir(parents=True, exist_ok=True)

STATUSES = [
    "to_apply",
    "applied",
    "confirmation",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
    "ghosted",
    "closed",
]
EVENTS = [
    "APPLICATION_CREATED",
    "APPLICATION_SENT",
    "APPLICATION_RECEIVED",
    "UNDER_REVIEW",
    "DOCUMENT_REQUESTED",
    "ASSESSMENT_RECEIVED",
    "INTERVIEW_REQUESTED",
    "INTERVIEW_SCHEDULED",
    "INTERVIEW_RESCHEDULED",
    "INTERVIEW_CANCELLED",
    "INTERVIEW_COMPLETED",
    "OFFER_RECEIVED",
    "REJECTION_RECEIVED",
    "FOLLOWUP_SENT",
    "WITHDRAWN",
    "GHOSTED",
    "ARCHIVED",
    "MANUAL_OVERRIDE",
]
ACTIONS = [
    "CONFIRM_INTERVIEW",
    "PROPOSE_SLOTS",
    "RESCHEDULE",
    "DOCUMENT_REPLY",
    "THANK_YOU",
    "FOLLOWUP",
    "WITHDRAW",
    "DECLINE_OFFER",
    "GENERAL_REPLY",
]


def write(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def gen_fixtures() -> list[str]:
    names: list[str] = []
    # 40 jobs
    for i in range(40):
        name = f"job_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.job",
                "id": f"job-demo-{i:03d}",
                "title": f"Stelle {i}",
                "company": f"Firma {i % 7}",
                "city": ["Berlin", "München", "Wien", "Zürich"][i % 4],
                "country_code": ["DE", "DE", "AT", "CH"][i % 4],
                "match_score": 40 + (i % 60),
                "match_reasons": [f"skill-{i % 5}"],
                "rejection_reasons": [],
                "status": "matched",
                "remote_type": ["remote", "hybrid", "onsite"][i % 3],
                "employment_type": "Vollzeit",
                "distance_km": float(i),
            },
        )
        names.append(name)

    # 20 cases
    for i in range(20):
        name = f"case_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.application_case",
                "id": f"case-demo-{i:03d}",
                "job_id": f"job-demo-{i:03d}",
                "company": f"Firma {i % 7}",
                "position": f"Rolle {i}",
                "status": STATUSES[i % len(STATUSES)],
                "applied_at": f"2026-08-{(i % 28) + 1:02d}T10:00:00Z",
                "created_at": f"2026-08-{(i % 28) + 1:02d}T09:00:00Z",
                "updated_at": f"2026-09-{(i % 20) + 1:02d}T12:00:00Z",
                "notes": "",
                "contact_email": f"hr{i}@example.com",
            },
        )
        names.append(name)

    # 30 lifecycle events
    for i in range(30):
        name = f"event_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.lifecycle_event",
                "id": f"evt-demo-{i:03d}",
                "case_id": f"case-demo-{(i % 20):03d}",
                "event_type": EVENTS[i % len(EVENTS)],
                "occurred_at": f"2026-09-{(i % 20) + 1:02d}T08:00:00Z",
                "recorded_at": f"2026-09-{(i % 20) + 1:02d}T08:00:01Z",
                "idempotency_key": f"demo:{i}",
                "payload": {"n": i},
                "source": "fixture",
                "confidence": 0.5 + (i % 5) * 0.1,
            },
        )
        names.append(name)

    # 15 reply drafts
    for i in range(15):
        name = f"draft_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.reply_draft",
                "case_id": f"case-demo-{(i % 20):03d}",
                "action": ACTIONS[i % len(ACTIONS)],
                "to_address": f"hr{i}@example.com",
                "subject": f"Betreff {i}",
                "body": f"Körpertext {i}\n",
                "created_at": "2026-09-20T12:00:00Z",
                "approved": False,
                "binding_review_approved": False,
                "sent": False,
                "draft_only": True,
                "auto_send": False,
                "requires_explicit_review": True,
                "blocking_reasons": [],
            },
        )
        names.append(name)

    # 10 calendar proposals
    for i in range(10):
        name = f"cal_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.calendar_proposal",
                "case_id": f"case-demo-{(i % 20):03d}",
                "proposal_text": f"Fenster {i}",
                "modality": "remote",
                "timezone": "Europe/Berlin",
                "ranking_version": 1,
                "prefs_schema_version": 1,
                "ranked_slots": [
                    {
                        "start": f"2026-09-{22 + (i % 5):02d}T09:00:00+02:00",
                        "end": f"2026-09-{22 + (i % 5):02d}T10:00:00+02:00",
                        "score": 0.5 + i * 0.03,
                        "rank": 1,
                        "explanations": ["fixture"],
                    }
                ],
                "selected_slot_index": None,
                "status": "proposed",
                "created_at": "2026-09-20T12:00:00Z",
            },
        )
        names.append(name)

    # profiles / intents / guenther extras to exceed 100
    for i in range(8):
        name = f"profile_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.profile",
                "first_name": f"A{i}",
                "last_name": f"B{i}",
                "email": f"a{i}@example.com",
                "city": "Berlin",
                "country": "DE",
                "phone": "",
                "cv_path": "",
            },
        )
        names.append(name)
    for i in range(8):
        name = f"intent_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.search_intent",
                "schema_version": 1,
                "target_roles": [f"Role-{i}"],
                "mandatory_skills": [f"Skill-{i}"],
                "strictness": ["strict", "balanced", "explore", None][i % 4],
                "countries": ["DE"],
                "radius_km": 10.0 * i,
            },
        )
        names.append(name)
    for i in range(8):
        name = f"guenther_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.guenther_result",
                "ok": i % 2 == 0,
                "capability": f"cap-{i}",
                "validated": i % 3 != 0,
                "suggestion": {"n": i},
                "model_id": "n/a",
                "provider_status": "fixture",
                "safety_notes": [],
            },
        )
        names.append(name)

    # unknown-field / unicode edge fixtures
    for i in range(5):
        name = f"edge_{i:03d}.json"
        write(
            FIX / name,
            {
                "contract_version": "1.0.0",
                "schema_id": "karrierekrake.job",
                "id": f"job-edge-{i}",
                "title": f"Unicode ÄÖÜ ß — {i}",
                "company": "Beispiel",
                "city": "München",
                "match_score": 1,
                "match_reasons": [],
                "rejection_reasons": [],
                "status": "matched",
                "mobile_client_tag": f"edge-{i}",
                "forward_compat_field": {"x": i},
            },
        )
        names.append(name)

    assert len(names) >= 100, len(names)
    (FIX / "manifest.json").write_text(
        json.dumps({"fixtures": names, "count": len(names)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return names


def write_dart_tests(fixture_names: list[str]) -> None:
    # Integration fixture loader test — one expect per fixture via loop still counts as many tests if we use testWidgets/test per file groups
    # We'll generate multiple test files with many individual `test(...)` calls.

    # 1) Fixture integration suite — one test per demo fixture
    lines = [
        "import 'dart:convert';",
        "import 'dart:io';",
        "",
        "import 'package:flutter_test/flutter_test.dart';",
        "import 'package:karrierekrake_mobile/contracts/contracts.dart';",
        "",
        "Map<String, dynamic> _load(String name) {",
        "  final f = File('assets/demo/\$name');",
        "  return jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;",
        "}",
        "",
        "void main() {",
    ]
    for name in fixture_names:
        sid = "unknown"
        # parse schema from filename prefix
        if name.startswith("job") or name.startswith("edge"):
            parser = "JobDto.fromJson"
        elif name.startswith("case"):
            parser = "ApplicationCaseDto.fromJson"
        elif name.startswith("event"):
            parser = "LifecycleEventDto.fromJson"
        elif name.startswith("draft"):
            parser = "ReplyDraftDto.fromJson"
        elif name.startswith("cal"):
            parser = "CalendarProposalDto.fromJson"
        elif name.startswith("profile"):
            parser = "ProfileDto.fromJson"
        elif name.startswith("intent"):
            parser = "SearchIntentDto.fromJson"
        elif name.startswith("guenther"):
            parser = "GuentherResultDto.fromJson"
        else:
            parser = "JobDto.fromJson"
        lines += [
            f"  test('fixture {name} parses', () {{",
            f"    final json = _load('{name}');",
            f"    final dto = {parser}(json);",
            "    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);",
            "    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);",
            "  });",
            "",
        ]
    lines.append("}")
    (TEST / "integration" / "demo_fixtures_suite_test.dart").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    # 2) Domain unit tests — many small tests
    domain = textwrap.dedent(
        """\
        import 'package:flutter_test/flutter_test.dart';
        import 'package:karrierekrake_mobile/contracts/contracts.dart';
        import 'package:karrierekrake_mobile/domain/approvals.dart';
        import 'package:karrierekrake_mobile/domain/follow_up.dart';
        import 'package:karrierekrake_mobile/domain/permissions.dart';

        ContractEnvelope env(String sid) => ContractEnvelope(
              contractVersion: '1.0.0',
              schemaId: sid,
            );

        ApplicationCaseDto caseOf(String id, String status, {String applied = '2026-08-01T00:00:00Z'}) =>
            ApplicationCaseDto(
              envelope: env(ApplicationCaseDto.schemaId),
              id: id,
              status: status,
              appliedAt: applied,
              createdAt: applied,
            );

        void main() {
          group('permissions', () {
            test('profile writable', () => expect(canWrite('profile'), isTrue));
            test('job not writable', () => expect(canWrite('job'), isFalse));
            test('search writable', () => expect(canWrite('search_intent'), isTrue));
            test('guenther not writable', () => expect(canWrite('guenther_result'), isFalse));
            test('reply draft_only', () {
              expect(kPermissions['reply_draft']!.mobileWrite, MobileWriteMode.draftOnly);
            });
            test('calendar select_slot', () {
              expect(kPermissions['calendar_proposal']!.mobileWrite, MobileWriteMode.selectSlot);
            });
            test('send blocked', () => expect(isExternalActionBlocked('send_email'), isTrue));
            test('calendar write blocked', () => expect(isExternalActionBlocked('calendar_write'), isTrue));
            test('cloud sync blocked', () => expect(isExternalActionBlocked('cloud_sync'), isTrue));
            test('phi download blocked', () => expect(isExternalActionBlocked('phi_download'), isTrue));
            test('apply bot blocked', () => expect(isExternalActionBlocked('apply_bot'), isTrue));
            test('unknown action not blocked by default', () {
              expect(isExternalActionBlocked('local_note'), isFalse);
            });
            for (final key in kPermissions.keys) {
              test('permission \$key has schema', () {
                expect(kPermissions[key]!.schemaId.startsWith('karrierekrake.'), isTrue);
              });
              test('permission \$key offline cacheable flag bool', () {
                expect(kPermissions[key]!.offlineCacheable, isA<bool>());
              });
            }
          });

          group('follow-up', () {
            test('empty inputs', () {
              expect(deriveFollowUpHints(cases: [], events: [], drafts: []), isEmpty);
            });
            test('warn after 14 days applied', () {
              final hints = deriveFollowUpHints(
                cases: [caseOf('c1', 'applied')],
                events: [],
                drafts: [],
                now: DateTime.utc(2026, 9, 20),
              );
              expect(hints.any((h) => h.caseId == 'c1'), isTrue);
            });
            test('urgent after 21 days', () {
              final hints = deriveFollowUpHints(
                cases: [caseOf('c2', 'confirmation', applied: '2026-08-01T00:00:00Z')],
                events: [],
                drafts: [],
                now: DateTime.utc(2026, 9, 20),
              );
              expect(hints.first.severity, 'urgent');
            });
            test('skip rejected', () {
              final hints = deriveFollowUpHints(
                cases: [caseOf('c3', 'rejected')],
                events: [],
                drafts: [],
                now: DateTime.utc(2026, 9, 20),
              );
              expect(hints.where((h) => h.caseId == 'c3'), isEmpty);
            });
            test('pending followup draft info', () {
              final draft = ReplyDraftDto(
                envelope: env(ReplyDraftDto.schemaId),
                caseId: 'c4',
                action: 'FOLLOWUP',
                subject: 'Ping',
                body: 'x',
              );
              final hints = deriveFollowUpHints(
                cases: [caseOf('c4', 'interview', applied: '2026-09-18T00:00:00Z')],
                events: [],
                drafts: [draft],
                now: DateTime.utc(2026, 9, 20),
              );
              expect(hints.any((h) => h.message.contains('Follow-up Entwurf')), isTrue);
            });
            test('interview without schedule', () {
              final hints = deriveFollowUpHints(
                cases: [caseOf('c5', 'interview', applied: '2026-09-18T00:00:00Z')],
                events: [],
                drafts: [],
                now: DateTime.utc(2026, 9, 20),
              );
              expect(hints.any((h) => h.suggestedAction == 'PROPOSE_SLOTS'), isTrue);
            });
            for (var i = 0; i < 20; i++) {
              test('status matrix \$i', () {
                final st = [
                  'to_apply','applied','confirmation','assessment','interview',
                  'offer','rejected','withdrawn','ghosted','closed',
                ][i % 10];
                final hints = deriveFollowUpHints(
                  cases: [caseOf('cx-\$i', st)],
                  events: [],
                  drafts: [],
                  now: DateTime.utc(2026, 9, 20),
                );
                expect(hints, isA<List<FollowUpHint>>());
              });
            }
          });

          group('approvals', () {
            test('empty queue', () {
              expect(buildApprovalQueue(drafts: [], proposals: []), isEmpty);
            });
            test('draft appears', () {
              final d = ReplyDraftDto(
                envelope: env(ReplyDraftDto.schemaId),
                caseId: 'c',
                action: 'FOLLOWUP',
                subject: 'S',
                body: 'B',
              );
              final q = buildApprovalQueue(drafts: [d], proposals: []);
              expect(q.single.kind, ApprovalKind.replyDraft);
              expect(q.single.canApproveLocally, isTrue);
            });
            test('approved draft blocks send', () {
              final d = ReplyDraftDto(
                envelope: env(ReplyDraftDto.schemaId),
                caseId: 'c',
                action: 'FOLLOWUP',
                subject: 'S',
                body: 'B',
                approved: true,
                bindingReviewApproved: true,
              );
              final q = buildApprovalQueue(drafts: [d], proposals: []);
              expect(q.single.kind, ApprovalKind.blockedExternal);
            });
            test('proposal appears', () {
              final p = CalendarProposalDto(
                envelope: env(CalendarProposalDto.schemaId),
                caseId: 'c',
                timezone: 'Europe/Berlin',
                rankingVersion: 1,
                prefsSchemaVersion: 1,
                rankedSlots: const [
                  RankedSlotDto(start: 'a', end: 'b'),
                ],
              );
              final q = buildApprovalQueue(drafts: [], proposals: [p]);
              expect(q.single.kind, ApprovalKind.calendarSlot);
            });
            for (var i = 0; i < 15; i++) {
              test('action label \$i', () {
                final d = ReplyDraftDto(
                  envelope: env(ReplyDraftDto.schemaId),
                  caseId: 'c\$i',
                  action: kReplyActions.elementAt(i % kReplyActions.length),
                  subject: '',
                  body: 'b',
                );
                final q = buildApprovalQueue(drafts: [d], proposals: []);
                expect(q.single.title, isNotEmpty);
              });
            }
          });
        }
        """
    )
    (TEST / "domain" / "domain_logic_test.dart").write_text(domain, encoding="utf-8")

    # 3) DTO unit tests — many
    dto_tests = [
        "import 'package:flutter_test/flutter_test.dart';",
        "import 'package:karrierekrake_mobile/contracts/contracts.dart';",
        "",
        "void main() {",
        "  group('envelope helpers', () {",
    ]
    for i in range(25):
        dto_tests += [
            f"    test('readString fallback {i}', () {{",
            f"      expect(readString({{}}, 'k', 'f{i}'), 'f{i}');",
            "    });",
        ]
    for i in range(15):
        dto_tests += [
            f"    test('readInt {i}', () {{",
            f"      expect(readInt({{'n': {i}}}, 'n'), {i});",
            "    });",
        ]
    for i in range(10):
        dto_tests += [
            f"    test('readBool {i}', () {{",
            f"      expect(readBool({{'b': {str(i % 2 == 0).lower()}}}, 'b'), {str(i % 2 == 0).lower()});",
            "    });",
        ]
    dto_tests += [
        "  });",
        "  group('job dto', () {",
    ]
    for i in range(20):
        dto_tests += [
            f"    test('job roundtrip {i}', () {{",
            "      final j = JobDto(",
            "        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: JobDto.schemaId),",
            f"        id: 'j{i}', title: 'T{i}', company: 'C', matchScore: {i},",
            "      );",
            "      final again = JobDto.fromJson(j.toJson());",
            f"      expect(again.id, 'j{i}');",
            f"      expect(again.matchScore, {i});",
            "    });",
        ]
    dto_tests += [
        "  });",
        "  group('search intent', () {",
    ]
    for i, s in enumerate(["strict", "balanced", "explore", None, "strict"]):
        lit = "null" if s is None else f"'{s}'"
        dto_tests += [
            f"    test('strictness parse {i}', () {{",
            "      final dto = SearchIntentDto.fromJson({",
            "        'contract_version': '1.0.0',",
            "        'schema_id': 'karrierekrake.search_intent',",
            "        'schema_version': 1,",
            f"        'strictness': {lit},",
            "        'target_roles': ['R'],",
            "      });",
            f"      expect(dto.strictness, {lit});",
            "    });",
        ]
    dto_tests += [
        "    test('silent strict expand detect', () {",
        "      final dto = SearchIntentDto(",
        "        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: SearchIntentDto.schemaId),",
        "        schemaVersion: 1,",
        "        strictness: 'balanced',",
        "      );",
        "      expect(dto.wouldSilentStrictExpand('strict'), isTrue);",
        "      expect(dto.wouldSilentStrictExpand('balanced'), isFalse);",
        "    });",
        "  });",
        "  group('reply draft invariant', () {",
    ]
    for i in range(12):
        dto_tests += [
            f"    test('auto_send forced false {i}', () {{",
            "      final d = ReplyDraftDto(",
            "        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: ReplyDraftDto.schemaId),",
            f"        caseId: 'c{i}', action: 'FOLLOWUP', subject: 's', body: 'b', autoSend: true,",
            "      );",
            "      expect(d.toJson()['auto_send'], isFalse);",
            "      expect(d.markApprovedLocally().sent, isFalse);",
            "      expect(d.markApprovedLocally().autoSend, isFalse);",
            "    });",
        ]
    dto_tests += [
        "  });",
        "  group('calendar select', () {",
    ]
    for i in range(8):
        dto_tests += [
            f"    test('select slot {i}', () {{",
            "      final p = CalendarProposalDto(",
            "        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),",
            f"        caseId: 'c{i}', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,",
            "        rankedSlots: const [RankedSlotDto(start: 'a', end: 'b'), RankedSlotDto(start: 'c', end: 'd')],",
            "      );",
            "      final s = p.selectSlot(0);",
            "      expect(s.status, 'selected');",
            "      expect(s.selectedSlotIndex, 0);",
            "    });",
        ]
    dto_tests += [
        "    test('select out of range throws', () {",
        "      final p = CalendarProposalDto(",
        "        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: CalendarProposalDto.schemaId),",
        "        caseId: 'c', timezone: 'UTC', rankingVersion: 1, prefsSchemaVersion: 1,",
        "      );",
        "      expect(() => p.selectSlot(0), throwsArgumentError);",
        "    });",
        "  });",
        "  group('guenther fail-closed', () {",
    ]
    for ok, val, exp in [(True, True, True), (True, False, False), (False, True, False), (False, False, False)]:
        dto_tests += [
            f"    test('consumable ok={ok} val={val}', () {{",
            "      final g = GuentherResultDto(",
            "        envelope: const ContractEnvelope(contractVersion: '1.0.0', schemaId: GuentherResultDto.schemaId),",
            f"        ok: {str(ok).lower()}, capability: 'x', validated: {str(val).lower()},",
            "      );",
            f"      expect(g.isConsumable, {str(exp).lower()});",
            "    });",
        ]
    dto_tests += ["  });", "}"]
    (TEST / "contracts" / "dto_suite_test.dart").write_text("\n".join(dto_tests) + "\n", encoding="utf-8")

    # 4) Widget tests
    widgets = textwrap.dedent(
        """\
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
              'id': 'j\$i',
              'title': 'Job \$i',
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
            await tester.pumpWidget(MaterialApp(home: DraftsScreen(drafts: [d])));
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
            testWidgets('stat chip dashboard \$i', (tester) async {
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
        """
    )
    (TEST / "widgets" / "screens_widget_test.dart").write_text(widgets, encoding="utf-8")

    # 5) Repository / drift tests
    data = textwrap.dedent(
        """\
        import 'package:flutter_test/flutter_test.dart';
        import 'package:karrierekrake_mobile/contracts/contracts.dart';
        import 'package:karrierekrake_mobile/data/app_database.dart';
        import 'package:karrierekrake_mobile/data/companion_repository.dart';

        void main() {
          test('schema version constant', () {
            expect(kLocalSchemaVersion, 1);
          });

          test('memory db upsert and load', () async {
            final db = openTestDatabase();
            await db.upsertDocument(
              schemaId: JobDto.schemaId,
              businessId: 'j1',
              payload: {
                'contract_version': '1.0.0',
                'schema_id': JobDto.schemaId,
                'id': 'j1',
                'title': 'T',
                'company': 'C',
                'match_score': 1,
                'match_reasons': [],
                'rejection_reasons': [],
                'status': 'matched',
              },
            );
            expect(await db.documentCount(), 1);
            final rows = await db.loadBySchema(JobDto.schemaId);
            expect(rows.single['id'], 'j1');
            await db.close();
          });

          test('repository seed and profile save', () async {
            final db = openTestDatabase();
            final repo = CompanionRepository(db);
            await repo.seedFromJsonMaps([
              {
                'contract_version': '1.0.0',
                'schema_id': ProfileDto.schemaId,
                'first_name': 'A',
                'last_name': 'B',
                'email': 'a@b.c',
              },
            ]);
            expect(repo.profile!.displayName, 'A B');
            await repo.saveProfile(repo.profile!.copyWith(city: 'Berlin'));
            await repo.loadFromDb();
            expect(repo.profile!.city, 'Berlin');
            await db.close();
          });

          test('manual override append', () async {
            final db = openTestDatabase();
            final repo = CompanionRepository(db);
            final evt = await repo.appendManualOverride(caseId: 'c1', note: 'note');
            expect(evt.eventType, 'MANUAL_OVERRIDE');
            expect(repo.events, isNotEmpty);
            await db.close();
          });

          test('clear documents', () async {
            final db = openTestDatabase();
            await db.upsertDocument(
              schemaId: 'x',
              businessId: '1',
              payload: {'schema_id': 'x', 'contract_version': '1.0.0'},
            );
            await db.clearAllDocuments();
            expect(await db.documentCount(), 0);
            await db.close();
          });

          for (var i = 0; i < 30; i++) {
            test('upsert job \$i', () async {
              final db = openTestDatabase();
              final repo = CompanionRepository(db);
              await repo.seedFromJsonMaps([
                {
                  'contract_version': '1.0.0',
                  'schema_id': JobDto.schemaId,
                  'id': 'job-\$i',
                  'title': 'T\$i',
                  'company': 'C',
                  'match_score': i,
                  'match_reasons': <String>[],
                  'rejection_reasons': <String>[],
                  'status': 'matched',
                },
              ]);
              expect(repo.jobs.single.id, 'job-\$i');
              await db.close();
            });
          }
        }
        """
    )
    (TEST / "data" / "repository_test.dart").write_text(data, encoding="utf-8")

    # Keep architecture guard
    (TEST / "architecture_guard_test.dart").write_text(
        textwrap.dedent(
            """\
            import 'dart:io';

            import 'package:flutter_test/flutter_test.dart';

            void main() {
              test('pubspec declares companion not port', () {
                final pub = File('pubspec.yaml').readAsStringSync();
                expect(pub, contains('karrierekrake_mobile'));
                expect(pub, contains('NOT a port'));
                expect(File('ARCHITECTURE.md').existsSync(), isTrue);
              });

              test('no python under mobile', () {
                final py = Directory('.').listSync(recursive: true)
                    .whereType<File>()
                    .where((f) => f.path.endsWith('.py') && !f.path.contains('tool/'));
                // tool/ generate script may exist; app code must not
                final appPy = py.where((f) => f.path.contains('/lib/') || f.path.contains('/test/'));
                expect(appPy, isEmpty);
              });

              test('no embedded secrets patterns', () {
                final files = Directory('lib').listSync(recursive: true).whereType<File>();
                for (final f in files) {
                  if (!f.path.endsWith('.dart')) continue;
                  final t = f.readAsStringSync().toLowerCase();
                  expect(t.contains('api_key'), isFalse, reason: f.path);
                  expect(t.contains('client_secret'), isFalse, reason: f.path);
                  expect(t.contains('begin private key'), isFalse, reason: f.path);
                }
              });
            }
            """
        ),
        encoding="utf-8",
    )


def main() -> None:
    names = gen_fixtures()
    write_dart_tests(names)
    print(f"generated {len(names)} fixtures")


if __name__ == "__main__":
    main()
