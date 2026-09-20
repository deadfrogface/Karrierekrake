/// One-shot migration: wipe any insecure legacy token locations, then mark done.
///
/// There is intentionally **no** plaintext read→secure copy path that keeps
/// operating on SharedPreferences. Insecure material is destroyed.
library;

import 'secure_token_store.dart';

typedef PlainMap = Map<String, String>;

class TokenStoreMigration {
  TokenStoreMigration({
    required this.secureStore,
    required this.readLegacyPlain,
    required this.clearLegacyPlain,
  });

  final SecureTokenStore secureStore;
  final Future<PlainMap> Function() readLegacyPlain;
  final Future<void> Function() clearLegacyPlain;

  bool migrated = false;

  /// Destroy insecure leftovers. Does not re-import tokens (force re-auth).
  Future<MigrationReport> migrateOnce() async {
    if (migrated) {
      return const MigrationReport(alreadyDone: true, wipedKeys: []);
    }
    if (!await secureStore.isSecureBackend) {
      throw StateError('STOP: secure backend unavailable — no plaintext fallback');
    }
    final legacy = await readLegacyPlain();
    final wiped = <String>[];
    for (final key in legacy.keys) {
      wiped.add(key);
    }
    if (legacy.isNotEmpty) {
      await clearLegacyPlain();
      // Also clear secure store if we cannot trust provenance.
      await secureStore.clear();
    }
    migrated = true;
    return MigrationReport(alreadyDone: false, wipedKeys: wiped);
  }
}

class MigrationReport {
  const MigrationReport({
    required this.alreadyDone,
    required this.wipedKeys,
  });

  final bool alreadyDone;
  final List<String> wipedKeys;
}
