/// Push / notification policy.
///
/// Remote push requires an approved backend (PR37 sync = UNSPECIFIED).
/// This module documents and enforces the STOP — it does **not** invent FCM/APNs.
library;

import '../security/feature_flags.dart';

class PushPolicy {
  const PushPolicy({this.flags = MobileFeatureFlags.commercialSafe});

  final MobileFeatureFlags flags;

  bool get remotePushAllowed => flags.remotePushEnabled;

  /// Validate a hypothetical notification payload before display/schedule.
  PushPayloadVerdict validatePayload(Map<String, dynamic> payload) {
    if (!flags.remotePushEnabled && payload['remote'] == true) {
      return const PushPayloadVerdict(
        allowed: false,
        reason: 'remote push backend UNSPECIFIED — future work',
      );
    }
    for (final key in payload.keys) {
      final k = key.toLowerCase();
      if (_sensitiveKey(k)) {
        return PushPayloadVerdict(
          allowed: false,
          reason: 'sensitive field forbidden in push payload: $key',
        );
      }
    }
    final body = payload['body']?.toString() ?? '';
    if (_looksLikePii(body)) {
      return const PushPayloadVerdict(
        allowed: false,
        reason: 'payload body looks like PII / mail content',
      );
    }
    return const PushPayloadVerdict(allowed: true, reason: 'ok');
  }

  static bool _sensitiveKey(String k) =>
      k.contains('email') ||
      k.contains('token') ||
      k.contains('password') ||
      k.contains('access_token') ||
      k.contains('refresh') ||
      k.contains('cv') ||
      k.contains('salary') ||
      k.contains('message_body') ||
      k.contains('mail_body');

  static bool _looksLikePii(String body) {
    if (body.contains('@') && body.contains('.')) return true;
    if (RegExp(r'\+?\d[\d\s-]{7,}').hasMatch(body)) return true;
    return false;
  }
}

class PushPayloadVerdict {
  const PushPayloadVerdict({required this.allowed, required this.reason});
  final bool allowed;
  final String reason;
}

/// Documented future work — do not implement until backend approved.
const kPushFutureWork = '''
# Push — Future Work (STOP)

Remote push (FCM / APNs) needs:

1. Approved sync/transport architecture (`docs/mobile/sync_decision.md`)
2. Device registration endpoint with auth
3. Payload schema without mail/job PII
4. User opt-in + OS permission
5. Background constraints documented per platform

Until then: `MobileFeatureFlags.remotePushEnabled = false`.
''';
