# Karrierekrake auf macOS und Linux

Alle Desktop-Pakete verwenden dieselbe Python/PySide6-Anwendung, denselben CV-Import und dasselbe lokale Qwen-Modell. Es gibt kein zusätzliches Cloud-Konto.

## Pakete und Installation

- **Apple Silicon:** `Karrierekrake-Alpha-1.0-macOS-AppleSilicon.dmg`, gebaut auf macOS 14 / ARM64.
- **Intel-Mac:** `Karrierekrake-Alpha-1.0-macOS-Intel.dmg`, gebaut auf macOS 15 / x86_64.
- **Linux:** `Karrierekrake-Alpha-1.0-Linux-x86_64.tar.gz`, gebaut auf Ubuntu 22.04 / x86_64. Zunächst Ubuntu 22.04+ und darauf basierende Linux-Mint-Versionen; andere Distributionen sind nicht zugesichert.

macOS: Das passende DMG öffnen, Karrierekrake in „Programme“ ziehen und dort starten. Für diese erste Ausgabe sind keine Developer-ID-Zertifikate und keine Apple-Notarisierung eingerichtet. Ein macOS-Build auf GitHub ist kein Nachweis, dass Gatekeeper die heruntergeladene App ohne zusätzliche Benutzerfreigabe öffnet. Ältere macOS-Versionen sind nicht geprüft.

Linux: Den gesamten Ordner entpacken und die ausführbare Datei `Karrierekrake` darin starten. Den Ordner `_internal` zusammen mit der Anwendung behalten. Bei fehlenden Systembibliotheken unter Ubuntu/Mint:

```sh
sudo apt-get install libegl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libdbus-1-3
```

Bei Systemen ohne grafische Sitzung kann die Desktop-App nicht geöffnet werden. Für sichere Mail-/Kalender-Zugangsdaten braucht Linux einen funktionierenden Secret-Service-Schlüsselbund (z. B. GNOME Keyring). Es gibt keinen Klartext-Ersatz für fehlende sichere Speicherung.

## Daten und Funktionen

Windows verwendet weiterhin `%LOCALAPPDATA%\Karrierekrake`. macOS verwendet `~/Library/Application Support/Karrierekrake`, Linux `$XDG_DATA_HOME/Karrierekrake` oder `~/.local/share/Karrierekrake`. Ein relatives `XDG_DATA_HOME` wird ignoriert. `KARRIEREKRAKE_DATA_DIR` kann einen absoluten isolierten Datenordner festlegen, beispielsweise für Tests.

Der Setuphelfer empfiehlt auf allen Systemen ein Modell aus demselben Hardwarekatalog. Setup und nativer Updatebereich verwenden denselben Installer mit SHA-256-Prüfung und Modellprobe. Bei unzureichendem RAM wird kein Modell erzwungen. Es liegt im Benutzer-Datenordner und bleibt bei Programmupdates erhalten. Anschließend benötigt der Lebenslauf-Import kein Internet. Browserautomation installiert Chromium auf Wunsch einmal in den Benutzerordner. Jobsuche und Anbieteranmeldung benötigen wie unter Windows Internet. Reale Google-/IMAP-/CalDAV-Anmeldungen benötigen weiterhin einen Test mit einem Nutzerkonto; CI benutzt keine echten Zugangsdaten.

Die Zeitplanung verwendet auf macOS einen LaunchAgent und auf Linux systemd-Benutzerdienste. Sie gilt für die angemeldete Benutzer-Sitzung und benötigt keine Administratorrechte. Ohne systemd-Benutzermanager meldet die Oberfläche einen Fehler. Vorhandene Programme/Tasks anderer Anwendungen werden nicht verändert. Die Windows-Aufgabenplanung bleibt bestehen.

## Updates

Windows behält den vorhandenen Komponenten-Updater. macOS/Linux prüfen beim Start und manuell auf Pakete derselben Plattform/Architektur. Der native Installer lädt das vollständige Paket, prüft Größe, SHA-256 und Paketidentität und bereitet den Austausch neben der Installation vor. Nach Bestätigung beendet sich die App; ein Helfer tauscht die Ordner atomar aus. Eine Startquittung bestätigt das neue Programm; fehlt sie, versucht der Helfer den Rücktausch. Der Installationsordner muss beschreibbar sein und das Dateisystem den atomaren Austausch unterstützen. Sonst bleibt das alte Programm bestehen und der Vorgang meldet einen Fehler.

Native Delta-Downloads sind nicht erforderlich: vollständige Pakete sind der konservative Übertragungsweg. Abbruch ist während Transfer/Vorbereitung möglich; der anschließende atomare Austausch wird nicht unterbrochen. Die eigenen Daten und das Modell liegen außerhalb des Programmpakets. Wiederherstellung von Profildaten ist kein Teil des Programm-Rollbacks. Diese Implementierung muss noch auf echten Zielsystemen geprüft werden.

## Deinstallation

Vorher bei Bedarf in Einstellungen ein Backup in einen anderen Ordner erstellen und prüfen. Konten in der App trennen, damit verwaltete Schlüsselbund-Einträge entfernt werden. „Alle Daten löschen“ beseitigt app-eigene Daten; separat gespeicherte Exporte, Original-Lebensläufe und Backups bleiben erhalten. App schließen und unter Windows/Linux den entpackten Programmordner bzw. unter macOS die App entfernen. Eine lokale Lizenzlöschung oder Deinstallation kündigt keinen Vertrag beim Zahlungsanbieter. Geplante App-Aufgaben zuvor in der App deaktivieren; keine fremden Tasks oder Schlüsselbund-Einträge löschen.

## Build- und Release-Gates

`Desktop Platforms` baut auf Ubuntu 22.04, macOS 14 ARM64 und macOS 15 Intel. Die Workflow-Matrix führt Plattform-/Updater-/Packaging-Regressionen aus, kompiliert das gepinnte llama.cpp ohne CPU-native Compileroptimierung, provisioniert das geprüfte GGUF und den registrierten Google-Desktop-Client, baut die native Anwendung und testet das **fertige Binary** mit Qt-Smoke sowie Offline-DE/EN-Lebenslauf-Import mit dem verifizierten Modell im isolierten Benutzer-Datenordner (Zustand nach Ersteinrichtung). Einzelne Release-Dateien bleiben unter GitHubs 2-GiB-Grenze.

`Publish component update` wartet auf CI, Windows Smoke **und** Desktop Platforms für denselben aktuellen main-Commit und baut anschließend die geprüften Windows-Komponenten als internes Artefakt. `Publish Karrierekrake Alpha` erstellt daraus und aus den passenden nativen Artefakten **einen** Release „Karrierekrake Alpha 1.0“. Der Release bleibt ein Entwurf, bis alle vier Downloads (Windows, Mac Apple Silicon, Mac Intel, Linux) und deren Update-Manifeste hochgeladen sind. Bei einem fehlgeschlagenen Build oder Upload erscheint kein unvollständiger öffentlicher Release. Alte öffentliche Windows-Releases bleiben erhalten.

Ein gemeinsamer Versionswert (`core/release_identity.py`) legt Titel, Programmversion und eindeutige Dateinamen fest. Die Core-Funktionen, das Modell und der Quellcode-Commit sind identisch. Pakete enthalten keine Anwendungsversion eines anderen Betriebssystems. Der Windows-Updater akzeptiert nur sein Komponentenmanifest und lädt nur dessen Programm-/Modellteile; macOS/Linux prüfen zusätzlich das tatsächliche Laufzeitsystem und die CPU-Architektur und fragen nur ihr eigenes Manifest ab. Die Mac-Architekturen bleiben getrennte Downloads, damit nicht beide heruntergeladen werden.

Die macOS-Builds, der Qt-Start und der lokale Lebenslauf-Import werden auf echten macOS-GitHub-Runnern ausgeführt. Dafür ist kein Apple-Gerät des Entwicklers erforderlich. Die fehlende Developer-ID-Notarisierung kann beim Download weiterhin eine Gatekeeper-Freigabe erforderlich machen.

Lokale Quellcode-Smoke-Tests ersetzen diese nativen Build-Gates nicht. Zusätzlich zu den GitHub-Tests bleiben für eine spätere breitere Freigabe noch interaktive Tests sinnvoll: Gatekeeper/Installation, GUI-Sitzung auf Ubuntu/Mint, Schlüsselbundzugriff, Anbieterlogin, Browserautomation und Schreiben eines Anschreibens im verpackten Programm.
