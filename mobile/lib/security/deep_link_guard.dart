/// Deep-link / App-Link hardening for OAuth redirects.
library;

class DeepLinkGuard {
  DeepLinkGuard({
    required this.allowedRedirectUris,
    required this.expectedState,
  });

  final Set<String> allowedRedirectUris;
  final String expectedState;

  DeepLinkVerdict validate(Uri incoming) {
    final normalized = _normalize(incoming);
    final allowed = allowedRedirectUris.map(_normalizeUriString).toSet();
    if (!allowed.contains(normalized)) {
      return DeepLinkVerdict.rejected(
        'redirect_uri not in allowlist',
        AuthTamperKind.wrongRedirect,
      );
    }
    final state = incoming.queryParameters['state'] ?? '';
    if (state.isEmpty || state != expectedState) {
      return DeepLinkVerdict.rejected(
        'state mismatch / missing',
        AuthTamperKind.stateMismatch,
      );
    }
    if (incoming.queryParameters.containsKey('error')) {
      final err = incoming.queryParameters['error'] ?? 'denied';
      if (err == 'access_denied') {
        return const DeepLinkVerdict(
          accepted: false,
          reason: 'user denied',
          tamper: AuthTamperKind.none,
          userCancelled: true,
        );
      }
      return DeepLinkVerdict.rejected(err, AuthTamperKind.none);
    }
    final code = incoming.queryParameters['code'];
    if (code == null || code.isEmpty) {
      return DeepLinkVerdict.rejected(
        'missing authorization code',
        AuthTamperKind.missingCode,
      );
    }
    // Reject unexpected query junk that looks like injection.
    for (final key in incoming.queryParameters.keys) {
      if (_dangerousParam(key)) {
        return DeepLinkVerdict.rejected(
          'suspicious query param: $key',
          AuthTamperKind.suspiciousParam,
        );
      }
    }
    return DeepLinkVerdict(
      accepted: true,
      reason: 'ok',
      authorizationCode: code,
    );
  }

  static bool _dangerousParam(String key) {
    final k = key.toLowerCase();
    return k.contains('<') ||
        k.contains('javascript') ||
        k == 'access_token' || // implicit flow forbidden
        k == 'id_token';
  }

  static String _normalize(Uri uri) {
    // Compare scheme + host + path only (ignore query for allowlist).
    return _normalizeUriString(
      uri.replace(query: '', fragment: '').toString(),
    );
  }

  static String _normalizeUriString(String raw) {
    final u = Uri.parse(raw.trim());
    final path = (u.path.isEmpty || u.path == '/') ? '' : u.path;
    if (u.host.isNotEmpty) {
      return '${u.scheme}://${u.host}$path'.toLowerCase();
    }
    // scheme:/path form
    final p = u.path.isEmpty ? '/' : u.path;
    return '${u.scheme}:$p'.toLowerCase();
  }
}

enum AuthTamperKind {
  none,
  wrongRedirect,
  stateMismatch,
  missingCode,
  suspiciousParam,
}

class DeepLinkVerdict {
  const DeepLinkVerdict({
    required this.accepted,
    required this.reason,
    this.authorizationCode,
    this.tamper = AuthTamperKind.none,
    this.userCancelled = false,
  });

  factory DeepLinkVerdict.rejected(String reason, AuthTamperKind tamper) =>
      DeepLinkVerdict(accepted: false, reason: reason, tamper: tamper);

  final bool accepted;
  final String reason;
  final String? authorizationCode;
  final AuthTamperKind tamper;
  final bool userCancelled;
}
