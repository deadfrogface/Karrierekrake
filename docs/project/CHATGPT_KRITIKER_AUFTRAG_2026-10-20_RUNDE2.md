# Prüfauftrag: unabhängige Kritiker-Abnahme von 22 Linux-Punkten (Karrierekrake PR 144, Runde 2)

Du bist unabhängiger Kritiker für das Projekt Karrierekrake (lokale Desktop-App für Jobsuche, PySide6/Python,
Linux-Paket mit PyInstaller auf Ubuntu 22.04 gebaut). In der ersten Runde (Stand `f2a4d052`) hast du 15 dieser Punkte
als OFFEN bewertet, weil Bedrohungsmodell-Annahmen („nur bösartiger X-Server“, „nur lokale Konfiguration“, „nicht
erreichbar“) keinen Nachweis ersetzen. Claude Code hat daraufhin nicht weiter argumentiert, sondern die betroffenen
Bibliotheken aus dem Linux-Paket entfernt bzw. auf die Host-Bibliothek umgestellt. Sieben weitere offene Punkte
(cairo, pixman, gdk-pixbuf) fallen mit derselben Änderung weg. Claude Code hat die Änderung selbst umgesetzt und darf sie
deshalb nicht selbst abnehmen. Du entscheidest je Punkt: **FERTIG** oder **OFFEN**.

## Regeln

1. FERTIG nur, wenn die Begründung für **genau dieses Kriterium** trägt und mit den genannten Quellen nachprüfbar ist.
   Im Zweifel OFFEN. Keine Rechtsberatung, keine Paket- oder Gerätefreigabe ableiten.
2. Prüfe jede Behauptung selbst: liegt der betroffene Code wirklich in der entfernten Datei, ist die Entfernung im
   Paket belegt, und greift die Regression bei einem Rückfall? Nimm die Begründung nicht als gegeben.
3. Benenne bei OFFEN den konkreten fehlenden Beleg oder den Denkfehler.
4. Schreibe keine Fakten dazu, die du nicht prüfen konntest. Kannst du eine Quelle nicht öffnen, sag das.

## Was geändert wurde (Stand `b8386a34`)

- Ursache: PyInstaller sammelte Qts Plugin `platformthemes/libqgtk3.so` ein und mit ihm GTK 3, GDK, cairo, pango,
  pixman, gdk-pixbuf, libXi, libXrender u. a. vom Build-Host. GIO (`libgio-2.0.so.0`) kam zusätzlich über das
  QNetworkInformation-Backend `networkinformation/libqglib.so`.
- Umsetzung: Beide Plugins werden entfernt, dazu jede Bibliothek, die vorher per DT_NEEDED erreichbar war und
  danach nicht mehr. Bibliotheken, die nie über DT_NEEDED erreichbar waren (dlopen), bleiben unangetastet.
  `libexpat.so.1` wird gezielt nicht mehr gebündelt; die mitgelieferte fontconfig lädt die libexpat des Hosts.
  Code: [scripts/linux_bundle_libraries.py](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/scripts/linux_bundle_libraries.py),
  Aufruf in [packaging/Karrierekrake.spec](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/packaging/Karrierekrake.spec) (Linux-Block vor
  `export_release_inventory`).
- Folgen für Nutzer: Qt-eigene statt GTK-Dateidialoge; die App braucht auf dem Host die üblichen Desktop-Bibliotheken
  (libexpat, xcb-Pakete), die auf jedem Linux-Desktop vorhanden sind.
- Paketregression in CI ([Workflow](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/.github/workflows/desktop-platforms.yml), Linux):
  - Schritt „Linux bundle without GTK theme, libXi/libXrender, GIO and bundled libexpat (T06.05.04.03)“: bricht ab,
    wenn eine Datei aus `FORBIDDEN_IN_BUNDLE` im fertigen Paket liegt, oder wenn eine DT_NEEDED-Referenz darauf
    (geprüft mit `ldd`) ins Paket oder ins Leere zeigt.
  - Schritt „Actual GUI startup on X11 (xcb under Xvfb) with host libraries“: startet das gebaute Programm über X11;
    die xcb-Hostpakete werden erst **nach** dem Packen installiert, damit PyInstaller sie nicht einsammelt.
  - Beides grün im Lauf [Desktop Platforms 39417740594](https://github.com/deadfrogface/Karrierekrake/actions/runs/39417740594) (Linux-Job [118611183682](https://github.com/deadfrogface/Karrierekrake/actions/runs/39417740594/job/118611183682),
    Commit `180f5a4c`), ebenso Paketierung und Upgrade-Test. Die Job-Logs erfordern einen GitHub-Login; **öffentlich**
    sind die Annotationen des Laufs, darunter „Linux bundle removed“ mit der vollständigen Liste der entfernten
    Dateien (auch per API: `https://api.github.com/repos/deadfrogface/Karrierekrake/check-runs/118611183682/annotations`).
- Tests: [tests/test_linux_bundle_libraries.py](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/tests/test_linux_bundle_libraries.py) (DT_NEEDED-Parser an
  synthetischem ELF, Entfernungslogik, Prüfschritt) und
  [tests/test_native_linux_disposition.py](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/tests/test_native_linux_disposition.py)
  (`test_removed_candidates_are_gated_out_of_the_linux_bundle`: jede neue Einstufung nennt eine Datei, die der
  CI-Prüfschritt sperrt). Alle 21 Checks auf `b8386a34` grün.
- Einstufung je CVE: [Disposition](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/docs/security/NATIVE_LINUX_CANDIDATE_DISPOSITION_2026-10-20.json)
  (Felder `class`, `affected_file`, `reasoning`), Rohdaten:
  [Triage](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/docs/security/NATIVE_LINUX_CANDIDATE_TRIAGE_2026-10-17.json).
- Hinweis: Direkte OSV-Abrufe scheiterten bei dir zuletzt mit HTTP 403; je Punkt ist deshalb auch der CVE.org-Datensatz
  verlinkt.

## Worauf du besonders achten sollst

1. **Entfernung tatsächlich belegt?** Stimmen Sperrliste, Annotation „Linux bundle removed“ und die
   `affected_file` je Punkt überein? Gibt es einen zweiten Weg, über den der betroffene Code doch im Paket landet
   (z. B. statisch in eine andere ausgelieferte Bibliothek gelinkt, oder eine andere Datei mit gleichem Code)?
2. **Richtige Datei?** Liegt die betroffene Routine wirklich in `affected_file`? Beispiel: CVE-2026-86469 betrifft
   `g_file_replace()` in GIO (`libgio-2.0.so.0`, entfernt); `libglib-2.0.so.0` wird weiterhin ausgeliefert.
3. **Host-libexpat (Klasse B):** Das Kriterium verlangt „gegebenenfalls Ursache beheben und Regression im Paket
   bestätigen“. Trägt es als Behebung, dass das Paket keine eigene libexpat mehr enthält und die des Hosts lädt
   (Distributions-Sicherheitsupdates greifen), oder fehlt etwas, z. B. eine Mindestversion? Enthält eine andere
   ausgelieferte Bibliothek expat statisch? (Pythons `pyexpat` nutzt die in CPython gebündelte expat, siehe
   [tests/test_linux_pyexpat_bundled.py](https://github.com/deadfrogface/Karrierekrake/blob/b8386a34/tests/test_linux_pyexpat_bundled.py).)
4. **Regression wirksam?** Würde der CI-Schritt fehlschlagen, wenn eine dieser Bibliotheken auf anderem Weg wieder ins
   Paket käme?

## Antwortformat (bitte genau so, eine Zeile je Punkt)

```
| ID | Urteil (FERTIG/OFFEN) | Begründung in 1–3 Sätzen | geprüfte Quelle(n) |
```

Danach ein kurzer Absatz „Auffälligkeiten“ für Muster, die mehrere Punkte betreffen.

## Die 22 Punkte

### Klasse A – Bibliothek nicht mehr im Linux-Paket (16)

**T06.05.04.03.02 – UBUNTU-CVE-2017-7475**  
Kriterium: UBUNTU-CVE-2017-7475: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: cairo 1.16.0-5ubuntu2.1 (libcairo-gobject.so.2); cairo 1.16.0-5ubuntu2.1 (libcairo.so.2)  
Betroffene Datei laut Einstufung: `libcairo.so.2`  
Advisory: Cairo version 1.15.4 is vulnerable to a NULL pointer dereference related to the FT_Load_Glyph and FT_Render_Glyph resulting in an application crash.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2017-7475 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2017-7475  
Vorheriges Urteil: nicht vorgelegt (bisher OFFEN, Einstufung „Erreichbarkeit unsicher“).  

**T06.05.04.03.04 – UBUNTU-CVE-2018-18064**  
Kriterium: UBUNTU-CVE-2018-18064: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: cairo 1.16.0-5ubuntu2.1 (libcairo-gobject.so.2); cairo 1.16.0-5ubuntu2.1 (libcairo.so.2)  
Betroffene Datei laut Einstufung: `libcairo.so.2`  
Advisory: cairo through 1.15.14 has an out-of-bounds stack-memory write during processing of a crafted document by WebKitGTK+ because of the interaction between cairo-rectangular-scan-converter.c (the generate and render_rows functions) and cairo-image-compositor.c (the _cairo_image_spans_and_zero function).  
Quellen: https://www.cve.org/CVERecord?id=CVE-2018-18064 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2018-18064  
Vorheriges Urteil: nicht vorgelegt (bisher OFFEN, Einstufung „Erreichbarkeit unsicher“).  

**T06.05.04.03.11 – UBUNTU-CVE-2023-37769**  
Kriterium: UBUNTU-CVE-2023-37769: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: pixman 0.40.0-1ubuntu0.22.04.1 (libpixman-1.so.0)  
Betroffene Datei laut Einstufung: `libpixman-1.so.0`  
Advisory: stress-test master commit e4c878 was discovered to contain a FPE vulnerability via the component combine_inner at /pixman-combine-float.c.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2023-37769 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2023-37769  
Vorheriges Urteil: nicht vorgelegt (bisher OFFEN, Einstufung „Erreichbarkeit unsicher“).  

**T06.05.04.03.13 – UBUNTU-CVE-2025-50422**  
Kriterium: UBUNTU-CVE-2025-50422: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: cairo 1.16.0-5ubuntu2.1 (libcairo-gobject.so.2); cairo 1.16.0-5ubuntu2.1 (libcairo.so.2)  
Betroffene Datei laut Einstufung: `libcairo.so.2`  
Advisory: Cairo through 1.18.4, as used in Poppler through 25.08.0, has an "unscaled->face == NULL" assertion failure for _cairo_ft_unscaled_font_fini in cairo-ft-font.c.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2025-50422 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2025-50422  
Vorheriges Urteil: nicht vorgelegt (bisher OFFEN, Einstufung „Erreichbarkeit unsicher“).  

**T06.05.04.03.21 – UBUNTU-CVE-2026-16768**  
Kriterium: UBUNTU-CVE-2026-16768: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: gdk-pixbuf 2.42.8+dfsg-1ubuntu0.5 (libgdk_pixbuf-2.0.so.0)  
Betroffene Datei laut Einstufung: `libgdk_pixbuf-2.0.so.0`  
Advisory: A flaw was found in gdk-pixbuf. When parsing a specially crafted ICO file with pixel values that exceed the defined palette range, an out-of-bounds read can occur due to improper bounds checking against the actual palette size. This vulnerability causes heap bytes to be interpreted as valid palette indices and rendered as RGB pixel values in the output image, allowing an attacker to extract heap content via the generated output, such as a thumbnail.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-16768 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-16768  
Vorheriges Urteil: nicht vorgelegt (bisher OFFEN, Einstufung „Erreichbarkeit unsicher“).  

**T06.05.04.03.22 – UBUNTU-CVE-2026-18090**  
Kriterium: UBUNTU-CVE-2026-18090: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: gdk-pixbuf 2.42.8+dfsg-1ubuntu0.5 (libgdk_pixbuf-2.0.so.0)  
Betroffene Datei laut Einstufung: `libgdk_pixbuf-2.0.so.0`  
Advisory: A flaw was found in gdk-pixbuf. This vulnerability allows a remote attacker to cause a heap out-of-bounds read by providing a specially crafted Apple Icon Image (.icns) file. The uncompress() function, which handles RLE-encoded ICNS icon data, fails to validate the source buffer's boundaries during decompression. This can lead to a denial of service, where the application crashes, or to information disclosure, potentially revealing sensitive data from adjacent memory.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-18090 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-18090  
Vorheriges Urteil: nicht vorgelegt (bisher OFFEN, Einstufung „Erreichbarkeit unsicher“).  

**T06.05.04.03.32 – UBUNTU-CVE-2026-81893**  
Kriterium: UBUNTU-CVE-2026-81893: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: gdk-pixbuf 2.42.8+dfsg-1ubuntu0.5 (libgdk_pixbuf-2.0.so.0)  
Betroffene Datei laut Einstufung: `libgdk_pixbuf-2.0.so.0`  
Advisory: A flaw was found in gdk-pixbuf. When loading a specially crafted JPEG image containing chunked ICC profile markers, an error during ICC profile parsing can leave stale size metadata after the profile buffer is freed. A subsequent allocation in the same decode can cause an out-of-bounds write, potentially crashing the application. To exploit this flaw, an application using gdk-pixbuf must process the malicious JPEG image. Affected version >= 2.26.4  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-81893 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-81893  
Vorheriges Urteil: nicht vorgelegt (bisher OFFEN, Einstufung „Erreichbarkeit unsicher“).  

**T06.05.04.03.35 – UBUNTU-CVE-2026-86469**  
Kriterium: UBUNTU-CVE-2026-86469: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: glib2.0 2.72.4-0ubuntu2.10 (libgio-2.0.so.0, libglib-2.0.so.0, libgmodule-2.0.so.0, libgobject-2.0.so.0, libgthread-2.0.so.0)  
Betroffene Datei laut Einstufung: `libgio-2.0.so.0`  
Advisory: A flaw was found in GLib2. When g_file_replace() is used with G_FILE_CREATE_REPLACE_DESTINATION and creating the .goutputstream-XXXXXX temporary file fails, the library unlinks the destination and recreates it without exclusive creation or symlink protection. A local attacker who can write to the destination directory can win that race and redirect the write to another file.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-86469 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-86469  
Vorheriges Urteil: OFFEN. GLib-Fallback enthält unlink und anschließendes Öffnen ohne exklusive Erstellung; Produkt nutzt native QFileDialog-Aufrufe; GTK-/GIO-Pfade nicht untersucht, Python-Dateischreiben beweist keine Unerreichbarkeit.  

**T06.05.04.03.36 – UBUNTU-CVE-2026-88807**  
Kriterium: UBUNTU-CVE-2026-88807: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxrender 1:0.9.10-1build4 (libXrender.so.1)  
Betroffene Datei laut Einstufung: `libXrender.so.1`  
Advisory: A heap overflow in libXrender before 0.9.13 in RenderQueryPictFormats could be used by malicious X servers to inject code into attached X clients.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-88807 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-88807  
Vorheriges Urteil: OFFEN. Antwortparser in libXrender 0.9.10 ist XRenderQueryFormats (RenderQueryPictFormats ist die Protokollanfrage). Die Annahme 'wer den X-Server kontrolliert, kontrolliert die Sitzung' ersetzt weder belegten Ausschluss des Angriffswegs noch Behebung mit Paketregression.  

**T06.05.04.03.42 – UBUNTU-CVE-2026-93541**  
Kriterium: UBUNTU-CVE-2026-93541: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxi 2:1.8-1build1 (libXi.so.6)  
Betroffene Datei laut Einstufung: `libXi.so.6`  
Advisory: An out-of-bounds read in libXi's XQueryDeviceState() in libXi before 1.8.4 could be used by a  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-93541 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93541  
Vorheriges Urteil: OFFEN. XQueryDeviceState ist in libXi 1.8 enthalten; konkreter Aufrufpfad im ausgelieferten Produkt und belastbare Behandlung des Restrisikos fehlen.  

**T06.05.04.03.43 – UBUNTU-CVE-2026-93542**  
Kriterium: UBUNTU-CVE-2026-93542: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxi 2:1.8-1build1 (libXi.so.6)  
Betroffene Datei laut Einstufung: `libXi.so.6`  
Advisory: An out-of-bounds read in libXi's XI2 class parsing via size_classes() and copy_classes() in libXi before 1.8.4 could be used by malicous servers to crash the X client.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-93542 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93542  
Vorheriges Urteil: OFFEN. size_classes/copy_classes in der geprüften Quellversion vorhanden; X-Server-Vertrauensannahme belegt weder Unerreichbarkeit noch Eingabeprüfung; Paketregression fehlt.  

**T06.05.04.03.44 – UBUNTU-CVE-2026-93543**  
Kriterium: UBUNTU-CVE-2026-93543: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxi 2:1.8-1build1 (libXi.so.6)  
Betroffene Datei laut Einstufung: `libXi.so.6`  
Advisory: An out-of-bounds read in libXi's XI2 class parser in libXi before 1.8.4 could be used by malicious X servers to crash an attached X client.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-93543 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93543  
Vorheriges Urteil: OFFEN. XI2-Klassenparser enthalten; tatsächlicher Aufruf durch die ausgelieferten Qt-/GTK-Komponenten nicht untersucht.  

**T06.05.04.03.45 – UBUNTU-CVE-2026-93544**  
Kriterium: UBUNTU-CVE-2026-93544: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxi 2:1.8-1build1 (libXi.so.6)  
Betroffene Datei laut Einstufung: `libXi.so.6`  
Advisory: An out-of-bounds read in libXi's XI2 XIQueryDevice reply parsing in libXi before 1.8.4 can be used by a malicious X server to crash an attached X client.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-93544 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93544  
Vorheriges Urteil: OFFEN. XIQueryDevice verarbeitet Serverantworten über die Klassenparser; Aussage zum eigenen DISPLAY genügt nicht als Nachweis.  

**T06.05.04.03.46 – UBUNTU-CVE-2026-93545**  
Kriterium: UBUNTU-CVE-2026-93545: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxi 2:1.8-1build1 (libXi.so.6)  
Betroffene Datei laut Einstufung: `libXi.so.6`  
Advisory: An out-of-bounds read in libXi's XListInputDevices() in libXi before 1.8.4 could be used by malicious X servers to crash an attached X client.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-93545 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93545  
Vorheriges Urteil: OFFEN. XListInputDevices in libXi 1.8 vorhanden; Produkt-Aufrufpfad bzw. dessen Ausschluss und Nachweis sicherer Behandlung fehlen.  

**T06.05.04.03.48 – UBUNTU-CVE-2026-94281**  
Kriterium: UBUNTU-CVE-2026-94281: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxi 2:1.8-1build1 (libXi.so.6)  
Betroffene Datei laut Einstufung: `libXi.so.6`  
Advisory: An out-of-bounds read in libXi's XListInputDevices() class parsing in libXi before 1.8.4 could be used by malicious X servers to crash an attached X client.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-94281 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-94281  
Vorheriges Urteil: OFFEN. Klassenverarbeitung in XListInputDevices Bestandteil der Quelle; eingeschränktes Angreifermodell allein erledigt Erreichbarkeits-/Behebungsnachweis nicht.  

**T06.05.04.03.49 – UBUNTU-CVE-2026-94282**  
Kriterium: UBUNTU-CVE-2026-94282: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: libxi 2:1.8-1build1 (libXi.so.6)  
Betroffene Datei laut Einstufung: `libXi.so.6`  
Advisory: An out-of-bounds read in libXi's XI2 enter/leave/focus cookie conversion in libXi before 1.8.4 could be used by malicious X server to crash an attached X client.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-94282 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-94282  
Vorheriges Urteil: OFFEN. wireToEnterLeave in XExtInt.c enthalten; ausgelieferte Aufrufer nicht untersucht, Paketnachweis fehlt.  

### Klasse B – libexpat wird vom Host geladen (6)

**T06.05.04.03.14 – UBUNTU-CVE-2025-59375**  
Kriterium: UBUNTU-CVE-2025-59375: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Betroffene Datei laut Einstufung: `libexpat.so.1`  
Advisory: libexpat in Expat before 2.7.2 allows attackers to trigger large dynamic memory allocations via a small document that is submitted for parsing.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2025-59375 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2025-59375  
Vorheriges Urteil: OFFEN. Getrennte Python-expat-Kopie klärt nicht die Eingaben der gebündelten System-libexpat; 'nur fontconfig, nur vertrauenswürdige Konfiguration' ohne vollständigen Nachweis der nativen Verbraucher; version_info > 2.4.7 beweist keinen Fix dieser CVE.  

**T06.05.04.03.16 – UBUNTU-CVE-2025-66382**  
Kriterium: UBUNTU-CVE-2025-66382: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Betroffene Datei laut Einstufung: `libexpat.so.1`  
Advisory: In libexpat through 2.7.3, a crafted file with an approximate size of 2 MiB can lead to dozens of seconds of processing time.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2025-66382 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2025-66382  
Vorheriges Urteil: OFFEN. Eingabegrenzen und vollständige Zuordnung aller nativen expat-Verbraucher fehlen; pyexpat-Test prüft weder diesen Angriff noch die ausgelieferte libexpat.so.1.  

**T06.05.04.03.24 – UBUNTU-CVE-2026-41080**  
Kriterium: UBUNTU-CVE-2026-41080: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Betroffene Datei laut Einstufung: `libexpat.so.1`  
Advisory: libexpat before 2.8.0 uses insufficient entropy, and thus hash flooding can occur via a crafted XML document.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-41080 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-41080  
Vorheriges Urteil: OFFEN. Salz-/Hash-Verarbeitung in der Quelle vorhanden; CVE-spezifische Absicherung im Ubuntu-Patchstand und ausschließliche Verwendung für vertrauenswürdige Dateien nicht belegt.  

**T06.05.04.03.25 – UBUNTU-CVE-2026-45186**  
Kriterium: UBUNTU-CVE-2026-45186: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Betroffene Datei laut Einstufung: `libexpat.so.1`  
Advisory: In libexpat before 2.8.1, the computational complexity of attribute name collision checks allows a denial of service via moderately sized crafted XML input.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-45186 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-45186  
Vorheriges Urteil: OFFEN. Konkreter Abgleich der Attribut-Kollisionsprüfung und der erreichbaren XML-Eingaben fehlt.  

**T06.05.04.03.28 – UBUNTU-CVE-2026-77214**  
Kriterium: UBUNTU-CVE-2026-77214: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Betroffene Datei laut Einstufung: `libexpat.so.1`  
Advisory: libexpat before commit 13c5f63 contains a heap buffer over-read vulnerability in xmlparse.c. XML_ParseBuffer advances the parse buffer end with parser->m_bufferEnd += len using a caller-supplied length that is not validated against the allocated buffer size, so repeated XML_ParseBuffer calls move m_bufferEnd past the end of the heap allocation and subsequent parsing reads out of bounds. Reaching this path requires a parse buffer to already be present; otherwise XML_ParseBuffer returns XML_ERROR_NO_BUFFER. A buffer is present after a prior call to XML_GetBuffer, either directly (the common case) or indirectly through a prior XML_Parse call that allocates the buffer internally. The over-read discloses adjacent heap memory to the calling application, recovering heap pointers, libc function pointers, and code pointers sufficient to defeat ASLR and build further exploitation primitives.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-77214 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-77214  
Vorheriges Urteil: OFFEN. fontconfig (fcxml.c) begrenzt die übergebene Länge auf den angeforderten Puffer; damit ist nur dieser Aufrufer untersucht, die vollständige Verbraucherliste der System-expat fehlt.  

**T06.05.04.03.47 – UBUNTU-CVE-2026-93990**  
Kriterium: UBUNTU-CVE-2026-93990: betroffene Routine und genaue ausgelieferte Quellversion abgleichen, Produkteingang/Erreichbarkeit prüfen, gegebenenfalls Ursache beheben und Regression im Paket bestätigen  
Ausgeliefert bis zur Änderung: expat 2.4.7-1ubuntu0.9 (libexpat.so.1)  
Betroffene Datei laut Einstufung: `libexpat.so.1`  
Advisory: Expat before 2.8.5 fails to validate that a high surrogate in UTF-16 input is followed by a low surrogate, allowing malformed UTF-16 sequences to be accepted. Attackers can supply UTF-16 encoded XML containing lone high surrogates that consume the following code unit, causing Expat to pass unpaired surrogates to applications built with XML_UNICODE and to silently replace input characters in other builds.  
Quellen: https://www.cve.org/CVERecord?id=CVE-2026-93990 · https://api.osv.dev/v1/vulns/UBUNTU-CVE-2026-93990  
Vorheriges Urteil: OFFEN. Abgleich des Ubuntu-Patchstands für fehlerhafte UTF-16-Sequenzen und Nachweis der erreichbaren Verbraucher fehlen; separates Python-expat schließt den Fehler nicht aus.  
