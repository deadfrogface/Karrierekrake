import 'dart:convert';
import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

part 'app_database.g.dart';

/// Local schema version — bump on migrations. Mobile-only; never touches desktop data.
const int kLocalSchemaVersion = 1;

class ContractDocuments extends Table {
  TextColumn get docKey => text()(); // schema_id + ':' + business id
  TextColumn get schemaId => text()();
  TextColumn get businessId => text().withDefault(const Constant(''))();
  TextColumn get payloadJson => text()();
  DateTimeColumn get updatedAt => dateTime()();

  @override
  Set<Column> get primaryKey => {docKey};
}

class AppMeta extends Table {
  TextColumn get key => text()();
  TextColumn get value => text()();

  @override
  Set<Column> get primaryKey => {key};
}

@DriftDatabase(tables: [ContractDocuments, AppMeta])
class AppDatabase extends _$AppDatabase {
  AppDatabase(super.e);

  @override
  int get schemaVersion => kLocalSchemaVersion;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) async {
          await m.createAll();
          await into(appMeta).insert(
            AppMetaCompanion.insert(
              key: 'schema_version',
              value: '$kLocalSchemaVersion',
            ),
          );
          await into(appMeta).insert(
            AppMetaCompanion.insert(
              key: 'sync_transport',
              value: 'UNSPECIFIED',
            ),
          );
        },
        onUpgrade: (m, from, to) async {
          // Future migrations go here. v1 has no upgrades yet.
        },
      );

  Future<void> upsertDocument({
    required String schemaId,
    required String businessId,
    required Map<String, dynamic> payload,
  }) {
    final key = '$schemaId:$businessId';
    return into(contractDocuments).insertOnConflictUpdate(
      ContractDocumentsCompanion.insert(
        docKey: key,
        schemaId: schemaId,
        businessId: Value(businessId),
        payloadJson: jsonEncode(payload),
        updatedAt: DateTime.now().toUtc(),
      ),
    );
  }

  Future<List<Map<String, dynamic>>> loadBySchema(String schemaId) async {
    final rows = await (select(contractDocuments)
          ..where((t) => t.schemaId.equals(schemaId)))
        .get();
    return rows
        .map((r) => jsonDecode(r.payloadJson) as Map<String, dynamic>)
        .toList();
  }

  Future<Map<String, dynamic>?> loadOne(String schemaId, String businessId) async {
    final key = '$schemaId:$businessId';
    final row = await (select(contractDocuments)
          ..where((t) => t.docKey.equals(key)))
        .getSingleOrNull();
    if (row == null) return null;
    return jsonDecode(row.payloadJson) as Map<String, dynamic>;
  }

  Future<int> documentCount() async {
    final count = countAll();
    final query = selectOnly(contractDocuments)..addColumns([count]);
    final row = await query.getSingle();
    return row.read(count) ?? 0;
  }

  Future<void> clearAllDocuments() async {
    await delete(contractDocuments).go();
  }
}

LazyDatabase openConnection({String? overridePath}) {
  return LazyDatabase(() async {
    if (overridePath != null) {
      return NativeDatabase(File(overridePath));
    }
    final dir = await getApplicationDocumentsDirectory();
    final file = File(p.join(dir.path, 'karrierekrake_companion_v$kLocalSchemaVersion.sqlite'));
    return NativeDatabase.createInBackground(file);
  });
}

/// In-memory DB for tests — does not touch desktop AppData.
AppDatabase openTestDatabase() {
  driftRuntimeOptions.dontWarnAboutMultipleDatabases = true;
  return AppDatabase(NativeDatabase.memory());
}
