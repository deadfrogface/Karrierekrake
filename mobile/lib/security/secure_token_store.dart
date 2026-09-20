import 'token_models.dart';

/// Abstraction over platform secure storage (Keystore / Keychain).
/// Implementations MUST NOT fall back to plaintext.
abstract class SecureTokenStore {
  Future<void> save(TokenSet tokens);
  Future<TokenSet?> read();
  Future<void> clear();
  Future<bool> get isSecureBackend;
}

/// In-memory store for unit tests — simulates secure enclave behavior.
class MemorySecureTokenStore implements SecureTokenStore {
  TokenSet? _tokens;
  bool backendSecure;

  MemorySecureTokenStore({this.backendSecure = true});

  @override
  Future<bool> get isSecureBackend async => backendSecure;

  @override
  Future<void> save(TokenSet tokens) async {
    if (!backendSecure) {
      throw StateError('STOP: refuse plaintext token fallback');
    }
    if (tokens.accessToken.isEmpty) {
      throw ArgumentError('access_token required');
    }
    _tokens = tokens;
  }

  @override
  Future<TokenSet?> read() async => _tokens;

  @override
  Future<void> clear() async {
    _tokens = null;
  }
}

/// Keys used with flutter_secure_storage on device.
class SecureStorageKeys {
  static const tokenBlob = 'kk_oauth_token_v1';
  static const storeVersion = 'kk_oauth_store_version';
  static const currentVersion = '1';
  /// Legacy insecure markers — wiped on migrate.
  static const legacyPlainPrefs = 'kk_oauth_token_plain_DO_NOT_USE';
}
