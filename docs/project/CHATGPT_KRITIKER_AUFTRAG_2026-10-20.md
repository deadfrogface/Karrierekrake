# Prüfauftrag: unabhängige Kritiker-Abnahme von 23 Punkten (Karrierekrake PR 144)

Du bist unabhängiger Kritiker für das Projekt Karrierekrake (lokale Desktop-App für Jobsuche, PySide6/Python,
Linux-Paket mit PyInstaller auf Ubuntu 22.04 gebaut). Ein anderer KI-Assistent (Claude Code) hat die 23 Punkte unten
selbst umgesetzt und darf sie deshalb nicht selbst abnehmen. Du entscheidest je Punkt: **FERTIG** oder **OFFEN**.

## Regeln

1. FERTIG nur, wenn die Begründung für **genau dieses Kriterium** trägt und mit den genannten Quellen nachprüfbar ist.
   Im Zweifel OFFEN. Keine Rechtsberatung, keine Paket- oder Gerätefreigabe ableiten.
2. Prüfe jede Behauptung selbst: Advisory-Text (OSV-Link), ausgelieferte Version und Datei gegen den betroffenen Code.
   Nimm die Begründung nicht als gegeben.
3. Benenne bei OFFEN den konkreten fehlenden Beleg oder den Denkfehler.
4. Schreibe keine Fakten dazu, die du nicht prüfen konntest. Kannst du eine Quelle nicht öffnen, sag das.
5. Kontext, den du nutzen darfst:
   - Im Linux-Paket ist `libgtk-3-0` enthalten, also auch die GTK-Abhängigkeiten (gdk-pixbuf, cairo, pango, glib).
     Vollständige Paketliste: https://github.com/deadfrogface/Karrierekrake/blob/f2a4d052/docs/security/NATIVE_LINUX_ARTIFACT_AUDIT_2026-10-16.json (Feld `queries`).
   - Python-XML (`pyexpat`) nutzt die in CPython gebündelte expat, nicht die System-libexpat 2.4.7. Belegt durch
     https://github.com/deadfrogface/Karrierekrake/blob/f2a4d052/tests/test_linux_pyexpat_bundled.py, in der Linux-CI grün.
   - Eigener Produktcode importiert kein XML-Modul. Prüfbar per Code-Suche im Repo.
   - Gesamtbewertung je CVE: https://github.com/deadfrogface/Karrierekrake/blob/f2a4d052/docs/security/NATIVE_LINUX_CANDIDATE_DISPOSITION_2026-10-20.json
   - Rohdaten der Kandidaten: https://github.com/deadfrogface/Karrierekrake/blob/f2a4d052/docs/security/NATIVE_LINUX_CANDIDATE_TRIAGE_2026-10-17.json
   - Repository (öffentlich): https://github.com/deadfrogface/Karrierekrake/tree/f2a4d052

## Antwortformat (bitte genau so, eine Zeile je Punkt)

```
| ID | Urteil (FERTIG/OFFEN) | Begründung in 1–3 Sätzen | geprüfte Quelle(n) |
```

Danach ein kurzer Absatz „Auffälligkeiten“ für Muster, die mehrere Punkte betreffen (z. B. ein Denkfehler in einer
ganzen Klasse).

## Die 23 Punkte


### Klasse A – nur über einen bösartigen X-Server auslösbar

**T06.05.04.03.36 – UBUNTU-CVE-2026-88807**  
Kriterium: UBUNTU-CVE-2026-88807: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxrender 1:0.9.10-1build4 (libXrender.so.1)  
Advisory: A heap overflow in libXrender before 0.9.13 in RenderQueryPictFormats could be used by malicious X servers to inject code into attached X clients.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-88807  
Begründung (Claude Code): Heap-Überlauf in RenderQueryPictFormats. Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).

**T06.05.04.03.42 – UBUNTU-CVE-2026-93541**  
Kriterium: UBUNTU-CVE-2026-93541: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxi 2:1.8-1build1 (libXi.so.6)  
Advisory: An out-of-bounds read in libXi's XQueryDeviceState() in libXi before 1.8.4 could be used by a  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93541  
Begründung (Claude Code): libXi-Antwortparsing (XI/XI2). Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).

**T06.05.04.03.43 – UBUNTU-CVE-2026-93542**  
Kriterium: UBUNTU-CVE-2026-93542: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxi 2:1.8-1build1 (libXi.so.6)  
Advisory: An out-of-bounds read in libXi's XI2 class parsing via size_classes() and copy_classes() in libXi before 1.8.4 could be used by malicous servers to crash the X client.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93542  
Begründung (Claude Code): libXi-Antwortparsing (XI/XI2). Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).

**T06.05.04.03.44 – UBUNTU-CVE-2026-93543**  
Kriterium: UBUNTU-CVE-2026-93543: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxi 2:1.8-1build1 (libXi.so.6)  
Advisory: An out-of-bounds read in libXi's XI2 class parser in libXi before 1.8.4 could be used by malicious X servers to crash an attached X client.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93543  
Begründung (Claude Code): libXi-Antwortparsing (XI/XI2). Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).

**T06.05.04.03.45 – UBUNTU-CVE-2026-93544**  
Kriterium: UBUNTU-CVE-2026-93544: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxi 2:1.8-1build1 (libXi.so.6)  
Advisory: An out-of-bounds read in libXi's XI2 XIQueryDevice reply parsing in libXi before 1.8.4 can be used by a malicious X server to crash an attached X client.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93544  
Begründung (Claude Code): libXi-Antwortparsing (XI/XI2). Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).

**T06.05.04.03.46 – UBUNTU-CVE-2026-93545**  
Kriterium: UBUNTU-CVE-2026-93545: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxi 2:1.8-1build1 (libXi.so.6)  
Advisory: An out-of-bounds read in libXi's XListInputDevices() in libXi before 1.8.4 could be used by malicious X servers to crash an attached X client.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93545  
Begründung (Claude Code): libXi-Antwortparsing (XI/XI2). Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).

**T06.05.04.03.48 – UBUNTU-CVE-2026-94281**  
Kriterium: UBUNTU-CVE-2026-94281: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxi 2:1.8-1build1 (libXi.so.6)  
Advisory: An out-of-bounds read in libXi's XListInputDevices() class parsing in libXi before 1.8.4 could be used by malicious X servers to crash an attached X client.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-94281  
Begründung (Claude Code): libXi-Antwortparsing (XI/XI2). Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).

**T06.05.04.03.49 – UBUNTU-CVE-2026-94282**  
Kriterium: UBUNTU-CVE-2026-94282: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libxi 2:1.8-1build1 (libXi.so.6)  
Advisory: An out-of-bounds read in libXi's XI2 enter/leave/focus cookie conversion in libXi before 1.8.4 could be used by malicious X server to crash an attached X client.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-94282  
Begründung (Claude Code): libXi-Antwortparsing (XI/XI2). Nur durch einen bösartigen X-Server auslösbar (Antwortparsing im X-Client). Der X-Server ist Teil der lokalen Sitzung des Nutzers; wer ihn kontrolliert, kontrolliert die Sitzung bereits. Karrierekrake verbindet sich nur mit dem DISPLAY der eigenen Sitzung (Qt xcb).


### Klasse B – expat: nur lokale Konfigurationsdateien (fontconfig) als Eingabe

**T06.05.04.03.14 – UBUNTU-CVE-2025-59375**  
Kriterium: UBUNTU-CVE-2025-59375: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Advisory: libexpat in Expat before 2.7.2 allows attackers to trigger large dynamic memory allocations via a small document that is submitted for parsing.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2025-59375  
Begründung (Claude Code): Große Allokationen durch kleines Dokument. System-libexpat 2.4.7 wird im Paket nur von nativen Bibliotheken (fontconfig über Qt) geladen; fontconfig parst lokale, vom Administrator/Nutzer kontrollierte Konfigurationsdateien (/etc/fonts, ~/.config/fontconfig), keine Netzdaten. Python-XML (pyexpat) nutzt die in CPython gebündelte expat: tests/test_linux_pyexpat_bundled.py (linux-pytest, gleiche setup-python-CPython 3.12.15 wie der Linux-Build) prüft version_info > 2.4.7 und kein libexpat.so im ldd von pyexpat. UNSICHER: Welche ausgelieferte Bibliothek libexpat.so.1 lädt, ist nicht per ldd am Paket belegt (fontconfig ist die naheliegende, nicht nachgewiesene Quelle).

**T06.05.04.03.16 – UBUNTU-CVE-2025-66382**  
Kriterium: UBUNTU-CVE-2025-66382: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Advisory: In libexpat through 2.7.3, a crafted file with an approximate size of 2 MiB can lead to dozens of seconds of processing time.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2025-66382  
Begründung (Claude Code): Lange Rechenzeit bei ~2 MiB Datei. System-libexpat 2.4.7 wird im Paket nur von nativen Bibliotheken (fontconfig über Qt) geladen; fontconfig parst lokale, vom Administrator/Nutzer kontrollierte Konfigurationsdateien (/etc/fonts, ~/.config/fontconfig), keine Netzdaten. Python-XML (pyexpat) nutzt die in CPython gebündelte expat: tests/test_linux_pyexpat_bundled.py (linux-pytest, gleiche setup-python-CPython 3.12.15 wie der Linux-Build) prüft version_info > 2.4.7 und kein libexpat.so im ldd von pyexpat. UNSICHER: Welche ausgelieferte Bibliothek libexpat.so.1 lädt, ist nicht per ldd am Paket belegt (fontconfig ist die naheliegende, nicht nachgewiesene Quelle).

**T06.05.04.03.24 – UBUNTU-CVE-2026-41080**  
Kriterium: UBUNTU-CVE-2026-41080: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Advisory: libexpat before 2.8.0 uses insufficient entropy, and thus hash flooding can occur via a crafted XML document.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-41080  
Begründung (Claude Code): Hash-Flooding durch geringe Entropie. System-libexpat 2.4.7 wird im Paket nur von nativen Bibliotheken (fontconfig über Qt) geladen; fontconfig parst lokale, vom Administrator/Nutzer kontrollierte Konfigurationsdateien (/etc/fonts, ~/.config/fontconfig), keine Netzdaten. Python-XML (pyexpat) nutzt die in CPython gebündelte expat: tests/test_linux_pyexpat_bundled.py (linux-pytest, gleiche setup-python-CPython 3.12.15 wie der Linux-Build) prüft version_info > 2.4.7 und kein libexpat.so im ldd von pyexpat. UNSICHER: Welche ausgelieferte Bibliothek libexpat.so.1 lädt, ist nicht per ldd am Paket belegt (fontconfig ist die naheliegende, nicht nachgewiesene Quelle).

**T06.05.04.03.25 – UBUNTU-CVE-2026-45186**  
Kriterium: UBUNTU-CVE-2026-45186: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Advisory: In libexpat before 2.8.1, the computational complexity of attribute name collision checks allows a denial of service via moderately sized crafted XML input.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-45186  
Begründung (Claude Code): Komplexität der Attributnamen-Kollisionsprüfung. System-libexpat 2.4.7 wird im Paket nur von nativen Bibliotheken (fontconfig über Qt) geladen; fontconfig parst lokale, vom Administrator/Nutzer kontrollierte Konfigurationsdateien (/etc/fonts, ~/.config/fontconfig), keine Netzdaten. Python-XML (pyexpat) nutzt die in CPython gebündelte expat: tests/test_linux_pyexpat_bundled.py (linux-pytest, gleiche setup-python-CPython 3.12.15 wie der Linux-Build) prüft version_info > 2.4.7 und kein libexpat.so im ldd von pyexpat. UNSICHER: Welche ausgelieferte Bibliothek libexpat.so.1 lädt, ist nicht per ldd am Paket belegt (fontconfig ist die naheliegende, nicht nachgewiesene Quelle).

**T06.05.04.03.28 – UBUNTU-CVE-2026-77214**  
Kriterium: UBUNTU-CVE-2026-77214: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Advisory: libexpat before commit 13c5f63 contains a heap buffer over-read vulnerability in xmlparse.c. XML_ParseBuffer advances the parse buffer end with parser->m_bufferEnd += len using a caller-supplied length that is not validated against the allocated buffer size, so repeated XML_ParseBuffer calls move m_bufferEnd past the end of the heap allocation and subsequent parsing reads out of bounds. Reaching this path requires a parse buffer to already be present; otherwise XML_ParseBuffer returns XML_ERROR_NO_BUFFER. A buffer is present after a prior call to XML_GetBuffer, either directly (the common case) or indirectly through a prior XML_Parse call that allocates the buffer internally. The over-read discloses adjacent heap memory to the calling application, recovering heap pointers, libc function pointers, and code pointers sufficient to defeat ASLR and build further exploitation primitives.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-77214  
Begründung (Claude Code): XML_ParseBuffer mit vom Aufrufer gelieferter, ungeprüfter Länge (Aufruferfehler nötig). System-libexpat 2.4.7 wird im Paket nur von nativen Bibliotheken (fontconfig über Qt) geladen; fontconfig parst lokale, vom Administrator/Nutzer kontrollierte Konfigurationsdateien (/etc/fonts, ~/.config/fontconfig), keine Netzdaten. Python-XML (pyexpat) nutzt die in CPython gebündelte expat: tests/test_linux_pyexpat_bundled.py (linux-pytest, gleiche setup-python-CPython 3.12.15 wie der Linux-Build) prüft version_info > 2.4.7 und kein libexpat.so im ldd von pyexpat. UNSICHER: Welche ausgelieferte Bibliothek libexpat.so.1 lädt, ist nicht per ldd am Paket belegt (fontconfig ist die naheliegende, nicht nachgewiesene Quelle).

**T06.05.04.03.47 – UBUNTU-CVE-2026-93990**  
Kriterium: UBUNTU-CVE-2026-93990: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Advisory: Expat before 2.8.5 fails to validate that a high surrogate in UTF-16 input is followed by a low surrogate, allowing malformed UTF-16 sequences to be accepted. Attackers can supply UTF-16 encoded XML containing lone high surrogates that consume the following code unit, causing Expat to pass unpaired surrogates to applications built with XML_UNICODE and to silently replace input characters in other builds.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93990  
Begründung (Claude Code): Ungepaarte UTF-16-Surrogate. System-libexpat 2.4.7 wird im Paket nur von nativen Bibliotheken (fontconfig über Qt) geladen; fontconfig parst lokale, vom Administrator/Nutzer kontrollierte Konfigurationsdateien (/etc/fonts, ~/.config/fontconfig), keine Netzdaten. Python-XML (pyexpat) nutzt die in CPython gebündelte expat: tests/test_linux_pyexpat_bundled.py (linux-pytest, gleiche setup-python-CPython 3.12.15 wie der Linux-Build) prüft version_info > 2.4.7 und kein libexpat.so im ldd von pyexpat. UNSICHER: Welche ausgelieferte Bibliothek libexpat.so.1 lädt, ist nicht per ldd am Paket belegt (fontconfig ist die naheliegende, nicht nachgewiesene Quelle).


### Klasse C – nur bei privilegiertem Mounten (SUID mount/nsenter)

**T06.05.04.03.27 – UBUNTU-CVE-2026-76642**  
Kriterium: UBUNTU-CVE-2026-76642: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: util-linux 2.37.2-4ubuntu3.6 (libblkid.so.1); util-linux 2.37.2-4ubuntu3.6 (libmount.so.1); util-linux 2.37.2-4ubuntu3.6 (libuuid.so.1)  
Advisory: util-linux versions through 2.41.5 and 2.42.2 fail to check mount helper exit status before running post-mount hooks, allowing unprivileged users to execute privileged operations on pre-existing filesystems. Attackers can exploit X-mount.idmap or X-mount.owner hooks to clone filesystems with inherited suid bits or modify target inode permissions after a helper fails, achieving privilege escalation.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-76642  
Begründung (Claude Code): Betrifft die SUID-Programme mount(8)/nsenter bzw. deren Hook-Pfad in libmount bei privilegiertem Mounten. Karrierekrake mountet nichts und läuft ohne Privilegien; libblkid/libmount/libuuid werden nur indirekt (glib/GIO) geladen.

**T06.05.04.03.29 – UBUNTU-CVE-2026-78408**  
Kriterium: UBUNTU-CVE-2026-78408: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: util-linux 2.37.2-4ubuntu3.6 (libblkid.so.1); util-linux 2.37.2-4ubuntu3.6 (libmount.so.1); util-linux 2.37.2-4ubuntu3.6 (libuuid.so.1)  
Advisory: The nsenter --join-cgroup option opens the target cgroup.procs file as root and leaves that file descriptor open across later namespace and credential changes and across execve(). Because the kernel checks later cgroup migrations using the credentials from the original open, a program run in an attacker-controlled target can inherit root's ability to move host processes between cgroups. After a privileged operator uses --join-cgroup against that target, an unprivileged user can migrate and terminate unrelated root processes.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-78408  
Begründung (Claude Code): nsenter --join-cgroup (Programm, root). Betrifft die SUID-Programme mount(8)/nsenter bzw. deren Hook-Pfad in libmount bei privilegiertem Mounten. Karrierekrake mountet nichts und läuft ohne Privilegien; libblkid/libmount/libuuid werden nur indirekt (glib/GIO) geladen.

**T06.05.04.03.30 – UBUNTU-CVE-2026-78409**  
Kriterium: UBUNTU-CVE-2026-78409: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: util-linux 2.37.2-4ubuntu3.6 (libblkid.so.1); util-linux 2.37.2-4ubuntu3.6 (libmount.so.1); util-linux 2.37.2-4ubuntu3.6 (libuuid.so.1)  
Advisory: The X-mount.subdir option uses a detached-tree fast path on Linux 6.15 and later and passes the configured subdirectory to open_tree() with AT_SYMLINK_NOFOLLOW. That flag does not stop intermediate symlink traversal or keep resolution inside the newly mounted filesystem. A local unprivileged user with an fstab-authorized X-mount.subdir entry can attach a host path at the intended mountpoint.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-78409  
Begründung (Claude Code): X-mount.subdir beim SUID-mount. Betrifft die SUID-Programme mount(8)/nsenter bzw. deren Hook-Pfad in libmount bei privilegiertem Mounten. Karrierekrake mountet nichts und läuft ohne Privilegien; libblkid/libmount/libuuid werden nur indirekt (glib/GIO) geladen.

**T06.05.04.03.31 – UBUNTU-CVE-2026-78410**  
Kriterium: UBUNTU-CVE-2026-78410: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: util-linux 2.37.2-4ubuntu3.6 (libblkid.so.1); util-linux 2.37.2-4ubuntu3.6 (libmount.so.1); util-linux 2.37.2-4ubuntu3.6 (libuuid.so.1)  
Advisory: A flaw was found in util-linux. Restricted bind mounts take the source path from fstab but do not pin that source before the privileged mount. A local unprivileged user who can replace the authorized source or a writable ancestor can redirect SUID mount(8) to bind another host directory. If the fstab entry also sets X-mount.owner, X-mount.group, or X-mount.mode, root then changes ownership or mode on that redirected inode.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-78410  
Begründung (Claude Code): Restricted bind mounts beim SUID-mount. Betrifft die SUID-Programme mount(8)/nsenter bzw. deren Hook-Pfad in libmount bei privilegiertem Mounten. Karrierekrake mountet nichts und läuft ohne Privilegien; libblkid/libmount/libuuid werden nur indirekt (glib/GIO) geladen.


### Klasse D – betroffener Code nicht in der ausgelieferten Bibliothek

**T06.05.04.03.03 – UBUNTU-CVE-2018-10126**  
Kriterium: UBUNTU-CVE-2018-10126: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: libjpeg-turbo 2.1.2-0ubuntu1 (libjpeg.so.8)  
Advisory: ijg-libjpeg before 9d, as used in tiff2pdf (from LibTIFF) and other products, does not check for a NULL pointer at a certain place in jpeg_fdct_16x16 in jfdctint.c.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2018-10126  
Begründung (Claude Code): jpeg_fdct_16x16 aus IJG libjpeg 9 (SmartScale); libjpeg-turbo 2.1.2 implementiert diese Skalierungs-DCT nicht.

**T06.05.04.03.07 – UBUNTU-CVE-2022-27943**  
Kriterium: UBUNTU-CVE-2022-27943: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: gcc-12 12.3.0-1ubuntu1~22.04.3 (libgcc_s.so.1); gcc-12 12.3.0-1ubuntu1~22.04.3 (libgomp.so.1); gcc-12 12.3.0-1ubuntu1~22.04.3 (libstdc++.so.6)  
Advisory: libiberty/rust-demangle.c in GNU GCC 11.2 allows stack consumption in demangle_const, as demonstrated by nm-new.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2022-27943  
Begründung (Claude Code): libiberty/rust-demangle.c (statisch in binutils/gdb/nm); libstdc++/libgcc_s/libgomp enthalten keinen Rust-Demangler.


### Klasse E – betroffene Funktion vom Produkt nicht aufgerufen

**T06.05.04.03.15 – UBUNTU-CVE-2025-62813**  
Kriterium: UBUNTU-CVE-2025-62813: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: lz4 1.9.3-2build2 (liblz4.so.1)  
Advisory: LZ4 through 1.10.0 allows attackers to cause a denial of service (application crash) or possibly have unspecified other impact when the application processes untrusted LZ4 frames. For example, LZ4F_createCDict_advanced in lib/lz4frame.c mishandles NULL checks.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2025-62813  
Begründung (Claude Code): Fehlende NULL-Prüfungen in LZ4F_createCDict_advanced/LZ4-Frames aus nicht vertrauenswürdiger Quelle. liblz4 wird nur über libsystemd (Journal) geladen; Karrierekrake verarbeitet keine LZ4-Frames.

**T06.05.04.03.35 – UBUNTU-CVE-2026-86469**  
Kriterium: UBUNTU-CVE-2026-86469: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert: glib2.0 2.72.4-0ubuntu2.10 (libgio-2.0.so.0, libglib-2.0.so.0, libgmodule-2.0.so.0, libgobject-2.0.so.0, libgthread-2.0.so.0)  
Advisory: A flaw was found in GLib2. When g_file_replace() is used with G_FILE_CREATE_REPLACE_DESTINATION and creating the .goutputstream-XXXXXX temporary file fails, the library unlinks the destination and recreates it without exclusive creation or symlink protection. A local attacker who can write to the destination directory can win that race and redirect the write to another file.  
OSV: https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-86469  
Begründung (Claude Code): Race in g_file_replace(G_FILE_CREATE_REPLACE_DESTINATION) mit Schreibzugriff des Angreifers auf das Zielverzeichnis. Karrierekrake schreibt Dateien über Python (os/pathlib, atomare .partial+os.replace), nicht über GIO g_file_replace. UNSICHER: GTK-Dateidialog-Pfade nicht einzeln geprüft.


### Klasse F – Markenrecherche

**T14.03**  
Kriterium: Konkrete Namens-/Ähnlichkeits-/Domainrecherche mit Quellen und Datum durchführen  
Beleg: https://github.com/deadfrogface/Karrierekrake/blob/f2a4d052/docs/commercial/BRAND_RESEARCH_PROTOCOL.md (Abschnitt „Register- und Domainrecherche am 20.10.2026“). Prüfe: Sind Methode, Quellen und Datum so dokumentiert, dass die Recherche wiederholbar ist? Gibt es offensichtliche Lücken (z. B. fehlende Register, Varianten oder ähnlich klingende Namen)? Eine Bewertung der Verwechslungsgefahr ist **nicht** Teil dieses Kriteriums (das ist T14.04).
