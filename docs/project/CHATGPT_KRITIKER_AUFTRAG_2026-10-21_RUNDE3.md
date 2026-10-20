# Prüfauftrag: unabhängige Kritiker-Abnahme von 19 Paket- und Nachweis-Punkten (Karrierekrake PR 144, Runde 3)

Du bist unabhängiger Kritiker für das Projekt Karrierekrake (lokale Desktop-App für Jobsuche, PySide6/Python, native
Pakete für Windows, Linux und macOS mit PyInstaller). Claude Code hat die folgenden 19 Punkte selbst umgesetzt und darf
sie deshalb nicht selbst abnehmen. Sie stehen in `docs/project/PR144_WORK_ITEMS.json` auf „IMPLEMENTIERT – PRÜFUNG
OFFEN“. Du entscheidest je Punkt: **FERTIG** oder **OFFEN**.

## Regeln

1. FERTIG nur, wenn die Begründung für **genau dieses Kriterium** trägt und mit den genannten Quellen nachprüfbar ist.
   Im Zweifel OFFEN. Keine Rechtsberatung, keine Paket- oder Gerätefreigabe ableiten.
2. Prüfe jede Behauptung selbst am Code und an den CI-Läufen. Nimm die Begründung nicht als gegeben.
3. Ein Quelltest ersetzt keinen Nachweis am gebauten Paket, wenn das Kriterium das Paket nennt.
4. Benenne bei OFFEN den konkreten fehlenden Beleg oder den Denkfehler.
5. Schreibe keine Fakten dazu, die du nicht prüfen konntest. Kannst du eine Quelle nicht öffnen, sag das.

## Stand

- Branch `cursor/roadmap-execution-20261012-d85b`, Head-Commit `7eb0fcee` (die Work-Items-Änderung dieses Auftrags
  liegt in einem späteren reinen Dokumentations-Commit).
- CI auf `7eb0fcee`: 21/21 grün. CI 39500605555, Desktop Platforms 39500603955, Windows Smoke 39500603920
  (<https://github.com/deadfrogface/Karrierekrake/actions/runs/39500603955>). Die Job-Logs erfordern einen
  GitHub-Login; öffentlich sind die Annotationen der Läufe.
- Der Abnahme-Maßstab steht in `docs/personaler/ABNAHME_CHECKLISTE.md`.

## Worauf du besonders achten sollst

- **macOS-Inventar (T06.05.07.06.03/.04):** Das `.app` wird nach dem SBOM-Export neu signiert; die Hashes der
  Mach-O-Dateien weichen deshalb ab und werden als `rewritten_after_sbom` mit beiden Hashes ausgewiesen statt als
  Fehler. Trägt das für „sämtliche nativen Dateien des tatsächlichen Pakets hashprüfen“, oder ist das Kriterium damit
  nur teilweise erfüllt (Vergleich signierter Pakete ist T08.06 und offen)?
- **Windows-Inventar (T06.05.07.06.02):** `VCRUNTIME140.dll` liegt mehrfach vor (Root, PySide6, shiboken6); die
  Zuordnung erfolgt über den Inhalts-Hash. Prüfe, ob eine manipulierte Kopie trotzdem auffiele
  (`test_same_name_with_unrecorded_bytes_still_fails`).
- **Herkunft der Assets (T08.05.05):** Geprüft wird der Repository-Stand von `assets/brand` und `templates`, nicht die
  Bytes im fertigen Paket. Die Vorlage `templates/cover_letter.txt` wurde nach dem Initial-Commit geändert (zuletzt
  `a3124286`); gepinnt ist der aktuelle Text-Hash (LF-normalisiert). Die Schrift DejaVu Sans Bold ist ins Bild
  `social-preview.png` eingerendert; ihr Lizenztext steht nicht in den Notices (offen, Rechtefreigabe T08.07).
- **Paket-Selbsttest (T02.06, T02.07, T03.06, T06.04, T06.05.07.05.03, T10.04, T11.05):** Trägt der automatische
  Selbsttest am gebauten Paket das jeweilige Kriterium, oder verlangt es einen GUI-Durchlauf bzw. ein Gerät
  (T05.05/T05.07 sind offen)?
- **T01.10:** Abnahme mit synthetischen Konten und Daten (Entscheidung 2026-10-18), nicht mit echten Konten.
- **T07.06:** Vier Hosts sind nicht abgedeckt (P32 in `docs/project/PR144_P_NICHT_MACHBAR.md`).
- **T14.03:** Handelsregister-Formularsuche (Northdata-Hinweis HRB 168732) steht aus und braucht Freigabe.

## Antwortformat (bitte genau so, eine Zeile je Punkt)

`<ID> | FERTIG oder OFFEN | Begründung in höchstens drei Sätzen mit Quelle`

## Die 19 Punkte

Je Punkt stehen `acceptance`, `evidence` und `evidence_scope` in `docs/project/PR144_WORK_ITEMS.json`.

| ID | Kriterium (Kurzform) | Hauptbeleg |
|---|---|---|
| T01.10 | Mail-/Kalender-Abläufe mit synthetischen Konten | `plan_mail_reply`, Zuordnung/Klassifikator 1.1.0, Commit `f2fd6ef0` |
| T02.06 | Guard und GGUF-Probe im Paket | `--package-selfcheck` |
| T02.07 | Realer Transfer und wiederholte Nutzung im Paket | `--package-selfcheck` |
| T03.04 | Windows-Upgrade von Altversion mit Profil | Windows Smoke, Upgrade-Schritt |
| T03.06 | Manuelle und Start-Updateprüfung im Paket | `--package-selfcheck`, Updater-Fix `15bee27c` |
| T06.04 | diskcache-Deserialisierung im Paket gesperrt | `--package-selfcheck` |
| T06.05.07.05.03 | Gepatchte cryptography/OpenSSL im Paket | `--package-selfcheck` |
| T06.05.07.06.01 | Linux: native Dateien hashprüfen | `scripts/ci_native_family_inventory.py` |
| T06.05.07.06.02 | Windows: native Dateien hashprüfen | dasselbe, Fix `2a6650ee` |
| T06.05.07.06.03 | ARM-macOS: native Dateien hashprüfen | dasselbe, Fix `7eb0fcee` |
| T06.05.07.06.04 | Intel-macOS: native Dateien hashprüfen | dasselbe, Fix `7eb0fcee` |
| T07.06 | Datenflussinventar gegen Paketstand | Inventar, 4 Hosts = P32 |
| T08.02.03 | Windows-Buildinventar und Lizenzprüfung | `scripts/ci_license_review_check.py` |
| T08.03 | OpenSSL-Minorversion im Buildinventar | Buildinventar |
| T08.05.01 | Distributions-Copyrighttexte im Paket | `THIRD_PARTY_NOTICES.txt` im Paket |
| T08.05.05 | Schriften-/Bild-/Vorlagenrechte technisch zuordnen | `scripts/asset_origins.py`, `tests/test_asset_origins.py` |
| T10.04 | Kernabläufe mit installiertem Paket | `--package-selfcheck` |
| T11.05 | Paket ohne Kampagne/Verkauf mit freier Basis | `--package-selfcheck` |
| T14.03 | Namens-/Domainrecherche mit Quellen und Datum | `docs/commercial/brand_evidence_2026-10-20`, Commit `3bad6456` |
