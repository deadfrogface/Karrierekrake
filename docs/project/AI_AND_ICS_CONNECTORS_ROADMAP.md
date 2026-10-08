# KI-Anbieter und kostenloser Kalender: sichere Einführung

## Stand dieses PRs
- Lokale KI bleibt der Standard; es werden keine Cloud-Keys benötigt.
- `guenther.ai_route.AIRoute` modelliert vier optionale Cloud-Anbieter (OpenAI, Anthropic, Gemini, Moonshot/Kimi). Cloud-Auswahl verlangt ausdrückliche Zustimmung **und einen nutzereigenen API-Key**. Diese Policy führt noch keine externen KI-Anfragen aus und ist noch nicht an die Einstellungen angeschlossen.
- Bestehende lokale Provider (llama.cpp, Ollama) bleiben unverändert.
- `integrations.calendar.ics_feed.fetch_ics_feed` bietet einen expliziten, nur lesenden ICS-Abruf mit Größenlimit, Kalender-Validierung und atomarem Dateiaustausch. **Noch nicht im UI aktiviert.** Die private URL muss künftig über den bestehenden OS-Keyring gespeichert werden; niemals in YAML, Logs oder URLs zu Telemetriediensten.
- Der kostenlose manuelle ICS-Import und IMAP bleiben weiterhin nutzbar.

## Noch erforderlich vor Freischaltung
1. **ICS-Sicherheit:** DNS-Pinning/Transport gegen DNS-Rebinding implementieren und Redirects mit echten HTTP-Tests abdecken. Aktuell ist der Feed aus Sicherheitsgründen auf Google-Hosts eingeschränkt. Private Kalender-ICS-Links sind geheime Bearer-URLs. URL nicht protokollieren.
2. **ICS-UI:** Opt-in-Dialog, Secret-Storage über Keyring, manuelle Aktualisierung, optionaler begrenzter Refresh, Löschen des Secrets, Status bei abgelaufenen Links und Integration mit `local_calendar_path`. Keine automatische Termin-Erstellung über ICS.
3. **KI:** Provider-Auswahl in Einstellungen, Kostenwarnung, lokale Secret-Verwaltung, Timeouts, Redaction und Tests für die externen APIs. Keine Hintergrundanfragen, keine automatischen Fallbacks zu Cloud-KI.
4. **Abo-Login:** ChatGPT-/Claude-/Gemini-/Kimi-Chatabos sind keine allgemein nutzbaren API-Schlüssel. Account-Anbindung nur über offiziell dokumentierte, für kommerzielle Drittanbieter erlaubte OAuth-/Partner-Flows. Bis dahin keinen Chat-Login-Button anbieten.
5. **Gmail:** IMAP mit App-Passwort nur dort anbieten, wo Google und die Kontorichtlinien es unterstützen. Keine Behauptung, dass IMAP bei jedem Google-Konto ohne OAuth funktioniert.

Keine kommerzielle Cloud-Integration wird mit diesem PR als fertig ausgewiesen.
