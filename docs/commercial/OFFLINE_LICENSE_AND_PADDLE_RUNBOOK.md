# Zahlungsabgleich und Offline-Lizenzen (T11/T12)

Implementiert, noch nicht gegen ein Anbieter-Konto getestet. Die ausgelieferte Konfiguration bleibt Sandbox, Verkauf aus, keine öffentlichen Schlüssel, keine Premium-Funktionen, keine Werbekampagne. Keine API-/Signierschlüssel im Client. `tools/commerce` ist Betreiberwerkzeug und kein Bestandteil der Desktop-Datenliste.

## Ablauf ohne eigenen Zahlungsserver

1. Betreiber richtet separat Sandbox-Konto, Produkt und wiederkehrenden Preis bei Paddle ein. API-Key nur in der Betreiberumgebung als `PADDLE_API_KEY` setzen. Niemals in Konfiguration, Ticket, Shell-Historie oder Repository schreiben.
2. Schlüssel außerhalb des Repositories erzeugen: `python -m tools.commerce keygen --private-key /geschuetzter/pfad/license.pem`. Ausgabe ist der öffentliche Ed25519-Schlüssel. Nur diesen unter einer stabilen Key-ID in `config/commercial_release.json` eintragen. Sandbox und Produktion erhalten getrennte Schlüssel/Buildkonfigurationen. Private Datei und SQLite-Journal geschützt sichern.
3. Testbestellung erzeugen: `python -m tools.commerce --operation-id sandbox-order-001 checkout --price-id pri_…`. Die vom Anbieter zurückgegebene Checkout-URL im eigenen Testbrowser verwenden. Ein Browser-Erfolgsbild oder Redirect allein berechtigt niemals zur Freischaltung.
4. Aktuelle abgeschlossene Transaktion abgleichen und signieren: `python -m tools.commerce license --transaction-id txn_… --private-key /geschuetzter/pfad/license.pem --key-id sandbox-1 --feature ad_free --price-id pri_… --output /geschuetzter/pfad/license.json`. Die CLI holt Transaktion einschließlich Adjustments sowie zugehöriges Abonnement frisch von Paddle. Produkt, Kundenzuordnung, Status und bezahlter Zeitraum müssen passen. Keine interaktive Anmeldung, kein Fremdzugriff und kein Versand erfolgen durch die CLI.
5. Lizenzdatei dem berechtigten Käufer über den vereinbarten sicheren Weg bereitstellen (nicht automatisiert implementiert). Nutzer importiert sie in Einstellungen. Sandbox-Lizenzen werden angezeigt, schalten aber keine Produktivfunktion frei. Ohne gültige Lizenz bleibt die lokale Basis nutzbar.
6. Verlängerung: zuletzt bezahlte Transaktions-ID abgleichen und neue Datei ausstellen/importieren. Maximale Offline-Laufzeit ist 31 Tage und niemals länger als der nachgewiesene bezahlte Zeitraum. Es gibt keinen automatischen serverlosen Lizenzversand. Dieser manuelle Betrieb ist die bewusst gewählte, vollständig lokale Alternative zum Lizenzserver.

Die Beispiele mit `…` sind absichtlich keine ausführbaren echten IDs. Die CLI prüft die exakten Anbieter-ID-Formate. Produktivmutationen verlangen zusätzlich `--environment production --allow-production`; dies ist keine Aufforderung, sie vor Freigabe auszuführen.

## Kündigung, Erstattung, Rechnungen

- Kündigung zum Periodenende: `python -m tools.commerce --operation-id sandbox-cancel-001 cancel --subscription-id sub_…`. `--immediate` nur bei ausdrücklich beabsichtigtem sofortigem Ende.
- Volle Erstattung: `python -m tools.commerce --operation-id sandbox-refund-001 refund --transaction-id txn_… --reason "Sandbox-Prüfung"`. Der Anbieter kann eine Erstattung zur Prüfung vormerken; `pending_approval` ist keine bestätigte Rückzahlung. Danach aktuellen Status im Anbieterportal abgleichen.
- Rechnungen/Zahlungsdaten: `python -m tools.commerce portal --customer-id ctm_… --subscription-id sub_…` erzeugt eine kurzlebige Portal-Session. Session-URLs wie Zugangsdaten behandeln, nicht loggen oder veröffentlichen. Rechnungen werden beim Anbieter abgerufen; die App stellt keine steuerlichen Rechnungen aus.
- Nach Refund, Chargeback, fehlender Zahlung, Pause oder Ende eine neue Lizenzrevision ohne Premiumrechte ausstellen. Bereits offline ausgegebene Berechtigungen können ohne Import der neuen Datei bis zum Ablauf fortbestehen. Sofortiger globaler Widerruf, Schutz vor Systemzeitmanipulation und Schutz gegen Administratoren sind offline nicht zugesichert.
- App-Lizenz entfernen / Daten löschen kündigt keinen Vertrag. Der Client bietet getrennte konfigurierte Wege für Verwaltung, Kündigung und Widerruf. Ein generischer Login zum Kundenportal ist **kein Nachweis** eines rechtlich ausreichenden Kündigungs- oder Widerrufswegs. Die jeweiligen öffentlich erreichbaren Anbieterwege müssen vor Verkauf separat bereitgestellt und freigegeben werden.

## Doppelte Ereignisse und Fehler

Mutationen erhalten eine eindeutige `--operation-id`. Das SQLite-Journal schreibt `pending` **vor** dem Request. Timeout/Crash führt deshalb nicht zur blinden Wiederholung. Gleiche ID bleibt gesperrt; zuerst im Dashboard nachsehen, ob die Operation erfolgte. Keine neue ID benutzen, solange der Ausgang unklar ist. Das Journal enthält Request-Fingerprint und Provider-ID, keine Karten- oder vollständigen Kundenantworten. Journalverlust kann den Wiederholungsschutz aufheben.

Lizenzen haben pro Abonnement eine monotone Revision. Alte oder widersprüchliche Revisionen werden beim Import abgewiesen. Signatur, Umgebung, Produkt, Zeitraum und Featureliste werden geprüft. Ein veralteter Zahlungsvorgang gewährt keinen neuen Abrechnungszeitraum; bei aktiver Verlängerung immer die aktuelle bezahlte Transaktion verwenden.

`verify_webhook` prüft die exakten Rohbytes mit HMAC, Timestamp-Toleranz und mehreren möglichen `h1`-Signaturen. Es gibt hier **keinen öffentlich betriebenen Webhook-Endpunkt**. Der serverlose Betriebsweg benötigt keinen: er liest vor jeder Ausstellung den Anbieterzustand. Wer später automatisiert, muss nach Signaturprüfung zusätzlich Event-ID dauerhaft deduplizieren, Ereignisse ordnen und die aktuelle API-Wahrheit abgleichen; der Sandbox-Reducer darf nicht als Produktiv-Webhook verwendet werden.

## Prüffälle für den Nutzer

Erfolg; Checkout abgebrochen (keine Lizenz); doppelte Operation-ID; Timeout nach möglicher Anbieterannahme; veränderte Signatur; falsche Umgebung/Produkt/Preis; abgelaufene Lizenz; ältere Revision nach Widerruf; Refund beantragt/bestätigt; Kündigung zum Ende/sofort; ausbleibende Verlängerung; Key-Rotation; Offline-Neustart. Tests in `tests/test_commercial_signed_licenses.py` sind vorbereitet, hier nicht ausgeführt.

## Anbieterreferenzen

Am 14.10.2026 konsultierte offizielle Schnittstellen: [Transaktion erstellen](https://developer.paddle.com/api-reference/transactions/create-transaction), [Subscription lesen](https://developer.paddle.com/api-reference/subscriptions/get-subscription), [kündigen](https://developer.paddle.com/api-reference/subscriptions/cancel-subscription), [Adjustment erstellen](https://developer.paddle.com/api-reference/adjustments/create-adjustment), [Portal-Sessions](https://developer.paddle.com/api-reference/customer-portals/create-customer-portal-session), [Webhook-Signatur](https://developer.paddle.com/webhooks/about/signature-verification). Konkrete Tarif-/Vertragsbedingungen sind keine Codekonstanten und werden hier nicht zugesagt.
