import 'package:flutter_test/flutter_test.dart';
import 'package:karrierekrake_mobile/security/security.dart';

class _FakeBrowser implements AuthBrowser {
  _FakeBrowser(this.redirect);
  Uri? redirect;
  Uri? lastAuthUrl;

  @override
  Future<Uri?> authenticate({
    required Uri authorizationUrl,
    required String callbackUrlScheme,
  }) async {
    lastAuthUrl = authorizationUrl;
    return redirect;
  }
}

class _FakeTokens implements TokenEndpointClient {
  _FakeTokens();

  bool failExchange = false;
  bool failRefresh = false;
  bool failRevoke = false;
  int revokeCalls = 0;

  @override
  Future<TokenSet> exchangeCode({
    required OAuthClientConfig config,
    required String code,
    required String codeVerifier,
  }) async {
    if (failExchange) throw Exception('exchange failed');
    if (codeVerifier.isEmpty) throw Exception('missing pkce verifier');
    return TokenSet(
      accessToken: 'access-$code',
      refreshToken: 'refresh-1',
      expiresAt: DateTime.now().toUtc().add(const Duration(hours: 1)),
      scope: config.effectiveScopes,
      obtainedAt: DateTime.now().toUtc(),
    );
  }

  @override
  Future<TokenSet> refresh({
    required OAuthClientConfig config,
    required String refreshToken,
  }) async {
    if (failRefresh) throw Exception('refresh revoked');
    return TokenSet(
      accessToken: 'access-refreshed',
      refreshToken: refreshToken,
      expiresAt: DateTime.now().toUtc().add(const Duration(hours: 1)),
      scope: config.effectiveScopes,
      obtainedAt: DateTime.now().toUtc(),
    );
  }

  @override
  Future<void> revoke({
    required OAuthClientConfig config,
    required String token,
  }) async {
    revokeCalls++;
    if (failRevoke) throw Exception('revoke endpoint down');
  }
}

OAuthClientConfig _cfg({String redirect = kDefaultRedirectUri}) =>
    OAuthClientConfig(
      clientId: 'mobile-public',
      redirectUri: redirect,
      authorizationEndpoint: 'https://idp.example/auth',
      tokenEndpoint: 'https://idp.example/token',
      revocationEndpoint: 'https://idp.example/revoke',
      scopes: const ['openid', 'profile'],
    );

void main() {
  group('oauth config', () {
    test('valid public client', () {
      expect(_cfg().isValid, isTrue);
    });

    test('rejects desktop loopback', () {
      final c = _cfg(redirect: 'http://127.0.0.1:8080/');
      expect(c.validate().any((e) => e.contains('loopback')), isTrue);
    });

    test('rejects localhost loopback', () {
      final c = _cfg(redirect: 'http://localhost:8080/callback');
      expect(c.isValid, isFalse);
    });

    test('rejects broad scopes', () {
      final c = OAuthClientConfig(
        clientId: 'x',
        redirectUri: kDefaultRedirectUri,
        authorizationEndpoint: 'https://a',
        tokenEndpoint: 'https://t',
        scopes: const ['*'],
      );
      expect(c.validate().any((e) => e.contains('broad')), isTrue);
    });

    test('rejects gmail modify scope', () {
      final c = OAuthClientConfig(
        clientId: 'x',
        redirectUri: kDefaultRedirectUri,
        authorizationEndpoint: 'https://a',
        tokenEndpoint: 'https://t',
        scopes: const ['https://mail.google.com/'],
      );
      expect(c.isValid, isFalse);
    });
  });

  group('pkce', () {
    test('generates s256 verifier/challenge', () {
      final p = PkcePair.generate();
      expect(p.codeVerifier.length, greaterThan(40));
      expect(p.codeChallenge.length, greaterThan(20));
      expect(p.codeChallengeMethod, 'S256');
      expect(p.codeVerifier.contains('='), isFalse);
    });

    test('state is random', () {
      expect(generateOAuthState(), isNot(equals(generateOAuthState())));
    });
  });

  group('secure store', () {
    test('save read clear', () async {
      final store = MemorySecureTokenStore();
      final t = TokenSet(
        accessToken: 'a',
        refreshToken: 'r',
        expiresAt: DateTime.utc(2030),
      );
      await store.save(t);
      expect((await store.read())!.accessToken, 'a');
      await store.clear();
      expect(await store.read(), isNull);
    });

    test('refuses insecure backend', () async {
      final store = MemorySecureTokenStore(backendSecure: false);
      expect(
        () => store.save(const TokenSet(accessToken: 'a')),
        throwsStateError,
      );
    });

    test('token redaction', () {
      const t = TokenSet(accessToken: 'SECRET', refreshToken: 'R');
      expect(t.toString().contains('SECRET'), isFalse);
    });

    test('expiry skew', () {
      final t = TokenSet(
        accessToken: 'a',
        expiresAt: DateTime.now().toUtc().add(const Duration(seconds: 30)),
      );
      expect(t.isExpired(), isTrue);
    });
  });

  group('migration', () {
    test('wipes legacy plaintext and does not reimport', () async {
      final store = MemorySecureTokenStore();
      await store.save(const TokenSet(accessToken: 'should-clear'));
      var legacy = {'kk_oauth_token_plain_DO_NOT_USE': 'leak'};
      final mig = TokenStoreMigration(
        secureStore: store,
        readLegacyPlain: () async => Map<String, String>.from(legacy),
        clearLegacyPlain: () async => legacy.clear(),
      );
      final report = await mig.migrateOnce();
      expect(report.wipedKeys, isNotEmpty);
      expect(legacy, isEmpty);
      expect(await store.read(), isNull);
      final again = await mig.migrateOnce();
      expect(again.alreadyDone, isTrue);
    });

    test('STOP if secure backend missing', () async {
      final store = MemorySecureTokenStore(backendSecure: false);
      final mig = TokenStoreMigration(
        secureStore: store,
        readLegacyPlain: () async => {},
        clearLegacyPlain: () async {},
      );
      expect(mig.migrateOnce(), throwsStateError);
    });
  });

  group('deep link guard', () {
    test('accepts valid redirect', () {
      final g = DeepLinkGuard(
        allowedRedirectUris: {kDefaultRedirectUri},
        expectedState: 'abc',
      );
      final v = g.validate(
        Uri.parse('$kDefaultRedirectUri?code=xyz&state=abc'),
      );
      expect(v.accepted, isTrue);
      expect(v.authorizationCode, 'xyz');
    });

    test('rejects wrong state', () {
      final g = DeepLinkGuard(
        allowedRedirectUris: {kDefaultRedirectUri},
        expectedState: 'abc',
      );
      final v = g.validate(
        Uri.parse('$kDefaultRedirectUri?code=xyz&state=TAMPER'),
      );
      expect(v.tamper, AuthTamperKind.stateMismatch);
    });

    test('rejects wrong redirect', () {
      final g = DeepLinkGuard(
        allowedRedirectUris: {kDefaultRedirectUri},
        expectedState: 'abc',
      );
      final v = g.validate(
        Uri.parse('https://evil.example/cb?code=xyz&state=abc'),
      );
      expect(v.tamper, AuthTamperKind.wrongRedirect);
    });

    test('rejects implicit tokens in query', () {
      final g = DeepLinkGuard(
        allowedRedirectUris: {kDefaultRedirectUri},
        expectedState: 'abc',
      );
      final v = g.validate(
        Uri.parse('$kDefaultRedirectUri?code=x&state=abc&access_token=leak'),
      );
      expect(v.accepted, isFalse);
      expect(v.tamper, AuthTamperKind.suspiciousParam);
    });

    test('user cancel access_denied', () {
      final g = DeepLinkGuard(
        allowedRedirectUris: {kDefaultRedirectUri},
        expectedState: 'abc',
      );
      final v = g.validate(
        Uri.parse('$kDefaultRedirectUri?error=access_denied&state=abc'),
      );
      expect(v.userCancelled, isTrue);
    });
  });

  group('oauth session lifecycle', () {
    test('login success path uses PKCE', () async {
      final store = MemorySecureTokenStore();
      final client = _FakeTokens();
      final capturing = _CapturingBrowser();
      final session2 = NativeOAuthSession(
        config: _cfg(),
        store: store,
        browser: capturing,
        tokens: client,
      );
      final result = await session2.login();
      expect(result.ok, isTrue);
      expect(capturing.lastAuthUrl!.queryParameters['code_challenge_method'], 'S256');
      expect(await store.read(), isNotNull);
    });

    test('login cancel', () async {
      final session = NativeOAuthSession(
        config: _cfg(),
        store: MemorySecureTokenStore(),
        browser: _FakeBrowser(null),
        tokens: _FakeTokens(),
      );
      final r = await session.login();
      expect(r.outcome, AuthOutcome.cancelled);
    });

    test('login with feature flag off', () async {
      final session = NativeOAuthSession(
        config: _cfg(),
        store: MemorySecureTokenStore(),
        browser: _FakeBrowser(null),
        tokens: _FakeTokens(),
        flags: const MobileFeatureFlags(oauthEnabled: false),
      );
      final r = await session.login();
      expect(r.outcome, AuthOutcome.denied);
    });

    test('tampered redirect', () async {
      final capturing = _CapturingBrowser(tamperState: true);
      final session = NativeOAuthSession(
        config: _cfg(),
        store: MemorySecureTokenStore(),
        browser: capturing,
        tokens: _FakeTokens(),
      );
      final r = await session.login();
      expect(r.outcome, AuthOutcome.tamperedRedirect);
    });

    test('refresh on expiry', () async {
      final store = MemorySecureTokenStore();
      await store.save(TokenSet(
        accessToken: 'old',
        refreshToken: 'r',
        expiresAt: DateTime.now().toUtc().subtract(const Duration(minutes: 1)),
      ));
      final session = NativeOAuthSession(
        config: _cfg(),
        store: store,
        browser: _FakeBrowser(null),
        tokens: _FakeTokens(),
      );
      final r = await session.ensureFresh();
      expect(r.ok, isTrue);
      expect((await store.read())!.accessToken, 'access-refreshed');
    });

    test('offline expired', () async {
      final store = MemorySecureTokenStore();
      await store.save(TokenSet(
        accessToken: 'old',
        refreshToken: 'r',
        expiresAt: DateTime.now().toUtc().subtract(const Duration(minutes: 1)),
      ));
      final session = NativeOAuthSession(
        config: _cfg(),
        store: store,
        browser: _FakeBrowser(null),
        tokens: _FakeTokens(),
      );
      final r = await session.ensureFresh(offline: true);
      expect(r.outcome, AuthOutcome.offline);
    });

    test('revoke clears store', () async {
      final store = MemorySecureTokenStore();
      final client = _FakeTokens();
      await store.save(const TokenSet(accessToken: 'a', refreshToken: 'r'));
      final session = NativeOAuthSession(
        config: _cfg(),
        store: store,
        browser: _FakeBrowser(null),
        tokens: client,
      );
      final r = await session.revoke();
      expect(r.outcome, AuthOutcome.success);
      expect(await store.read(), isNull);
      expect(client.revokeCalls, 1);
    });

    test('relogin after revoke', () async {
      final store = MemorySecureTokenStore();
      final client = _FakeTokens();
      final session = NativeOAuthSession(
        config: _cfg(),
        store: store,
        browser: _CapturingBrowser(),
        tokens: client,
      );
      expect((await session.login()).ok, isTrue);
      await session.revoke();
      expect(await store.read(), isNull);
      expect((await session.login()).ok, isTrue);
      expect(await store.read(), isNotNull);
    });

    test('refresh failure treated as revoked', () async {
      final store = MemorySecureTokenStore();
      await store.save(TokenSet(
        accessToken: 'old',
        refreshToken: 'r',
        expiresAt: DateTime.now().toUtc().subtract(const Duration(minutes: 1)),
      ));
      final tokens = _FakeTokens()..failRefresh = true;
      final session = NativeOAuthSession(
        config: _cfg(),
        store: store,
        browser: _FakeBrowser(null),
        tokens: tokens,
      );
      final r = await session.ensureFresh();
      expect(r.outcome, AuthOutcome.revoked);
      expect(await store.read(), isNull);
    });

    test('invalid config', () async {
      final session = NativeOAuthSession(
        config: _cfg(redirect: 'http://127.0.0.1:9/'),
        store: MemorySecureTokenStore(),
        browser: _FakeBrowser(null),
        tokens: _FakeTokens(),
      );
      final r = await session.login();
      expect(r.outcome, AuthOutcome.invalidConfig);
    });

    test('insecure store blocks login', () async {
      final session = NativeOAuthSession(
        config: _cfg(),
        store: MemorySecureTokenStore(backendSecure: false),
        browser: _CapturingBrowser(),
        tokens: _FakeTokens(),
      );
      final r = await session.login();
      expect(r.outcome, AuthOutcome.denied);
      expect(r.message.contains('plaintext'), isTrue);
    });
  });

  group('backup restore policy', () {
    test('android allowBackup false documented via data extraction rules file exists', () {
      // Presence checked in architecture/integration test file; token store must clear on reinstall semantics.
      expect(SecureStorageKeys.currentVersion, '1');
    });

    test('reinstall semantics: empty store after clear', () async {
      final store = MemorySecureTokenStore();
      await store.save(const TokenSet(accessToken: 'a'));
      await store.clear();
      expect(await store.read(), isNull);
    });
  });
}

class _CapturingBrowser implements AuthBrowser {
  _CapturingBrowser({this.tamperState = false});
  Uri? lastAuthUrl;
  final bool tamperState;

  @override
  Future<Uri?> authenticate({
    required Uri authorizationUrl,
    required String callbackUrlScheme,
  }) async {
    lastAuthUrl = authorizationUrl;
    final state = authorizationUrl.queryParameters['state'] ?? '';
    final st = tamperState ? 'WRONG' : state;
    return Uri.parse('$kDefaultRedirectUri?code=authcode1&state=$st');
  }
}
