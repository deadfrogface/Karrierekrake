import 'dart:convert';

/// Tokens held only in secure storage — never SharedPreferences / Drift / logs.
class TokenSet {
  const TokenSet({
    required this.accessToken,
    this.refreshToken,
    this.idToken,
    this.tokenType = 'Bearer',
    this.expiresAt,
    this.scope = const [],
    this.obtainedAt,
  });

  final String accessToken;
  final String? refreshToken;
  final String? idToken;
  final String tokenType;
  final DateTime? expiresAt;
  final List<String> scope;
  final DateTime? obtainedAt;

  bool isExpired([DateTime? now]) {
    if (expiresAt == null) return false;
    final clock = now ?? DateTime.now().toUtc();
    // 60s skew
    return !clock.isBefore(expiresAt!.subtract(const Duration(seconds: 60)));
  }

  bool get hasRefresh => (refreshToken ?? '').isNotEmpty;

  Map<String, dynamic> toJson() => {
        'access_token': accessToken,
        'refresh_token': refreshToken,
        'id_token': idToken,
        'token_type': tokenType,
        'expires_at': expiresAt?.toUtc().toIso8601String(),
        'scope': scope,
        'obtained_at': obtainedAt?.toUtc().toIso8601String(),
      };

  factory TokenSet.fromJson(Map<String, dynamic> json) {
    DateTime? parse(String? raw) =>
        raw == null || raw.isEmpty ? null : DateTime.tryParse(raw)?.toUtc();
    final scopeRaw = json['scope'];
    List<String> scopes = const [];
    if (scopeRaw is List) {
      scopes = scopeRaw.map((e) => e.toString()).toList();
    } else if (scopeRaw is String && scopeRaw.isNotEmpty) {
      scopes = scopeRaw.split(RegExp(r'\s+'));
    }
    return TokenSet(
      accessToken: json['access_token']?.toString() ?? '',
      refreshToken: json['refresh_token']?.toString(),
      idToken: json['id_token']?.toString(),
      tokenType: json['token_type']?.toString() ?? 'Bearer',
      expiresAt: parse(json['expires_at']?.toString()),
      scope: scopes,
      obtainedAt: parse(json['obtained_at']?.toString()),
    );
  }

  String encode() => jsonEncode(toJson());

  factory TokenSet.decode(String raw) =>
      TokenSet.fromJson(jsonDecode(raw) as Map<String, dynamic>);

  /// Redacted for logs / UI — never leak tokens.
  @override
  String toString() =>
      'TokenSet(expiresAt: $expiresAt, scopes: $scope, hasRefresh: $hasRefresh)';
}

enum AuthOutcome {
  success,
  cancelled,
  denied,
  networkError,
  invalidConfig,
  tamperedRedirect,
  expired,
  revoked,
  offline,
}

class AuthResult {
  const AuthResult({
    required this.outcome,
    this.tokens,
    this.message = '',
  });

  final AuthOutcome outcome;
  final TokenSet? tokens;
  final String message;

  bool get ok => outcome == AuthOutcome.success && tokens != null;
}
