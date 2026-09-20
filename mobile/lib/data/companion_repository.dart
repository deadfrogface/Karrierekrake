import 'dart:convert';

import 'package:flutter/services.dart';

import '../contracts/contracts.dart';
import 'app_database.dart';

/// Local companion store. No network. Sync transport = UNSPECIFIED.
class CompanionRepository {
  CompanionRepository(this.db);

  final AppDatabase db;

  ProfileDto? profile;
  SearchIntentDto? searchIntent;
  List<JobDto> jobs = [];
  List<ApplicationCaseDto> cases = [];
  List<LifecycleEventDto> events = [];
  List<CalendarProposalDto> proposals = [];
  List<ReplyDraftDto> drafts = [];
  List<GuentherResultDto> guenther = [];
  bool offline = true; // MVP is offline-first; no cloud
  String? lastError;

  Future<void> loadFromDb() async {
    try {
      final profiles = await db.loadBySchema(ProfileDto.schemaId);
      profile = profiles.isEmpty ? null : ProfileDto.fromJson(profiles.first);

      final intents = await db.loadBySchema(SearchIntentDto.schemaId);
      searchIntent =
          intents.isEmpty ? null : SearchIntentDto.fromJson(intents.first);

      jobs = (await db.loadBySchema(JobDto.schemaId))
          .map(JobDto.fromJson)
          .toList();
      cases = (await db.loadBySchema(ApplicationCaseDto.schemaId))
          .map(ApplicationCaseDto.fromJson)
          .toList();
      events = (await db.loadBySchema(LifecycleEventDto.schemaId))
          .map(LifecycleEventDto.fromJson)
          .toList();
      proposals = (await db.loadBySchema(CalendarProposalDto.schemaId))
          .map(CalendarProposalDto.fromJson)
          .toList();
      drafts = (await db.loadBySchema(ReplyDraftDto.schemaId))
          .map(ReplyDraftDto.fromJson)
          .toList();
      guenther = (await db.loadBySchema(GuentherResultDto.schemaId))
          .map(GuentherResultDto.fromJson)
          .toList();
      lastError = null;
    } catch (e) {
      lastError = e.toString();
      rethrow;
    }
  }

  Future<void> seedFromAssetManifest(List<String> assetPaths) async {
    for (final path in assetPaths) {
      final raw = await rootBundle.loadString(path);
      final json = jsonDecode(raw) as Map<String, dynamic>;
      await _upsertParsed(json);
    }
    await loadFromDb();
  }

  Future<void> seedFromJsonMaps(List<Map<String, dynamic>> docs) async {
    for (final json in docs) {
      await _upsertParsed(json);
    }
    await loadFromDb();
  }

  Future<void> _upsertParsed(Map<String, dynamic> json) async {
    final schemaId = json['schema_id']?.toString() ?? '';
    final businessId = _businessId(schemaId, json);
    await db.upsertDocument(
      schemaId: schemaId,
      businessId: businessId,
      payload: json,
    );
  }

  String _businessId(String schemaId, Map<String, dynamic> json) {
    switch (schemaId) {
      case ProfileDto.schemaId:
        return 'singleton';
      case SearchIntentDto.schemaId:
        return 'singleton';
      case JobDto.schemaId:
      case ApplicationCaseDto.schemaId:
      case LifecycleEventDto.schemaId:
        return json['id']?.toString() ?? 'unknown';
      case CalendarProposalDto.schemaId:
      case ReplyDraftDto.schemaId:
        return '${json['case_id']}_${schemaId.hashCode}';
      case GuentherResultDto.schemaId:
        return json['capability']?.toString() ?? 'unknown';
      default:
        return json['id']?.toString() ?? 'doc';
    }
  }

  Future<void> saveProfile(ProfileDto next) async {
    profile = next;
    await db.upsertDocument(
      schemaId: ProfileDto.schemaId,
      businessId: 'singleton',
      payload: next.toJson(),
    );
  }

  Future<void> saveSearchIntent(SearchIntentDto next) async {
    // Guard: never silently expand to STRICT without explicit user choice.
    searchIntent = next;
    await db.upsertDocument(
      schemaId: SearchIntentDto.schemaId,
      businessId: 'singleton',
      payload: next.toJson(),
    );
  }

  Future<void> saveCaseNotes(ApplicationCaseDto next) async {
    await db.upsertDocument(
      schemaId: ApplicationCaseDto.schemaId,
      businessId: next.id,
      payload: next.toJson(),
    );
    cases = [
      for (final c in cases) if (c.id == next.id) next else c,
    ];
  }

  Future<void> saveProposal(CalendarProposalDto next) async {
    await db.upsertDocument(
      schemaId: CalendarProposalDto.schemaId,
      businessId: next.caseId,
      payload: next.toJson(),
    );
    proposals = [
      for (final p in proposals)
        if (p.caseId == next.caseId) next else p,
    ];
  }

  Future<void> saveDraft(ReplyDraftDto next) async {
    assert(next.autoSend == false);
    await db.upsertDocument(
      schemaId: ReplyDraftDto.schemaId,
      businessId: '${next.caseId}_${next.action}',
      payload: next.toJson(),
    );
    drafts = [
      for (final d in drafts)
        if (!(d.caseId == next.caseId && d.action == next.action)) d,
      next,
    ];
  }

  Future<LifecycleEventDto> appendManualOverride({
    required String caseId,
    required String note,
  }) async {
    final evt = LifecycleEventDto(
      envelope: const ContractEnvelope(
        contractVersion: kContractBundleVersion,
        schemaId: LifecycleEventDto.schemaId,
      ),
      eventType: 'MANUAL_OVERRIDE',
      id: 'manual-${DateTime.now().toUtc().millisecondsSinceEpoch}',
      caseId: caseId,
      occurredAt: DateTime.now().toUtc().toIso8601String(),
      recordedAt: DateTime.now().toUtc().toIso8601String(),
      idempotencyKey: 'manual:$caseId:${DateTime.now().toUtc().millisecondsSinceEpoch}',
      payload: {'note': note},
      source: 'mobile',
      confidence: 1.0,
    );
    await db.upsertDocument(
      schemaId: LifecycleEventDto.schemaId,
      businessId: evt.id,
      payload: evt.toJson(),
    );
    events = [...events, evt];
    return evt;
  }
}

/// Default demo asset paths shipped with the MVP (no secrets).
const kDemoAssetFixtures = <String>[
  'assets/fixtures/profile.valid.json',
  'assets/fixtures/search_intent.valid.json',
  'assets/fixtures/job.valid.json',
  'assets/fixtures/application_case.valid.json',
  'assets/fixtures/lifecycle_event.valid.json',
  'assets/fixtures/calendar_proposal.valid.json',
  'assets/fixtures/reply_draft.valid.json',
  'assets/fixtures/guenther_result.valid.json',
];
