// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'app_database.dart';

// ignore_for_file: type=lint
class $ContractDocumentsTable extends ContractDocuments
    with TableInfo<$ContractDocumentsTable, ContractDocument> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $ContractDocumentsTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _docKeyMeta = const VerificationMeta('docKey');
  @override
  late final GeneratedColumn<String> docKey = GeneratedColumn<String>(
      'doc_key', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _schemaIdMeta =
      const VerificationMeta('schemaId');
  @override
  late final GeneratedColumn<String> schemaId = GeneratedColumn<String>(
      'schema_id', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _businessIdMeta =
      const VerificationMeta('businessId');
  @override
  late final GeneratedColumn<String> businessId = GeneratedColumn<String>(
      'business_id', aliasedName, false,
      type: DriftSqlType.string,
      requiredDuringInsert: false,
      defaultValue: const Constant(''));
  static const VerificationMeta _payloadJsonMeta =
      const VerificationMeta('payloadJson');
  @override
  late final GeneratedColumn<String> payloadJson = GeneratedColumn<String>(
      'payload_json', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _updatedAtMeta =
      const VerificationMeta('updatedAt');
  @override
  late final GeneratedColumn<DateTime> updatedAt = GeneratedColumn<DateTime>(
      'updated_at', aliasedName, false,
      type: DriftSqlType.dateTime, requiredDuringInsert: true);
  @override
  List<GeneratedColumn> get $columns =>
      [docKey, schemaId, businessId, payloadJson, updatedAt];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'contract_documents';
  @override
  VerificationContext validateIntegrity(Insertable<ContractDocument> instance,
      {bool isInserting = false}) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('doc_key')) {
      context.handle(_docKeyMeta,
          docKey.isAcceptableOrUnknown(data['doc_key']!, _docKeyMeta));
    } else if (isInserting) {
      context.missing(_docKeyMeta);
    }
    if (data.containsKey('schema_id')) {
      context.handle(_schemaIdMeta,
          schemaId.isAcceptableOrUnknown(data['schema_id']!, _schemaIdMeta));
    } else if (isInserting) {
      context.missing(_schemaIdMeta);
    }
    if (data.containsKey('business_id')) {
      context.handle(
          _businessIdMeta,
          businessId.isAcceptableOrUnknown(
              data['business_id']!, _businessIdMeta));
    }
    if (data.containsKey('payload_json')) {
      context.handle(
          _payloadJsonMeta,
          payloadJson.isAcceptableOrUnknown(
              data['payload_json']!, _payloadJsonMeta));
    } else if (isInserting) {
      context.missing(_payloadJsonMeta);
    }
    if (data.containsKey('updated_at')) {
      context.handle(_updatedAtMeta,
          updatedAt.isAcceptableOrUnknown(data['updated_at']!, _updatedAtMeta));
    } else if (isInserting) {
      context.missing(_updatedAtMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {docKey};
  @override
  ContractDocument map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return ContractDocument(
      docKey: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}doc_key'])!,
      schemaId: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}schema_id'])!,
      businessId: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}business_id'])!,
      payloadJson: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}payload_json'])!,
      updatedAt: attachedDatabase.typeMapping
          .read(DriftSqlType.dateTime, data['${effectivePrefix}updated_at'])!,
    );
  }

  @override
  $ContractDocumentsTable createAlias(String alias) {
    return $ContractDocumentsTable(attachedDatabase, alias);
  }
}

class ContractDocument extends DataClass
    implements Insertable<ContractDocument> {
  final String docKey;
  final String schemaId;
  final String businessId;
  final String payloadJson;
  final DateTime updatedAt;
  const ContractDocument(
      {required this.docKey,
      required this.schemaId,
      required this.businessId,
      required this.payloadJson,
      required this.updatedAt});
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['doc_key'] = Variable<String>(docKey);
    map['schema_id'] = Variable<String>(schemaId);
    map['business_id'] = Variable<String>(businessId);
    map['payload_json'] = Variable<String>(payloadJson);
    map['updated_at'] = Variable<DateTime>(updatedAt);
    return map;
  }

  ContractDocumentsCompanion toCompanion(bool nullToAbsent) {
    return ContractDocumentsCompanion(
      docKey: Value(docKey),
      schemaId: Value(schemaId),
      businessId: Value(businessId),
      payloadJson: Value(payloadJson),
      updatedAt: Value(updatedAt),
    );
  }

  factory ContractDocument.fromJson(Map<String, dynamic> json,
      {ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return ContractDocument(
      docKey: serializer.fromJson<String>(json['docKey']),
      schemaId: serializer.fromJson<String>(json['schemaId']),
      businessId: serializer.fromJson<String>(json['businessId']),
      payloadJson: serializer.fromJson<String>(json['payloadJson']),
      updatedAt: serializer.fromJson<DateTime>(json['updatedAt']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'docKey': serializer.toJson<String>(docKey),
      'schemaId': serializer.toJson<String>(schemaId),
      'businessId': serializer.toJson<String>(businessId),
      'payloadJson': serializer.toJson<String>(payloadJson),
      'updatedAt': serializer.toJson<DateTime>(updatedAt),
    };
  }

  ContractDocument copyWith(
          {String? docKey,
          String? schemaId,
          String? businessId,
          String? payloadJson,
          DateTime? updatedAt}) =>
      ContractDocument(
        docKey: docKey ?? this.docKey,
        schemaId: schemaId ?? this.schemaId,
        businessId: businessId ?? this.businessId,
        payloadJson: payloadJson ?? this.payloadJson,
        updatedAt: updatedAt ?? this.updatedAt,
      );
  ContractDocument copyWithCompanion(ContractDocumentsCompanion data) {
    return ContractDocument(
      docKey: data.docKey.present ? data.docKey.value : this.docKey,
      schemaId: data.schemaId.present ? data.schemaId.value : this.schemaId,
      businessId:
          data.businessId.present ? data.businessId.value : this.businessId,
      payloadJson:
          data.payloadJson.present ? data.payloadJson.value : this.payloadJson,
      updatedAt: data.updatedAt.present ? data.updatedAt.value : this.updatedAt,
    );
  }

  @override
  String toString() {
    return (StringBuffer('ContractDocument(')
          ..write('docKey: $docKey, ')
          ..write('schemaId: $schemaId, ')
          ..write('businessId: $businessId, ')
          ..write('payloadJson: $payloadJson, ')
          ..write('updatedAt: $updatedAt')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode =>
      Object.hash(docKey, schemaId, businessId, payloadJson, updatedAt);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is ContractDocument &&
          other.docKey == this.docKey &&
          other.schemaId == this.schemaId &&
          other.businessId == this.businessId &&
          other.payloadJson == this.payloadJson &&
          other.updatedAt == this.updatedAt);
}

class ContractDocumentsCompanion extends UpdateCompanion<ContractDocument> {
  final Value<String> docKey;
  final Value<String> schemaId;
  final Value<String> businessId;
  final Value<String> payloadJson;
  final Value<DateTime> updatedAt;
  final Value<int> rowid;
  const ContractDocumentsCompanion({
    this.docKey = const Value.absent(),
    this.schemaId = const Value.absent(),
    this.businessId = const Value.absent(),
    this.payloadJson = const Value.absent(),
    this.updatedAt = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  ContractDocumentsCompanion.insert({
    required String docKey,
    required String schemaId,
    this.businessId = const Value.absent(),
    required String payloadJson,
    required DateTime updatedAt,
    this.rowid = const Value.absent(),
  })  : docKey = Value(docKey),
        schemaId = Value(schemaId),
        payloadJson = Value(payloadJson),
        updatedAt = Value(updatedAt);
  static Insertable<ContractDocument> custom({
    Expression<String>? docKey,
    Expression<String>? schemaId,
    Expression<String>? businessId,
    Expression<String>? payloadJson,
    Expression<DateTime>? updatedAt,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (docKey != null) 'doc_key': docKey,
      if (schemaId != null) 'schema_id': schemaId,
      if (businessId != null) 'business_id': businessId,
      if (payloadJson != null) 'payload_json': payloadJson,
      if (updatedAt != null) 'updated_at': updatedAt,
      if (rowid != null) 'rowid': rowid,
    });
  }

  ContractDocumentsCompanion copyWith(
      {Value<String>? docKey,
      Value<String>? schemaId,
      Value<String>? businessId,
      Value<String>? payloadJson,
      Value<DateTime>? updatedAt,
      Value<int>? rowid}) {
    return ContractDocumentsCompanion(
      docKey: docKey ?? this.docKey,
      schemaId: schemaId ?? this.schemaId,
      businessId: businessId ?? this.businessId,
      payloadJson: payloadJson ?? this.payloadJson,
      updatedAt: updatedAt ?? this.updatedAt,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (docKey.present) {
      map['doc_key'] = Variable<String>(docKey.value);
    }
    if (schemaId.present) {
      map['schema_id'] = Variable<String>(schemaId.value);
    }
    if (businessId.present) {
      map['business_id'] = Variable<String>(businessId.value);
    }
    if (payloadJson.present) {
      map['payload_json'] = Variable<String>(payloadJson.value);
    }
    if (updatedAt.present) {
      map['updated_at'] = Variable<DateTime>(updatedAt.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('ContractDocumentsCompanion(')
          ..write('docKey: $docKey, ')
          ..write('schemaId: $schemaId, ')
          ..write('businessId: $businessId, ')
          ..write('payloadJson: $payloadJson, ')
          ..write('updatedAt: $updatedAt, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

class $AppMetaTable extends AppMeta with TableInfo<$AppMetaTable, AppMetaData> {
  @override
  final GeneratedDatabase attachedDatabase;
  final String? _alias;
  $AppMetaTable(this.attachedDatabase, [this._alias]);
  static const VerificationMeta _keyMeta = const VerificationMeta('key');
  @override
  late final GeneratedColumn<String> key = GeneratedColumn<String>(
      'key', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  static const VerificationMeta _valueMeta = const VerificationMeta('value');
  @override
  late final GeneratedColumn<String> value = GeneratedColumn<String>(
      'value', aliasedName, false,
      type: DriftSqlType.string, requiredDuringInsert: true);
  @override
  List<GeneratedColumn> get $columns => [key, value];
  @override
  String get aliasedName => _alias ?? actualTableName;
  @override
  String get actualTableName => $name;
  static const String $name = 'app_meta';
  @override
  VerificationContext validateIntegrity(Insertable<AppMetaData> instance,
      {bool isInserting = false}) {
    final context = VerificationContext();
    final data = instance.toColumns(true);
    if (data.containsKey('key')) {
      context.handle(
          _keyMeta, key.isAcceptableOrUnknown(data['key']!, _keyMeta));
    } else if (isInserting) {
      context.missing(_keyMeta);
    }
    if (data.containsKey('value')) {
      context.handle(
          _valueMeta, value.isAcceptableOrUnknown(data['value']!, _valueMeta));
    } else if (isInserting) {
      context.missing(_valueMeta);
    }
    return context;
  }

  @override
  Set<GeneratedColumn> get $primaryKey => {key};
  @override
  AppMetaData map(Map<String, dynamic> data, {String? tablePrefix}) {
    final effectivePrefix = tablePrefix != null ? '$tablePrefix.' : '';
    return AppMetaData(
      key: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}key'])!,
      value: attachedDatabase.typeMapping
          .read(DriftSqlType.string, data['${effectivePrefix}value'])!,
    );
  }

  @override
  $AppMetaTable createAlias(String alias) {
    return $AppMetaTable(attachedDatabase, alias);
  }
}

class AppMetaData extends DataClass implements Insertable<AppMetaData> {
  final String key;
  final String value;
  const AppMetaData({required this.key, required this.value});
  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    map['key'] = Variable<String>(key);
    map['value'] = Variable<String>(value);
    return map;
  }

  AppMetaCompanion toCompanion(bool nullToAbsent) {
    return AppMetaCompanion(
      key: Value(key),
      value: Value(value),
    );
  }

  factory AppMetaData.fromJson(Map<String, dynamic> json,
      {ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return AppMetaData(
      key: serializer.fromJson<String>(json['key']),
      value: serializer.fromJson<String>(json['value']),
    );
  }
  @override
  Map<String, dynamic> toJson({ValueSerializer? serializer}) {
    serializer ??= driftRuntimeOptions.defaultSerializer;
    return <String, dynamic>{
      'key': serializer.toJson<String>(key),
      'value': serializer.toJson<String>(value),
    };
  }

  AppMetaData copyWith({String? key, String? value}) => AppMetaData(
        key: key ?? this.key,
        value: value ?? this.value,
      );
  AppMetaData copyWithCompanion(AppMetaCompanion data) {
    return AppMetaData(
      key: data.key.present ? data.key.value : this.key,
      value: data.value.present ? data.value.value : this.value,
    );
  }

  @override
  String toString() {
    return (StringBuffer('AppMetaData(')
          ..write('key: $key, ')
          ..write('value: $value')
          ..write(')'))
        .toString();
  }

  @override
  int get hashCode => Object.hash(key, value);
  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is AppMetaData &&
          other.key == this.key &&
          other.value == this.value);
}

class AppMetaCompanion extends UpdateCompanion<AppMetaData> {
  final Value<String> key;
  final Value<String> value;
  final Value<int> rowid;
  const AppMetaCompanion({
    this.key = const Value.absent(),
    this.value = const Value.absent(),
    this.rowid = const Value.absent(),
  });
  AppMetaCompanion.insert({
    required String key,
    required String value,
    this.rowid = const Value.absent(),
  })  : key = Value(key),
        value = Value(value);
  static Insertable<AppMetaData> custom({
    Expression<String>? key,
    Expression<String>? value,
    Expression<int>? rowid,
  }) {
    return RawValuesInsertable({
      if (key != null) 'key': key,
      if (value != null) 'value': value,
      if (rowid != null) 'rowid': rowid,
    });
  }

  AppMetaCompanion copyWith(
      {Value<String>? key, Value<String>? value, Value<int>? rowid}) {
    return AppMetaCompanion(
      key: key ?? this.key,
      value: value ?? this.value,
      rowid: rowid ?? this.rowid,
    );
  }

  @override
  Map<String, Expression> toColumns(bool nullToAbsent) {
    final map = <String, Expression>{};
    if (key.present) {
      map['key'] = Variable<String>(key.value);
    }
    if (value.present) {
      map['value'] = Variable<String>(value.value);
    }
    if (rowid.present) {
      map['rowid'] = Variable<int>(rowid.value);
    }
    return map;
  }

  @override
  String toString() {
    return (StringBuffer('AppMetaCompanion(')
          ..write('key: $key, ')
          ..write('value: $value, ')
          ..write('rowid: $rowid')
          ..write(')'))
        .toString();
  }
}

abstract class _$AppDatabase extends GeneratedDatabase {
  _$AppDatabase(QueryExecutor e) : super(e);
  $AppDatabaseManager get managers => $AppDatabaseManager(this);
  late final $ContractDocumentsTable contractDocuments =
      $ContractDocumentsTable(this);
  late final $AppMetaTable appMeta = $AppMetaTable(this);
  @override
  Iterable<TableInfo<Table, Object?>> get allTables =>
      allSchemaEntities.whereType<TableInfo<Table, Object?>>();
  @override
  List<DatabaseSchemaEntity> get allSchemaEntities =>
      [contractDocuments, appMeta];
}

typedef $$ContractDocumentsTableCreateCompanionBuilder
    = ContractDocumentsCompanion Function({
  required String docKey,
  required String schemaId,
  Value<String> businessId,
  required String payloadJson,
  required DateTime updatedAt,
  Value<int> rowid,
});
typedef $$ContractDocumentsTableUpdateCompanionBuilder
    = ContractDocumentsCompanion Function({
  Value<String> docKey,
  Value<String> schemaId,
  Value<String> businessId,
  Value<String> payloadJson,
  Value<DateTime> updatedAt,
  Value<int> rowid,
});

class $$ContractDocumentsTableFilterComposer
    extends Composer<_$AppDatabase, $ContractDocumentsTable> {
  $$ContractDocumentsTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get docKey => $composableBuilder(
      column: $table.docKey, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get schemaId => $composableBuilder(
      column: $table.schemaId, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get businessId => $composableBuilder(
      column: $table.businessId, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get payloadJson => $composableBuilder(
      column: $table.payloadJson, builder: (column) => ColumnFilters(column));

  ColumnFilters<DateTime> get updatedAt => $composableBuilder(
      column: $table.updatedAt, builder: (column) => ColumnFilters(column));
}

class $$ContractDocumentsTableOrderingComposer
    extends Composer<_$AppDatabase, $ContractDocumentsTable> {
  $$ContractDocumentsTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get docKey => $composableBuilder(
      column: $table.docKey, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get schemaId => $composableBuilder(
      column: $table.schemaId, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get businessId => $composableBuilder(
      column: $table.businessId, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get payloadJson => $composableBuilder(
      column: $table.payloadJson, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<DateTime> get updatedAt => $composableBuilder(
      column: $table.updatedAt, builder: (column) => ColumnOrderings(column));
}

class $$ContractDocumentsTableAnnotationComposer
    extends Composer<_$AppDatabase, $ContractDocumentsTable> {
  $$ContractDocumentsTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get docKey =>
      $composableBuilder(column: $table.docKey, builder: (column) => column);

  GeneratedColumn<String> get schemaId =>
      $composableBuilder(column: $table.schemaId, builder: (column) => column);

  GeneratedColumn<String> get businessId => $composableBuilder(
      column: $table.businessId, builder: (column) => column);

  GeneratedColumn<String> get payloadJson => $composableBuilder(
      column: $table.payloadJson, builder: (column) => column);

  GeneratedColumn<DateTime> get updatedAt =>
      $composableBuilder(column: $table.updatedAt, builder: (column) => column);
}

class $$ContractDocumentsTableTableManager extends RootTableManager<
    _$AppDatabase,
    $ContractDocumentsTable,
    ContractDocument,
    $$ContractDocumentsTableFilterComposer,
    $$ContractDocumentsTableOrderingComposer,
    $$ContractDocumentsTableAnnotationComposer,
    $$ContractDocumentsTableCreateCompanionBuilder,
    $$ContractDocumentsTableUpdateCompanionBuilder,
    (
      ContractDocument,
      BaseReferences<_$AppDatabase, $ContractDocumentsTable, ContractDocument>
    ),
    ContractDocument,
    PrefetchHooks Function()> {
  $$ContractDocumentsTableTableManager(
      _$AppDatabase db, $ContractDocumentsTable table)
      : super(TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$ContractDocumentsTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$ContractDocumentsTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$ContractDocumentsTableAnnotationComposer(
                  $db: db, $table: table),
          updateCompanionCallback: ({
            Value<String> docKey = const Value.absent(),
            Value<String> schemaId = const Value.absent(),
            Value<String> businessId = const Value.absent(),
            Value<String> payloadJson = const Value.absent(),
            Value<DateTime> updatedAt = const Value.absent(),
            Value<int> rowid = const Value.absent(),
          }) =>
              ContractDocumentsCompanion(
            docKey: docKey,
            schemaId: schemaId,
            businessId: businessId,
            payloadJson: payloadJson,
            updatedAt: updatedAt,
            rowid: rowid,
          ),
          createCompanionCallback: ({
            required String docKey,
            required String schemaId,
            Value<String> businessId = const Value.absent(),
            required String payloadJson,
            required DateTime updatedAt,
            Value<int> rowid = const Value.absent(),
          }) =>
              ContractDocumentsCompanion.insert(
            docKey: docKey,
            schemaId: schemaId,
            businessId: businessId,
            payloadJson: payloadJson,
            updatedAt: updatedAt,
            rowid: rowid,
          ),
          withReferenceMapper: (p0) => p0
              .map((e) => (e.readTable(table), BaseReferences(db, table, e)))
              .toList(),
          prefetchHooksCallback: null,
        ));
}

typedef $$ContractDocumentsTableProcessedTableManager = ProcessedTableManager<
    _$AppDatabase,
    $ContractDocumentsTable,
    ContractDocument,
    $$ContractDocumentsTableFilterComposer,
    $$ContractDocumentsTableOrderingComposer,
    $$ContractDocumentsTableAnnotationComposer,
    $$ContractDocumentsTableCreateCompanionBuilder,
    $$ContractDocumentsTableUpdateCompanionBuilder,
    (
      ContractDocument,
      BaseReferences<_$AppDatabase, $ContractDocumentsTable, ContractDocument>
    ),
    ContractDocument,
    PrefetchHooks Function()>;
typedef $$AppMetaTableCreateCompanionBuilder = AppMetaCompanion Function({
  required String key,
  required String value,
  Value<int> rowid,
});
typedef $$AppMetaTableUpdateCompanionBuilder = AppMetaCompanion Function({
  Value<String> key,
  Value<String> value,
  Value<int> rowid,
});

class $$AppMetaTableFilterComposer
    extends Composer<_$AppDatabase, $AppMetaTable> {
  $$AppMetaTableFilterComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnFilters<String> get key => $composableBuilder(
      column: $table.key, builder: (column) => ColumnFilters(column));

  ColumnFilters<String> get value => $composableBuilder(
      column: $table.value, builder: (column) => ColumnFilters(column));
}

class $$AppMetaTableOrderingComposer
    extends Composer<_$AppDatabase, $AppMetaTable> {
  $$AppMetaTableOrderingComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  ColumnOrderings<String> get key => $composableBuilder(
      column: $table.key, builder: (column) => ColumnOrderings(column));

  ColumnOrderings<String> get value => $composableBuilder(
      column: $table.value, builder: (column) => ColumnOrderings(column));
}

class $$AppMetaTableAnnotationComposer
    extends Composer<_$AppDatabase, $AppMetaTable> {
  $$AppMetaTableAnnotationComposer({
    required super.$db,
    required super.$table,
    super.joinBuilder,
    super.$addJoinBuilderToRootComposer,
    super.$removeJoinBuilderFromRootComposer,
  });
  GeneratedColumn<String> get key =>
      $composableBuilder(column: $table.key, builder: (column) => column);

  GeneratedColumn<String> get value =>
      $composableBuilder(column: $table.value, builder: (column) => column);
}

class $$AppMetaTableTableManager extends RootTableManager<
    _$AppDatabase,
    $AppMetaTable,
    AppMetaData,
    $$AppMetaTableFilterComposer,
    $$AppMetaTableOrderingComposer,
    $$AppMetaTableAnnotationComposer,
    $$AppMetaTableCreateCompanionBuilder,
    $$AppMetaTableUpdateCompanionBuilder,
    (AppMetaData, BaseReferences<_$AppDatabase, $AppMetaTable, AppMetaData>),
    AppMetaData,
    PrefetchHooks Function()> {
  $$AppMetaTableTableManager(_$AppDatabase db, $AppMetaTable table)
      : super(TableManagerState(
          db: db,
          table: table,
          createFilteringComposer: () =>
              $$AppMetaTableFilterComposer($db: db, $table: table),
          createOrderingComposer: () =>
              $$AppMetaTableOrderingComposer($db: db, $table: table),
          createComputedFieldComposer: () =>
              $$AppMetaTableAnnotationComposer($db: db, $table: table),
          updateCompanionCallback: ({
            Value<String> key = const Value.absent(),
            Value<String> value = const Value.absent(),
            Value<int> rowid = const Value.absent(),
          }) =>
              AppMetaCompanion(
            key: key,
            value: value,
            rowid: rowid,
          ),
          createCompanionCallback: ({
            required String key,
            required String value,
            Value<int> rowid = const Value.absent(),
          }) =>
              AppMetaCompanion.insert(
            key: key,
            value: value,
            rowid: rowid,
          ),
          withReferenceMapper: (p0) => p0
              .map((e) => (e.readTable(table), BaseReferences(db, table, e)))
              .toList(),
          prefetchHooksCallback: null,
        ));
}

typedef $$AppMetaTableProcessedTableManager = ProcessedTableManager<
    _$AppDatabase,
    $AppMetaTable,
    AppMetaData,
    $$AppMetaTableFilterComposer,
    $$AppMetaTableOrderingComposer,
    $$AppMetaTableAnnotationComposer,
    $$AppMetaTableCreateCompanionBuilder,
    $$AppMetaTableUpdateCompanionBuilder,
    (AppMetaData, BaseReferences<_$AppDatabase, $AppMetaTable, AppMetaData>),
    AppMetaData,
    PrefetchHooks Function()>;

class $AppDatabaseManager {
  final _$AppDatabase _db;
  $AppDatabaseManager(this._db);
  $$ContractDocumentsTableTableManager get contractDocuments =>
      $$ContractDocumentsTableTableManager(_db, _db.contractDocuments);
  $$AppMetaTableTableManager get appMeta =>
      $$AppMetaTableTableManager(_db, _db.appMeta);
}
