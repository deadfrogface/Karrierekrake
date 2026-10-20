# Personaler-Abnahme 2026-10-20 (T01.10, T05.07)

Prüfende Instanz: Claude Code (KI-Assistent), von Damiano am 2026-10-20 als Kritiker und Personaler beauftragt.
Grundlage: `docs/personaler/ABNAHME_CHECKLISTE.md` §1, §2 und §8. Stand: #144-Head `3e5ebdf7`.
Hinweis zur Unabhängigkeit: Die prüfende Instanz hat am 2026-10-20 andere Punkte von PR 144 selbst umgesetzt,
aber weder das T01.10-Produktverhalten noch das Gold.

## T01.10 – Antwortentwürfe und ICS (synthetisches Konto)

- Gold: `tests/fixtures/t0110_synthetic_account/expected.json` (Commit `86a0e89`, Personaler, SHA-256 `5cd3a994…dea6c`,
  im Test gepinnt) und `expected_addendum_1.json` (Commit `c90aca32`, Personaler). Seitdem unverändert.
- Output: Produktverhalten über `tests/test_t0110_synthetic_mail_calendar.py`, lokal ausgeführt am 2026-10-20:
  150 bestanden, 31 strikte xfails (= dokumentierte Abweichungen vom Gold), 0 Netzversuche.

| Mail / Sample | Lieferstück | Urteil | Entscheidende Beobachtung | Versand frei | Kalender schreiben frei |
|---|---|---|---|---|---|
| M1 Eingangsbestätigung | Zuordnung | Papierkorb | kein Fall zugeordnet (Absender bewerbung@/karriere@, Referenz nicht genutzt); Gold `case-t0110-01` | nein | – |
| M2 Eingangsbestätigung | Zuordnung | Papierkorb | kein Fall zugeordnet; Gold `case-t0110-03` | nein | – |
| M3 Einladung | Antwortentwurf | Papierkorb | schlägt nie angebotene Termine vor (21.10., 23.10., 30.10.), Gold-Slot 28.10. 14–15 Uhr fehlt, Rang 1 falsch, keine Zusage genau eines Slots, Referenz BW-DA-7731 fehlt | nein | – |
| M3 Einladung | ICS | Papierkorb | `DTSTART`/`DTEND` in UTC (`…Z`) statt `TZID=Europe/Berlin`, keine `LOCATION` | – | nein |
| M4 Einladung | Antwortentwurf | Blockiert | kein Entwurf, obwohl das Gold einen erlaubt (fail-safe ohne Kandidaten) – nichts zu prüfen | nein | – |
| M5 Absage | Antwortentwurf | Papierkorb | bietet Rückfragen an, „freue mich auf die nächsten Schritte“, Standardbaustein statt kurzem Dank (§8.1 Absage) | nein | – |
| M6 Unterlagen-Anfrage | Antwortentwurf | Papierkorb | als `review` statt `document_request` eingestuft, Arbeitszeugnis nicht als Anhang genannt, Referenz fehlt | nein | – |
| M7 mehrdeutig | Antwortentwurf | Interview-ready | kein verbindlicher Entwurf, wie gefordert | nein | – |
| M8 ausgeschlossener Absender | Antwortentwurf | Interview-ready | kein Entwurf, wie gefordert | nein | – |
| M9 Terminabsage | Entwurf/ICS | Interview-ready | Absage-Update ohne Neuanlage; Gold-Prüfungen bestanden | nein | nein |

**Gesamturteil T01.10: nicht abgenommen.** 5 Mails Papierkorb, 1 Blockiert, 3 Interview-ready. Unbeaufsichtigter
Versand und Kalender-Schreiben bleiben aus. Work-Item T01.10 bleibt OFFEN.

## T05.07 – Design, Begriffe, Wartezeit aus Nutzersicht (synthetische Persona)

**Blockiert.** Im Stand liegt kein Durchlauf-Sample aus Nutzersicht (Bildschirmfotos oder Bildschirmtexte eines
installierten Pakets mit synthetischer Persona). Nach §2 wird ohne Quelle und Output kein Urteil gebildet und nichts
aus dem Gedächtnis ergänzt. Nötig: ein Durchlauf der Kernabläufe (Einrichtung, CV-Import mit Wartezeit, Suche,
Bewerbung) im installierten Paket auf einem echten Bildschirm, mit einer Persona aus `tests/e2e` und Bildschirmfotos je
Schritt. `scripts/capture_real_font_screenshots.py` reicht dafür nicht: Es fotografiert nur die Modell-Setup-Karte.
