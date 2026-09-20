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
    test('upsert job $i', () async {
      final db = openTestDatabase();
      final repo = CompanionRepository(db);
      await repo.seedFromJsonMaps([
        {
          'contract_version': '1.0.0',
          'schema_id': JobDto.schemaId,
          'id': 'job-$i',
          'title': 'T$i',
          'company': 'C',
          'match_score': i,
          'match_reasons': <String>[],
          'rejection_reasons': <String>[],
          'status': 'matched',
        },
      ]);
      expect(repo.jobs.single.id, 'job-$i');
      await db.close();
    });
  }
}
