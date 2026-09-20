import 'package:flutter/material.dart';

import '../../security/feature_flags.dart';
import '../../security/oauth_session.dart';

/// Security / auth controls — revoke, feature flags, no token display.
class SecuritySettingsScreen extends StatefulWidget {
  const SecuritySettingsScreen({super.key, required this.session});

  final NativeOAuthSession? session;

  @override
  State<SecuritySettingsScreen> createState() => _SecuritySettingsScreenState();
}

class _SecuritySettingsScreenState extends State<SecuritySettingsScreen> {
  String _status = '—';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _refreshStatus();
  }

  Future<void> _refreshStatus() async {
    final s = widget.session;
    if (s == null) {
      setState(() => _status = 'OAuth-Session nicht konfiguriert');
      return;
    }
    final t = await s.currentTokens();
    setState(() {
      _status = t == null
          ? 'Abgemeldet'
          : 'Angemeldet · läuft ab ${t.expiresAt ?? "unbekannt"} · scopes ${t.scope.join(" ")}';
    });
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final flags = session?.flags ?? MobileFeatureFlags.commercialSafe;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Sicherheit & Auth', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text(
          'Native OAuth (Systembrowser + PKCE). Kein WebView. '
          'Tokens nur in Secure Storage. Client-Secrets sind nicht vertraulich.',
        ),
        const SizedBox(height: 12),
        Text(_status),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _busy || session == null
              ? null
              : () async {
                  setState(() => _busy = true);
                  final r = await session.login();
                  setState(() {
                    _busy = false;
                    _status = r.ok
                        ? 'Login OK'
                        : 'Login: ${r.outcome.name} — ${r.message}';
                  });
                },
          child: const Text('Anmelden (Systembrowser)'),
        ),
        const SizedBox(height: 8),
        OutlinedButton(
          onPressed: _busy || session == null
              ? null
              : () async {
                  setState(() => _busy = true);
                  final r = await session.revoke();
                  setState(() {
                    _busy = false;
                    _status = 'Revoke: ${r.message}';
                  });
                },
          child: const Text('Abmelden / Revoke'),
        ),
        const Divider(height: 32),
        Text('Integrationen', style: Theme.of(context).textTheme.titleMedium),
        SwitchListTile(
          title: const Text('OAuth'),
          value: flags.oauthEnabled,
          onChanged: session == null
              ? null
              : (v) {
                  setState(() {
                    session.flags = flags.copyWith(oauthEnabled: v);
                  });
                },
        ),
        SwitchListTile(
          title: const Text('Kalender-Schreiben'),
          subtitle: const Text('Standard AUS — Transport UNSPECIFIED'),
          value: flags.calendarWriteEnabled,
          onChanged: session == null
              ? null
              : (v) {
                  setState(() {
                    session.flags = flags.copyWith(calendarWriteEnabled: v);
                  });
                },
        ),
        SwitchListTile(
          title: const Text('Remote Push'),
          subtitle: const Text('Gesperrt — Backend Future Work'),
          value: false,
          onChanged: null,
        ),
        const SizedBox(height: 12),
        const Text(
          'Push: siehe docs/mobile/auth_security.md — kein erfundenes Backend.',
          style: TextStyle(fontSize: 12),
        ),
      ],
    );
  }
}
