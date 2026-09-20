import 'oauth_config.dart';
import 'pkce.dart';
import 'secure_token_store.dart';
import 'token_models.dart';
import 'deep_link_guard.dart';
import 'feature_flags.dart';

/// Performs authorization-code + PKCE via an injected [AuthBrowser].
/// Never embeds a WebView. System browser / ASWebAuthenticationSession only.
abstract class AuthBrowser {
  /// Open system auth session; return redirect URI or null if cancelled.
  Future<Uri?> authenticate({
    required Uri authorizationUrl,
    required String callbackUrlScheme,
  });
}

/// Exchange code / refresh / revoke against token endpoints.
abstract class TokenEndpointClient {
  Future<TokenSet> exchangeCode({
    required OAuthClientConfig config,
    required String code,
    required String codeVerifier,
  });

  Future<TokenSet> refresh({
    required OAuthClientConfig config,
    required String refreshToken,
  });

  Future<void> revoke({
    required OAuthClientConfig config,
    required String token,
  });
}

class NativeOAuthSession {
  NativeOAuthSession({
    required this.config,
    required this.store,
    required this.browser,
    required this.tokens,
    this.flags = MobileFeatureFlags.commercialSafe,
  });

  final OAuthClientConfig config;
  final SecureTokenStore store;
  final AuthBrowser browser;
  final TokenEndpointClient tokens;
  MobileFeatureFlags flags;

  String? _pendingState;
  String? _pendingVerifier;

  Future<AuthResult> login() async {
    if (!flags.oauthEnabled) {
      return const AuthResult(
        outcome: AuthOutcome.denied,
        message: 'oauth disabled by feature flag',
      );
    }
    final errors = config.validate();
    if (errors.isNotEmpty) {
      return AuthResult(
        outcome: AuthOutcome.invalidConfig,
        message: errors.join('; '),
      );
    }
    if (!await store.isSecureBackend) {
      return const AuthResult(
        outcome: AuthOutcome.denied,
        message: 'STOP: secure storage unavailable — no plaintext fallback',
      );
    }

    final pkce = PkcePair.generate();
    final state = generateOAuthState();
    _pendingState = state;
    _pendingVerifier = pkce.codeVerifier;

    final authUri = Uri.parse(config.authorizationEndpoint).replace(
      queryParameters: {
        'client_id': config.clientId,
        'redirect_uri': config.redirectUri,
        'response_type': 'code',
        'scope': config.effectiveScopes.join(' '),
        'state': state,
        'code_challenge': pkce.codeChallenge,
        'code_challenge_method': pkce.codeChallengeMethod,
      },
    );

    final scheme = Uri.parse(config.redirectUri).scheme;
    final redirect = await browser.authenticate(
      authorizationUrl: authUri,
      callbackUrlScheme: scheme,
    );
    if (redirect == null) {
      return const AuthResult(
        outcome: AuthOutcome.cancelled,
        message: 'user cancelled',
      );
    }
    return completeWithRedirect(redirect);
  }

  Future<AuthResult> completeWithRedirect(Uri redirect) async {
    if (!flags.deepLinksEnabled) {
      return const AuthResult(
        outcome: AuthOutcome.denied,
        message: 'deep links disabled',
      );
    }
    final guard = DeepLinkGuard(
      allowedRedirectUris: {config.redirectUri},
      expectedState: _pendingState ?? '',
    );
    final verdict = guard.validate(redirect);
    if (!verdict.accepted) {
      if (verdict.userCancelled) {
        return AuthResult(
          outcome: AuthOutcome.cancelled,
          message: verdict.reason,
        );
      }
      return AuthResult(
        outcome: AuthOutcome.tamperedRedirect,
        message: verdict.reason,
      );
    }
    try {
      final set = await tokens.exchangeCode(
        config: config,
        code: verdict.authorizationCode!,
        codeVerifier: _pendingVerifier ?? '',
      );
      await store.save(set);
      _pendingState = null;
      _pendingVerifier = null;
      return AuthResult(outcome: AuthOutcome.success, tokens: set);
    } catch (e) {
      return AuthResult(
        outcome: AuthOutcome.networkError,
        message: e.toString(),
      );
    }
  }

  Future<AuthResult> ensureFresh({bool offline = false}) async {
    final current = await store.read();
    if (current == null) {
      return const AuthResult(outcome: AuthOutcome.denied, message: 'no session');
    }
    if (!current.isExpired()) {
      return AuthResult(outcome: AuthOutcome.success, tokens: current);
    }
    if (offline) {
      return const AuthResult(
        outcome: AuthOutcome.offline,
        message: 'token expired while offline',
      );
    }
    if (!current.hasRefresh) {
      await store.clear();
      return const AuthResult(
        outcome: AuthOutcome.expired,
        message: 'expired without refresh token',
      );
    }
    try {
      final next = await tokens.refresh(
        config: config,
        refreshToken: current.refreshToken!,
      );
      await store.save(next);
      return AuthResult(outcome: AuthOutcome.success, tokens: next);
    } catch (e) {
      await store.clear();
      return AuthResult(outcome: AuthOutcome.revoked, message: e.toString());
    }
  }

  Future<AuthResult> revoke() async {
    final current = await store.read();
    await store.clear();
    if (current == null) {
      return const AuthResult(outcome: AuthOutcome.success, message: 'already clear');
    }
    try {
      final t = current.refreshToken ?? current.accessToken;
      await tokens.revoke(config: config, token: t);
      return const AuthResult(outcome: AuthOutcome.success, message: 'revoked');
    } catch (e) {
      // Local clear already done — remote revoke best-effort.
      return AuthResult(
        outcome: AuthOutcome.success,
        message: 'local cleared; remote revoke: $e',
      );
    }
  }

  Future<TokenSet?> currentTokens() => store.read();
}
