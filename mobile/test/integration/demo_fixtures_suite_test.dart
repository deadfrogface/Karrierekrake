import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/contracts/contracts.dart';

Map<String, dynamic> _load(String name) {
  final f = File('assets/demo/$name');
  return jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
}

void main() {
  test('fixture job_000.json parses', () {
    final json = _load('job_000.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_001.json parses', () {
    final json = _load('job_001.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_002.json parses', () {
    final json = _load('job_002.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_003.json parses', () {
    final json = _load('job_003.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_004.json parses', () {
    final json = _load('job_004.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_005.json parses', () {
    final json = _load('job_005.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_006.json parses', () {
    final json = _load('job_006.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_007.json parses', () {
    final json = _load('job_007.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_008.json parses', () {
    final json = _load('job_008.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_009.json parses', () {
    final json = _load('job_009.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_010.json parses', () {
    final json = _load('job_010.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_011.json parses', () {
    final json = _load('job_011.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_012.json parses', () {
    final json = _load('job_012.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_013.json parses', () {
    final json = _load('job_013.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_014.json parses', () {
    final json = _load('job_014.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_015.json parses', () {
    final json = _load('job_015.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_016.json parses', () {
    final json = _load('job_016.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_017.json parses', () {
    final json = _load('job_017.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_018.json parses', () {
    final json = _load('job_018.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_019.json parses', () {
    final json = _load('job_019.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_020.json parses', () {
    final json = _load('job_020.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_021.json parses', () {
    final json = _load('job_021.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_022.json parses', () {
    final json = _load('job_022.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_023.json parses', () {
    final json = _load('job_023.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_024.json parses', () {
    final json = _load('job_024.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_025.json parses', () {
    final json = _load('job_025.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_026.json parses', () {
    final json = _load('job_026.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_027.json parses', () {
    final json = _load('job_027.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_028.json parses', () {
    final json = _load('job_028.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_029.json parses', () {
    final json = _load('job_029.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_030.json parses', () {
    final json = _load('job_030.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_031.json parses', () {
    final json = _load('job_031.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_032.json parses', () {
    final json = _load('job_032.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_033.json parses', () {
    final json = _load('job_033.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_034.json parses', () {
    final json = _load('job_034.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_035.json parses', () {
    final json = _load('job_035.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_036.json parses', () {
    final json = _load('job_036.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_037.json parses', () {
    final json = _load('job_037.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_038.json parses', () {
    final json = _load('job_038.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture job_039.json parses', () {
    final json = _load('job_039.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_000.json parses', () {
    final json = _load('case_000.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_001.json parses', () {
    final json = _load('case_001.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_002.json parses', () {
    final json = _load('case_002.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_003.json parses', () {
    final json = _load('case_003.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_004.json parses', () {
    final json = _load('case_004.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_005.json parses', () {
    final json = _load('case_005.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_006.json parses', () {
    final json = _load('case_006.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_007.json parses', () {
    final json = _load('case_007.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_008.json parses', () {
    final json = _load('case_008.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_009.json parses', () {
    final json = _load('case_009.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_010.json parses', () {
    final json = _load('case_010.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_011.json parses', () {
    final json = _load('case_011.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_012.json parses', () {
    final json = _load('case_012.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_013.json parses', () {
    final json = _load('case_013.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_014.json parses', () {
    final json = _load('case_014.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_015.json parses', () {
    final json = _load('case_015.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_016.json parses', () {
    final json = _load('case_016.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_017.json parses', () {
    final json = _load('case_017.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_018.json parses', () {
    final json = _load('case_018.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture case_019.json parses', () {
    final json = _load('case_019.json');
    final dto = ApplicationCaseDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_000.json parses', () {
    final json = _load('event_000.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_001.json parses', () {
    final json = _load('event_001.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_002.json parses', () {
    final json = _load('event_002.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_003.json parses', () {
    final json = _load('event_003.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_004.json parses', () {
    final json = _load('event_004.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_005.json parses', () {
    final json = _load('event_005.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_006.json parses', () {
    final json = _load('event_006.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_007.json parses', () {
    final json = _load('event_007.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_008.json parses', () {
    final json = _load('event_008.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_009.json parses', () {
    final json = _load('event_009.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_010.json parses', () {
    final json = _load('event_010.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_011.json parses', () {
    final json = _load('event_011.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_012.json parses', () {
    final json = _load('event_012.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_013.json parses', () {
    final json = _load('event_013.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_014.json parses', () {
    final json = _load('event_014.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_015.json parses', () {
    final json = _load('event_015.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_016.json parses', () {
    final json = _load('event_016.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_017.json parses', () {
    final json = _load('event_017.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_018.json parses', () {
    final json = _load('event_018.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_019.json parses', () {
    final json = _load('event_019.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_020.json parses', () {
    final json = _load('event_020.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_021.json parses', () {
    final json = _load('event_021.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_022.json parses', () {
    final json = _load('event_022.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_023.json parses', () {
    final json = _load('event_023.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_024.json parses', () {
    final json = _load('event_024.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_025.json parses', () {
    final json = _load('event_025.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_026.json parses', () {
    final json = _load('event_026.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_027.json parses', () {
    final json = _load('event_027.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_028.json parses', () {
    final json = _load('event_028.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture event_029.json parses', () {
    final json = _load('event_029.json');
    final dto = LifecycleEventDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_000.json parses', () {
    final json = _load('draft_000.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_001.json parses', () {
    final json = _load('draft_001.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_002.json parses', () {
    final json = _load('draft_002.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_003.json parses', () {
    final json = _load('draft_003.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_004.json parses', () {
    final json = _load('draft_004.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_005.json parses', () {
    final json = _load('draft_005.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_006.json parses', () {
    final json = _load('draft_006.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_007.json parses', () {
    final json = _load('draft_007.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_008.json parses', () {
    final json = _load('draft_008.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_009.json parses', () {
    final json = _load('draft_009.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_010.json parses', () {
    final json = _load('draft_010.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_011.json parses', () {
    final json = _load('draft_011.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_012.json parses', () {
    final json = _load('draft_012.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_013.json parses', () {
    final json = _load('draft_013.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture draft_014.json parses', () {
    final json = _load('draft_014.json');
    final dto = ReplyDraftDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_000.json parses', () {
    final json = _load('cal_000.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_001.json parses', () {
    final json = _load('cal_001.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_002.json parses', () {
    final json = _load('cal_002.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_003.json parses', () {
    final json = _load('cal_003.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_004.json parses', () {
    final json = _load('cal_004.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_005.json parses', () {
    final json = _load('cal_005.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_006.json parses', () {
    final json = _load('cal_006.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_007.json parses', () {
    final json = _load('cal_007.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_008.json parses', () {
    final json = _load('cal_008.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture cal_009.json parses', () {
    final json = _load('cal_009.json');
    final dto = CalendarProposalDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_000.json parses', () {
    final json = _load('profile_000.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_001.json parses', () {
    final json = _load('profile_001.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_002.json parses', () {
    final json = _load('profile_002.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_003.json parses', () {
    final json = _load('profile_003.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_004.json parses', () {
    final json = _load('profile_004.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_005.json parses', () {
    final json = _load('profile_005.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_006.json parses', () {
    final json = _load('profile_006.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture profile_007.json parses', () {
    final json = _load('profile_007.json');
    final dto = ProfileDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_000.json parses', () {
    final json = _load('intent_000.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_001.json parses', () {
    final json = _load('intent_001.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_002.json parses', () {
    final json = _load('intent_002.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_003.json parses', () {
    final json = _load('intent_003.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_004.json parses', () {
    final json = _load('intent_004.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_005.json parses', () {
    final json = _load('intent_005.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_006.json parses', () {
    final json = _load('intent_006.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture intent_007.json parses', () {
    final json = _load('intent_007.json');
    final dto = SearchIntentDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_000.json parses', () {
    final json = _load('guenther_000.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_001.json parses', () {
    final json = _load('guenther_001.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_002.json parses', () {
    final json = _load('guenther_002.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_003.json parses', () {
    final json = _load('guenther_003.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_004.json parses', () {
    final json = _load('guenther_004.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_005.json parses', () {
    final json = _load('guenther_005.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_006.json parses', () {
    final json = _load('guenther_006.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture guenther_007.json parses', () {
    final json = _load('guenther_007.json');
    final dto = GuentherResultDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture edge_000.json parses', () {
    final json = _load('edge_000.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture edge_001.json parses', () {
    final json = _load('edge_001.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture edge_002.json parses', () {
    final json = _load('edge_002.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture edge_003.json parses', () {
    final json = _load('edge_003.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

  test('fixture edge_004.json parses', () {
    final json = _load('edge_004.json');
    final dto = JobDto.fromJson(json);
    expect(dto.envelope.contractVersion.startsWith('1.'), isTrue);
    expect(kKnownSchemaIds.contains(dto.envelope.schemaId), isTrue);
  });

}
