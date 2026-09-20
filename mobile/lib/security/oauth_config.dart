/// OAuth client configuration for **installed** Android/iOS apps.
///
/// Public client + PKCE. Any `clientSecret` value must NEVER be treated as
/// confidential (it ships inside the binary). Prefer empty secret.
library;

class OAuthClientConfig {
  const OAuthClientConfig({
    required this.clientId,
    required this.redirectUri,
    required this.authorizationEndpoint,
    required this.tokenEndpoint,
    this.revocationEndpoint,
    this.clientSecret = '',
    this.scopes = const ['openid', 'profile', 'email'],
    this.additionalScopes = const [],
    this.discoveryDocumentUrl,
    this.allowHttpLoopback = false,
  });

  final String clientId;
  /// Custom scheme or https App Link / Universal Link — never desktop loopback.
  final String redirectUri;
  final String authorizationEndpoint;
  final String tokenEndpoint;
  final String? revocationEndpoint;
  /// Present only if IdP requires it for public clients — not a secret.
  final String clientSecret;
  final List<String> scopes;
  final List<String> additionalScopes;
  final String? discoveryDocumentUrl;
  /// Desktop-style http://127.0.0.1 loopback is forbidden on mobile.
  final bool allowHttpLoopback;

  List<String> get effectiveScopes => [...scopes, ...additionalScopes];

  /// Validate config before starting auth — fail closed.
  List<String> validate() {
    final errors = <String>[];
    if (clientId.trim().isEmpty) {
      errors.add('client_id required');
    }
    if (redirectUri.trim().isEmpty) {
      errors.add('redirect_uri required');
    }
    final uri = Uri.tryParse(redirectUri);
    if (uri == null) {
      errors.add('redirect_uri invalid');
    } else {
      if (uri.scheme == 'http' &&
          (uri.host == '127.0.0.1' ||
              uri.host == 'localhost' ||
              uri.host == '::1')) {
        if (!allowHttpLoopback) {
          errors.add(
            'desktop loopback redirect forbidden on mobile (use app scheme / App Links)',
          );
        }
      }
      if (uri.scheme == 'http' && !allowHttpLoopback) {
        errors.add('http redirect_uri forbidden (use https App Link or custom scheme)');
      }
    }
    if (authorizationEndpoint.trim().isEmpty ||
        tokenEndpoint.trim().isEmpty) {
      errors.add('authorization/token endpoints required');
    }
    if (effectiveScopes.contains('*') || effectiveScopes.contains('all')) {
      errors.add('broad scope forbidden');
    }
    // Refuse Gmail full-mailbox style scopes on companion by default.
    for (final s in effectiveScopes) {
      if (s.contains('mail.google.com') || s.contains('gmail.modify')) {
        errors.add('broad mail scope forbidden on companion: $s');
      }
    }
    return errors;
  }

  bool get isValid => validate().isEmpty;
}

/// Default redirect for Karrierekrake companion (register with IdP).
const kDefaultRedirectUri = 'de.karrierekrake.mobile://oauth2redirect';

/// Placeholder public-client config — replace endpoints after IdP approval.
/// Does not invent a sync backend; auth can target any OIDC provider.
const kPlaceholderOAuthConfig = OAuthClientConfig(
  clientId: 'karrierekrake-mobile-public',
  redirectUri: kDefaultRedirectUri,
  authorizationEndpoint: 'https://accounts.example.com/o/oauth2/v2/auth',
  tokenEndpoint: 'https://oauth2.example.com/token',
  revocationEndpoint: 'https://oauth2.example.com/revoke',
  scopes: ['openid', 'profile', 'email'],
);
