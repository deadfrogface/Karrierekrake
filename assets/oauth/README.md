# Desktop OAuth app identity

Before building the EXE, place the registered Google Desktop client JSON at
`assets/oauth/desktop_client.json`. The packaging allowlist includes only this
file. It is optional for source checkouts; users can import their own client
in Settings. The system browser requests consent and user tokens remain in
existing secure token storage.

The repository rejects the Google-generated client secret via secret scanning.
Do not bypass that rule or commit user tokens or service account keys. Provision
the file locally before packaging, or through an authorized private build input.
Never upload this file as a standalone CI artifact.
