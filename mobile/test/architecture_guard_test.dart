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
