# Demo und 12-Monats-Arbeitsplan (T13/T16)

## Zehnminütige Demo ohne echte Bewerbungen

Vorbereitung: isoliertes absolutes `KARRIEREKRAKE_DATA_DIR`, synthetischer CV, keine verbundenen Konten, Dry-Run sichtbar, gegebenenfalls Modell vorab installiert. Keine echten Daten aus dem regulären Profil kopieren.

1. Minute 0–2: Problem zeigen – Profil, Stellen und Rückmeldungen an einem Ort; kostenlose lokale Basis erklären. Keine beleglosen Aussagen zu Nutzerzahlen oder Marktanteilen.
2. Minute 2–4: Synthetischen CV importieren, erkannte Felder gemeinsam prüfen und einen Fehler bewusst korrigieren. Berufswunsch optional lassen und danach ergänzen.
3. Minute 4–6: Beispielsuche/gespeicherte synthetische Ergebnisse filtern; Vorbereitung im Dry-Run, Prüfung des Entwurfs und sichtbare Grenze vor realem Versand.
4. Minute 6–8: Bewerbung manuell im Verlauf markieren, Erinnerungs-/Kalenderentwurf zeigen. Ohne Testkonto keine Verbindung vortäuschen.
5. Minute 8–9: Export/Backup zeigen; Offline-Neustart vorbereiten. Lizenzbereich ohne Kaufzwang; kein echter Checkout in der Demo.
6. Minute 9–10: Grenzen offen zeigen: Alpha-Geräteabnahme, benötigte Anbieterfreigaben, Supportaufwand. Feedbackfrage: Welche konkrete Aufgabe wurde schneller, was blieb unklar?

## Positionierung und Vergleich

Vergleichshypothese: Karrierekrake verbindet lokale Datenhaltung, Vorbereitung und Bewerbungsverlauf. Gegenüber einer Tabelle/Notizen bietet das Produkt strukturierte Abläufe; gegenüber Jobbörsen soll es mehrere Schritte der persönlichen Organisation verbinden. Diese Aussagen sind Produktziele, keine geprüfte Marktüberlegenheit.

Für jeden realen Wettbewerber später dieselben belegbaren Merkmale erfassen: lokale/cloudbasierte Speicherung, Export/Löschung, Profilimport, Stellenquellen, tatsächlicher Versandmodus, Integrationen, Preisdatum, Plattformen, Quelle und beobachtete Einschränkungen. Preise/Marktanteile ohne aktuelle Quelle nicht in ein Pitchdeck übernehmen. Vor Gesprächen mit Jörg oder anderen Partnern diese Tabelle anhand der tatsächlich gewählten Kandidaten ergänzen; niemand wurde kontaktiert.

## Rechenmodell

`scripts/launch_scenario.py` berechnet zwölf Monate aus `config/launch_scenario.example.json`. Alle Werte in der Beispieldatei sind frei gewählte Rechenannahmen, einschließlich Steuersatz und Gebühren; keine Angebote oder geltenden Tarife. Bestehende alte Maps-Proxy-Kosten werden nicht vorausgesetzt. Die CLI erzeugt Monatswerte für aktive/zahlende Nutzer, Bruttowert, Erlös ohne angenommene Steuer, Providerkosten, Erstattungsreserve, Betrieb, Sponsorumsatz und Kassenbestand.

Vor belastbarer Verwendung ersetzen: tatsächliche Anbietergebühr, Steuerbehandlung, Preis, Domain/Hosting/Downloadkosten, Rechts-/Steuerberatung, Signierung, Supportstunden einschließlich eigener Arbeit, Geräte, Versicherung, Akquise und Erstattungspuffer. Keine Posten durch Null verstecken, nur weil ein Angebot fehlt. Drei Szenarien separat speichern: keine Konversion, vorsichtige Nachfrage, erhöhte Nachfrage mit höherem Supportbedarf. Negativer Kassenbestand ist ein Szenariosignal, keine Zahlungsfähigkeitsprognose.

## Arbeitsplan und Entscheidungen

| Zeitraum | Ergebnis | Messgröße / Entscheidung |
|---|---|---|
| Monat 1–2 | T01–T15-Abnahme mit synthetischen Daten und Zielgeräten | Blocker, Reproduzierbarkeit, Importkorrekturen, Supportminuten |
| Monat 3–4 | Freigegebene Anbieter-/Rechts-/Preisentscheidung, kleine freiwillige Beta | Erledigte Aufgaben je Testperson, Abbrüche, tatsächlich benötigte Funktionen |
| Monat 5–6 | Kontrollierte Veröffentlichung nur nach Release-Gates | Installation/Update-Erfolg, Fehlerquote, Wiederherstellung, reale Kosten |
| Monat 7–9 | Stabilisierung nach echten Rückmeldungen | Retention separat messen, Supportlast, Refunds, profitable/teure Funktionen |
| Monat 10–12 | Entscheidung über Wachstum, Partner und Mobile | Belegbare Nachfrage, Kosten je aktivem Nutzer, finanzierbarer Support |

Abhängigkeiten werden nicht als Zusagen verkauft. Jeder Zeitraum ist Planung, kein Veröffentlichungsversprechen. Kein Investor-/Partnerkontakt, kein Budgetauftrag und keine Veröffentlichung durch dieses Dokument.
