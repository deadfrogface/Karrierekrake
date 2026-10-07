# Windows component updates

The new managed installation ships `Karrierekrake.exe` and
`update-current.json`. The model is installed once from Settings → General.
Keep the whole installation directory in a writable folder. Existing standalone
EXEs require one manual move to this new Setup ZIP; their user data stays under
LOCALAPPDATA/Karrierekrake. No account/token/server is needed for public releases.

Startup checks GitHub in a worker after the window appears. Settings provides
manual check and install controls. No download or restart occurs without a click.
Offline/rate-limited checks do not block normal use.

Each release has a fixed repository/tag manifest with monotonic sequence,
protocol version, byte counts and SHA-256 for each component and each download
part. Downloads stream to staging. The multi-GB model is split into <=1 GB assets;
only changed components download, and unchanged components are verified before
installation. This is component-level updating, not binary delta patching.

A local PowerShell helper waits for the GUI process to exit, checks staged file
hashes again, backs up replaced files, commits the manifest last and restarts.
Normal replacement failures restore previous files. User data is never a target.
No elevation, remote script download or embedded GitHub token is used. Integrity
uses SHA-256 over authenticated HTTPS from the fixed public GitHub release;
independent publisher signing / Authenticode is not provided.

The publisher runs after successful main push CI and Windows Smoke for the same
SHA, ignores superseded main commits, builds a separate non-embedded EXE, scans
production content, checks the exact model hash and runs the complete component
installation acceptance. Assets remain a draft until uploaded and checked.
Existing embedded-onefile build/Smoke remains available unchanged.

The model stays inside the CI full install folder but is excluded from the public
Setup ZIP. On first run the UI offers the one-time model download, using the same
verified update transaction. Later UI changes download only the EXE component.

Rollback covers file installation errors, not failed database migrations after
launch or interrupted power during replacement. Database compatibility must be
maintained by the existing migration system; upgrades that change update protocol
need a compatible bridge release. Windows helper and packaged lifecycle checks
must pass before this can be called verified on a real Windows installation.

Developer checks: tests/test_app_updates.py (Windows helper cases run on Windows),
tests/test_update_panel.py, tests/test_package_component_update.py; the existing
CV EXE acceptance supports `--component-install` without weakening its default
embedded-model gate. Actual download/replacement end-to-end still needs a public
release produced by the new workflow after merge.
