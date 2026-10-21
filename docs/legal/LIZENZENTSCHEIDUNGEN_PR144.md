# Lizenzentscheidungen für das ausgelieferte Paket (T08.05.03, T08.05.04, T08.05.07)

Stand 2026-10-21. Entscheidung und Begründung durch Claude Code, von Damiano zum Abwägen ermächtigt.
Das ist eine technische und logische Einordnung nach den Lizenztexten, keine Rechtsberatung. Wo eine
Entscheidung offen für Widerspruch ist, steht das ausdrücklich dabei.

## 1. Ausgangspunkt: Karrierekrake steht unter GPL-3.0-or-later

`NOTICE` und `LICENSE` nennen GPL-3.0-or-later. Das ist keine freie Wahl: Teile der Jobquellen-Adapter sind aus
JobRadar (GPL-3.0) übernommen. Dadurch gilt für alles, was wir ausliefern:

- Das Programm als Ganzes darf nur unter GPL-3.0 weitergegeben werden. Wir dürfen es verkaufen, müssen aber jedem
  Empfänger den vollständigen Quelltext geben oder anbieten und dürfen die Rechte nicht weiter einschränken.
- Jede Komponente, die wir einbinden, muss mit GPL-3.0 verträglich sein. Wo eine Komponente mehrere Lizenzen zur
  Wahl anbietet, wählen wir die verträgliche. **GPL-2.0-only ist mit GPL-3.0 nicht verträglich und scheidet aus.**
- Bedingung für jede Veröffentlichung: Das Repository mit dem exakten Release-Stand muss öffentlich erreichbar sein
  (Tag oder Commit), sonst ist der Quelltext-Anspruch nicht erfüllt. Diese Freigabe liegt bei Damiano (T14.05).

## 2. T08.05.03 – Qt und PySide6 (6.11.2)

**Angebotene Lizenzen** der PySide6-/shiboken6-Wheels: LGPL-3.0-only ODER GPL-2.0-only ODER GPL-3.0-only (dazu
eine kommerzielle Qt-Lizenz, deren Text `LicenseRef-Qt-Commercial.txt` in den Wheels liegt).

**Wahl: LGPL-3.0-only.**

| Option | Urteil |
|---|---|
| Kommerzielle Qt-Lizenz | nicht erworben, nicht gewählt; ihr Text wird nicht ausgeliefert |
| GPL-2.0-only | mit GPL-3.0-or-later nicht verträglich |
| GPL-3.0-only | möglich; würde aber Qt fest an das Gesamtwerk binden und verlangt dieselben Quellpflichten ohne Vorteil |
| **LGPL-3.0-only** | verträglich, hält Qt als austauschbare Bibliothek getrennt, Pflichten unten |

**Pflichten und wie sie erfüllt sind**

| Pflicht (LGPL-3.0) | Erfüllung |
|---|---|
| Lizenztext und Hinweis auf die Nutzung | `THIRD_PARTY_NOTICES.txt` im Paket: Abschnitt „Qt / PySide6: license choice and source availability“ mit dem LGPL-3.0-Text; der GPL-3.0-Text, auf den die LGPL verweist, ist die mitgelieferte `LICENSE` |
| Quelltext von Qt/PySide6 | Der Abschnitt nennt den exakten Stand (Qt 6.11.2 bei download.qt.io, PySide6 bei code.qt.io, Tag v6.11.2) |
| Nutzer muss Qt austauschen können (§4 d) | siehe unten, je Plattform |
| Keine Technik, die das Austauschen verhindert | keine Sperre, kein DRM; Dateien liegen offen im Paket bzw. werden aus der Quelle neu gebaut |

**Austauschbarkeit je Plattform**

- *Linux:* Qt liegt als getrennte `.so`-Dateien im Paketordner. Austausch durch eine kompatible Qt-Version genügt.
- *macOS:* Qt liegt als getrennte Bibliotheken im `.app`. Austausch ist möglich; danach muss der Nutzer das Bundle neu
  signieren (ad-hoc genügt). Es gibt keine Gerätesperre.
- *Windows:* Das Paket ist eine einzelne EXE (PyInstaller onefile), die ihre Bibliotheken beim Start entpackt. Eine
  „bereits auf dem Rechner vorhandene Kopie“ (§4 d 1) nutzt sie dabei nicht. Die Pflicht ist deshalb über §4 d 0
  erfüllt: Das Programm ist selbst GPL, der vollständige Quelltext, die gepinnten Abhängigkeiten
  (`constraints-runtime.txt`, `PySide6==6.11.2`) und der Bauweg (`build.bat`, `packaging/Karrierekrake.spec`) sind
  öffentlich, der Nutzer kann Anwendung und eine geänderte Qt-Version neu verbinden und eine neue EXE bauen. Die
  Anleitung steht in den Notices. **Offener Punkt für Damiano:** Wer Qt auf Windows ohne Neubau austauschen können
  soll, braucht zusätzlich ein Ordner-Paket (onedir). Rechtlich verlangt wird das nicht; es wäre großzügiger.

## 3. T08.05.07 – Copyleft-Quellen und eigene Patches

**Eigene Patches an fremden Komponenten gibt es nicht.** Das ist geprüft: keine `*.patch`-Dateien, kein Patch-Schritt
im Bau oder in der CI. `tests/test_copyleft_sources.py` schlägt fehl, sobald einer auftaucht; dann muss diese Aussage
und das Angebot angepasst werden.

**Selbst gebaute Komponenten sind festgeschrieben:** OpenSSL 4.0.3 und cryptography 50.0.2 für Intel-macOS
(`packaging/intel_crypto_sources.json`, URL und SHA-256), CPython-Archive (`packaging/ci_python_runtimes.json`, URL,
SHA-256, Lizenztext-Hash). Der Bau läuft in der öffentlichen CI aus dem Repository.

**Quellangebot im Paket.** Jedes Paket enthält im Abschnitt „source availability of copyleft components“ für jede
Komponente mit Copyleft-Lizenz (Python-Distributionen) und für jedes Ubuntu-Paket (alle liefern Quelltext) die exakte
Version und den Fundort der Quelle, dazu das schriftliche Angebot (drei Jahre, über das Repository). Die CI prüft am
gebauten Paket, dass jede Komponente der SBOM dort einen Eintrag hat (`scripts/ci_license_review_check.py`).

**Einordnung der Copyleft-Komponenten im Paket**

| Komponente | Lizenz | Wahl / Folge |
|---|---|---|
| Qt, PySide6, shiboken6 | LGPL-3.0 / GPL-2.0 / GPL-3.0 | LGPL-3.0-only, Abschnitt 2 |
| caldav 3.3.1 | GPL-3.0-or-later ODER Apache-2.0 | GPL-3.0-or-later, passt zum Gesamtwerk |
| icalendar-searcher 1.0.6 | AGPL-3.0-or-later | verträglich mit GPL-3.0 (GPL-3 §13). Die Netzwerkklausel greift nicht, solange niemand das Programm entfernt als Dienst nutzt; sollte Karrierekrake je als Server betrieben werden, muss der Quelltext den Nutzern dieses Dienstes angeboten werden. Quelle im Angebot |
| recurring-ical-events, x-wr-timezone | LGPL-3.0-or-later | reiner Python-Code, Quelle im Angebot, als Quelle austauschbar |
| certifi | MPL-2.0 | unverändert, Datei-Copyleft, Quelle im Angebot |
| libidn2 (in der Linux-Wheel von curl_cffi) | GPL-2.0-or-later ODER LGPL-3.0-or-later | über GPL-2.0-or-later im GPL-3-Gesamtwerk; Quelle über curl_cffi |
| self_cell | Apache-2.0 ODER GPL-2.0-only | Apache-2.0 (GPL-2.0-only scheidet aus) |
| Ubuntu-Bibliotheken (nur Linux) | verschiedene, u. a. LGPL | getrennte `.so`; Quelle: `apt-get source <Paket>=<Version>`; Copyright-Text je Paket im Paket |
| PyInstaller-Bootloader | GPL-2.0-or-later mit Ausnahme | Ausnahme erlaubt die Nutzung, Gesamtwerk ist ohnehin GPL |
| Microsoft UCRT / Visual-C++-Laufzeit (nur Windows) | Microsofts Weitergabebedingungen | unverändert mitgeliefert; für die GPL Systembibliothek (Compiler-/OS-Laufzeit) |

## 4. T08.05.04 – native Dateien mit Lizenz und Quellversion verknüpfen

Eine native Datei ohne Lizenzangabe ihrer Python-Distribution wird **verknüpft, nie geraten**. Die SBOM trägt dafür
`kk:license-evidence`:

- `distro-copyright:<Paket>`: gehört zu einem Ubuntu-Paket; die exakte Paketversion steht in der SBOM, der
  Copyright-Text des Pakets steht in den Notices.
- `python-license-file:CPython`: gehört zur CPython-Laufzeit; deren `LICENSE.txt` (mit den Lizenzen der
  eingebundenen Software) steht in den Notices, die Archivversion ist per Hash festgeschrieben.
- `ms-redistributable:<Familie>`: Microsoft-Laufzeitdatei, eigener Notice-Abschnitt. Dateien wie
  `PySide6\MSVCP140.dll` bekommen damit nicht mehr fälschlich die Qt-Lizenz.

Die CI prüft, dass jede so verknüpfte Datei ihren Text im Paket hat und nicht zugleich als ungeklärt geführt wird.
**Ungeklärt bleibt**, was keine dieser Quellen hat (zum Beispiel in Wheels eingebettete Fremdbibliotheken wie
libwebp oder OpenBLAS); das bleibt als `native:`/`embedded-*` in `license-review.json` sichtbar und ist Teil der
offenen Inventare (T06.05.07.x). Eine Rechtefreigabe ersetzt das nicht (T08.07).
