# PR #144 — vollständige Arbeitszerlegung und Abnahme-Gates

Stand: 13.10.2026. **Kein Punkt ist allein durch eine PR-Nummer als erledigt anzusehen.** Alle nachfolgenden Änderungen bleiben bis zum späteren Review ungemergt.

| Paket | Bereits vorbereitete PRs | Weitere zwingende Nachweise / Implementierungen |
|---|---|---|
| T01 Kernfunktionen/CI | #145 | Laufzeit-Baseline, parallele Tests ohne Coverage-Verlust, Parser/Suche/Filter/Löschung/Dry-Run/Freeze-Regressions |
| T02 Modellinstallation | #146 #147 #148 #149 #150 #151 | Echter Download, SHA256, Wiederaufnahme, Probe, Aktivierung, Neustart auf Windows |
| T03 Updater | – | Fehler reproduzieren, Download/Checksum/Asset/Recovery/Profil-Erhalt E2E |
| T04 Desktop-OS | – | Windows/Linux/macOS Build-Matrix, native Smoke, physische Testgeräte |
| T05 Setup/UI/Browser | #148 #151 | Wizard-Start, Navigation, Browser-Auswahl, Popup-Fokus, 125–200%-Tests |
| T06 Security/CRA | #154 | Security-Audit, Dependency-Freeze/Advisories, Incident-Verifikation, CRA-Rechtsprüfung |
| T07 Datenschutz | – | Export/Löschung/Neustart-Tests, Logging-Redaktion, Datenflussabgleich |
| T08 SBOM/Lizenzen | #156 | Native Abhängigkeiten, Modelle, Daten, Lizenztexte, SBOM im Release |
| T09 Verbraucherrecht | #153 | Finales AGB/Impressum/Widerruf mit echten Anbieterangaben und juristischer Freigabe |
| T10 Barrierefreiheit | – | NVDA/VoiceOver, Tastatur, Kontrast, Skalierung, BFSG-Einstufung |
| T11 Free/Premium/Ads | #155 | Implementierte Offline-Free-Gates, Werbeeinwilligung und geprüfte Premium-Abgrenzung |
| T12 Payments | #155 | Paddle Sandbox, idempotente Entitlements, Refund/Cancel/Offline-Tests; Verträge offen |
| T13 Betrieb | #154 | Support- und Restore-E2E, Verantwortlichkeiten, reale Unternehmensdaten |
| T14 Website/Marke | #153 | Website-Implementierung, Domain-/Markenprüfung, Anbieterfreigabe |
| T15 Beta | #152 | Menschliche Windows/Linux/macOS Durchläufe und dokumentierte Befunde |
| T16 Wachstum | #155 | Validierte Kostenannahmen, Demo, belastbare Zahlen, reale Kontakte |

## Technische Gate-Regeln
1. Jede PR beginnt vom unveränderten aktuellen `main` und enthält einen begrenzten, prüfbaren Scope.
2. Ein erfolgreicher Unit-Test ist kein Endnutzer-E2E-Beleg. Statuswerte: ENTWURF / IMPLEMENTIERT / CI-BESTÄTIGT / REALGERÄT-BESTÄTIGT.
3. Keine reale Bewerbung, Mail, Zahlung, Kontoanlage, Werbeausspielung oder Veröffentlichung in CI.
4. CI darf nicht durch Entfernen/Skippen bestehender Tests beschleunigt werden.
5. Gleichzeitige PRs, die dieselben Dateien ändern, müssen vor dem Merge auf Konflikte geprüft und neu basiert werden.
6. Menschliche Freigaben und externe Anbieter-Verifizierung sind ausdrücklich nicht durch Code ersetzbar.

## Bestandsabgleich mit main
`core/app_updates.py`, `core/native_updates.py`, `desktop/services/browser_install.py`, `core/privacy/lifecycle.py` und diverse Security-/Accessibility-Dokumente existieren bereits. Die Arbeit besteht aus Lückenanalyse, Reparatur und Tests, **nicht** dem erneuten Erfinden dieser Funktionen.
