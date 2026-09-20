# Device OAuth bridge (optional)

`NativeOAuthSession` is fully testable via injected `AuthBrowser` /
`TokenEndpointClient`.

On real devices, wire `flutter_appauth` (AppAuth-Android / AppAuth-iOS) as the
`AuthBrowser` + token client — **system browser / Custom Tabs /
ASWebAuthenticationSession only**. Never embed a WebView.

Push backends and calendar cloud writes remain blocked until
`docs/mobile/sync_decision.md` is resolved.
