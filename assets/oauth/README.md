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

## GitHub Actions builds

Repository Settings → Secrets and variables → Actions → New repository secret.
Name: `GOOGLE_DESKTOP_CLIENT_JSON`. Value: the complete newly registered Desktop
client JSON (not a filename). Both Windows workflows provision it before
PyInstaller. Missing or invalid input stops the build. The release artifact gate
opens the actual EXE and validates the embedded client. Secret values are never
printed, cached, or uploaded separately. Fork PRs without secrets cannot produce
a distributable Google-enabled EXE.
