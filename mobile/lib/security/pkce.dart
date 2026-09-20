import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// PKCE (RFC 7636) helpers — required for native public clients.
class PkcePair {
  const PkcePair({
    required this.codeVerifier,
    required this.codeChallenge,
    this.codeChallengeMethod = 'S256',
  });

  final String codeVerifier;
  final String codeChallenge;
  final String codeChallengeMethod;

  /// Generate a high-entropy verifier and S256 challenge.
  factory PkcePair.generate([Random? random]) {
    final rng = random ?? Random.secure();
    final bytes = Uint8List.fromList(
      List<int>.generate(64, (_) => rng.nextInt(256)),
    );
    final verifier = base64UrlEncode(bytes).replaceAll('=', '');
    final digest = sha256.convert(utf8.encode(verifier));
    final challenge = base64UrlEncode(digest.bytes).replaceAll('=', '');
    return PkcePair(codeVerifier: verifier, codeChallenge: challenge);
  }
}

String generateOAuthState([Random? random]) {
  final rng = random ?? Random.secure();
  final bytes = Uint8List.fromList(
    List<int>.generate(32, (_) => rng.nextInt(256)),
  );
  return base64UrlEncode(bytes).replaceAll('=', '');
}
