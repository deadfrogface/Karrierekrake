import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'secure_token_store.dart';
import 'token_models.dart';

/// Production store backed by [FlutterSecureStorage].
/// Refuses to operate if asked to use a non-secure backend.
class FlutterSecureTokenStore implements SecureTokenStore {
  FlutterSecureTokenStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions: IOSOptions(
                accessibility: KeychainAccessibility.first_unlock_this_device,
              ),
            );

  final FlutterSecureStorage _storage;

  @override
  Future<bool> get isSecureBackend async => true;

  @override
  Future<void> save(TokenSet tokens) async {
    if (tokens.accessToken.isEmpty) {
      throw ArgumentError('access_token required');
    }
    await _storage.write(
      key: SecureStorageKeys.tokenBlob,
      value: tokens.encode(),
    );
    await _storage.write(
      key: SecureStorageKeys.storeVersion,
      value: SecureStorageKeys.currentVersion,
    );
  }

  @override
  Future<TokenSet?> read() async {
    final raw = await _storage.read(key: SecureStorageKeys.tokenBlob);
    if (raw == null || raw.isEmpty) return null;
    return TokenSet.decode(raw);
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: SecureStorageKeys.tokenBlob);
    await _storage.delete(key: SecureStorageKeys.legacyPlainPrefs);
  }
}
