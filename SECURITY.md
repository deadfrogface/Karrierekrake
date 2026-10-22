# Sicherheit / Security Policy

Karrierekrake ist eine lokale Desktop-Anwendung für Bewerbungen. Bewerbungsdaten bleiben auf dem Gerät.
Diese Seite sagt, wie du eine Sicherheitslücke meldest und was du von uns erwarten kannst.

> **Stand der Alpha:** Die Alpha wird nicht verkauft und nur an bekannte Tester gegeben. Die Regeln unten gelten
> trotzdem schon, damit beim ersten Verkauf nichts umgestellt werden muss.

## Lücke melden

| | |
|---|---|
| Meldeadresse | **[von Damiano auszufüllen: z. B. security@deine-domain.de]** |
| Hersteller | **[von Damiano auszufüllen: Name und ladungsfähige Anschrift]** |
| Sprache | Deutsch oder Englisch |

Bitte **keine** echten Bewerbungsdaten, Zugangsdaten oder Schadcode mitschicken. Beschreibe, welche Version und
welches Betriebssystem du nutzt und wie sich das Problem nachstellen lässt.
Bitte nenne die Lücke nicht öffentlich, bevor ein Fix verfügbar ist (koordinierte Offenlegung).
Wir nennen auf Wunsch gern deinen Namen in den Release-Hinweisen.

## Was du von uns erwarten kannst

- **Eingangsbestätigung** innerhalb von 5 Werktagen.
- **Einschätzung** (betroffen / nicht betroffen, Schweregrad) so schnell wie möglich, in der Regel binnen 14 Tagen.
- **Fix** für kritische und hohe Lücken zuerst; Umgehungslösungen, wenn der Fix länger braucht.
- **Hinweis an Nutzer** in den Release-Hinweisen und, wenn nötig, in der App.

Wird eine Lücke bereits aktiv ausgenutzt, gelten für uns als Hersteller die Meldefristen des Cyber Resilience Act
(Verordnung (EU) 2024/2847, Art. 14): Erstmeldung an die zuständigen Stellen binnen 24 Stunden, Folgemeldung
binnen 72 Stunden, Abschlussbericht danach. Der interne Ablauf steht in `docs/operations/SUPPORT_BACKUP_INCIDENT.md`.

## Unterstützte Versionen

Sicherheitsupdates gibt es für die **aktuelle und die vorherige veröffentlichte Version**. Wer eine ältere Version nutzt,
aktualisiert zuerst über die Zwischenversion (siehe `docs/project/PR144_ENTSCHEIDUNGSVORLAGEN_2026-10-20.md`).
Unterstützt wird **Windows 10 und 11 (x64)**. macOS und Linux sind experimentell und nur per automatischem Test geprüft.

*Dieser Zeitraum ist ein Vorschlag und wird vor dem ersten Verkauf als Supportzeitraum je Version verbindlich festgelegt.*

## Was im Umfang liegt

- Die Anwendung, ihr Updater und die ausgelieferten Pakete.
- Mitgelieferte Bibliotheken (siehe `THIRD_PARTY_NOTICES.txt` und die Stückliste `release-sbom.json` im Release).
- Der Umgang mit lokalen Daten (Lebenslauf, Postfach-Zugang, Kalender-Link) auf dem Gerät.

Nicht im Umfang: Lücken in den Diensten Dritter (Jobportale, Mailanbieter), die wir nicht betreiben. Wir leiten solche
Meldungen auf Wunsch weiter.

## Selbst prüfen

Jedes Release enthält eine Stückliste (SBOM) mit Python- und nativen Bibliotheken, Modellen und Datensätzen sowie die
Prüfsummen der Pakete. Die CI führt bei jedem Stand `pip-audit`, OSV, Bandit und Gitleaks aus.
