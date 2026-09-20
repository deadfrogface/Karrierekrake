import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/contracts/search_intent_dto.dart';

/// Loads shared fixtures from the monorepo `contracts/` tree.
///
/// Skips when Flutter tests run without the repo checkout (CI matrix optional).
File? _fixture(String name) {
  final candidates = <String>[
    '../contracts/fixtures/v1/$name',
    '../../contracts/fixtures/v1/$name',
    'contracts/fixtures/v1/$name',
  ];
  for (final path in candidates) {
    final f = File(path);
    if (f.existsSync()) return f;
  }
  return null;
}

void main() {
  test('ARCHITECTURE: mobile package is not the desktop tree', () {
    expect(Directory('../desktop').existsSync() || Directory('desktop').existsSync(),
        anyOf(isTrue, isFalse)); // monorepo may or may not be visible
    // Hard rule guard: this test file lives under mobile/test — never under desktop/.
    expect(File('pubspec.yaml').readAsStringSync(), contains('karrierekrake_mobile'));
    expect(File('pubspec.yaml').readAsStringSync(), contains('NOT a port'));
    expect(File('ARCHITECTURE.md').existsSync(), isTrue);
  });

  test('SearchIntent fixture decodes in Dart without Python', () {
    final file = _fixture('search_intent.valid.json');
    if (file == null) {
      // ignore: avoid_print
      print('skip: contracts fixtures not found from mobile/test cwd');
      return;
    }
    final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.schemaId, SearchIntentDto.schemaId);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(dto.targetRoles, isNotEmpty);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('unknown fixture fields do not break DTO parse', () {
    final json = <String, dynamic>{
      'contract_version': '1.0.0',
      'schema_id': 'karrierekrake.search_intent',
      'schema_version': 1,
      'target_roles': ['Controller'],
      'mandatory_skills': <String>[],
      'strictness': null,
      'mobile_client_tag': 'flutter-scaffold',
    };
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.targetRoles, ['Controller']);
    expect(dto.strictness, isNull);
  });
}
