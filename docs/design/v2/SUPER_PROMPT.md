# KARRIEREKRAKE V2 — FINAL UI/UX IMPLEMENTATION SUPER PROMPT

Du arbeitest jetzt am FINALEN V2-UI-REFACTOR von KarriereKrake.

WICHTIG:
Diese Aufgabe beginnt erst, nachdem alle geplanten Funktions-PRs, Bugfixes und Issue-Fixes abgeschlossen und in den aktuellen Main-Branch integriert wurden.

Das aktuelle Repository zum Zeitpunkt der Ausführung ist daher die verbindliche Quelle für den tatsächlichen Funktionsumfang.

ZIEL:
Die bestehende PySide6-Anwendung soll vollständig auf das neue KarriereKrake-V2-Design umgestellt werden, OHNE bestehende funktionierende Features zu verlieren, zu vereinfachen oder unbeabsichtigt zu verändern.

Dies ist primär ein UI-/UX-Refactor.

Kein Produkt-Neubau.
Kein Backend-Neubau.
Keine Feature-Reduktion.
Keine Interpretation der HTML-Mockups als Funktionsspezifikation.


============================================================
1. DIE WICHTIGSTE REGEL
============================================================

DIE HTML-MOCKUPS DEFINIEREN DAS AUSSEHEN.

DAS REPOSITORY DEFINIERT DIE FUNKTIONALITÄT.

Oder anders:

HTML = WIE KarriereKrake aussehen und sich anfühlen soll.

Repository = WAS KarriereKrake tatsächlich können muss.

Diese Trennung ist verbindlich.


============================================================
2. HTML-MOCKUPS SIND NUR DESIGNREFERENZEN
============================================================

Die bereitgestellten V2-HTML-Dateien sind visuelle Designreferenzen.

Sie definieren unter anderem:

- Layout
- Informationshierarchie
- Farben
- Typografie
- Spacing
- Cards
- Buttons
- Inputs
- Sidebar
- Tabellen
- Listen
- Split Views
- Modals
- Drawer
- Statusdarstellungen
- Empty States
- Loading States
- Error States
- Review States
- allgemeines Look & Feel

Sie definieren NICHT:

- den tatsächlichen Funktionsumfang
- Backend-Architektur
- Datenmodelle
- bestehende Business Logic
- verfügbare APIs
- tatsächliche Integrationen
- tatsächliche Statuswerte
- alle vorhandenen Einstellungen
- alle vorhandenen Buttons
- alle vorhandenen Workflows
- alle vorhandenen Sicherheitsmechanismen

Beispieldaten aus den HTML-Dateien wie:

- Namen
- Firmen
- Jobs
- Prozentwerte
- Gehälter
- Nachrichten
- Bewerbungsstatus
- Kalenderdaten
- Ansprechpartner

sind reine Mock-Daten.

NIEMALS statisch übernehmen.


============================================================
3. REPOSITORY = SINGLE SOURCE OF TRUTH FÜR FUNKTIONEN
============================================================

Bevor irgendein bestehender UI-Code entfernt oder ersetzt wird:

Analysiere den AKTUELLEN Main-Branch vollständig.

Inventarisiere alle Endnutzerfunktionen.

Dazu gehören ausdrücklich:

- Buttons
- Aktionen
- Kontextaktionen
- Filter
- Sortierungen
- Einstellungen
- Dialoge
- Importfunktionen
- Sicherheitsfunktionen
- Suchfunktionen
- Bewerbungsvorbereitung
- Bewerbungsausführung
- Review-Funktionen
- Lifecycle-Funktionen
- Mailfunktionen
- Zuordnungsfunktionen
- Follow-ups
- Erinnerungen
- Interviewfunktionen
- Kalenderfunktionen
- Integrationen
- Profilfunktionen
- CV-Funktionen
- Diagnosefunktionen
- Tray-Funktionen
- Wizard / First Run
- Fehlerzustände
- Offline-Zustände
- Hintergrundprozesse
- alle weiteren tatsächlich vorhandenen Endnutzerfunktionen

Verlasse dich NICHT auf alte Dokumentation, wenn der aktuelle Code etwas anderes sagt.

Der aktuelle Code gewinnt.


============================================================
4. ZUERST FEATURE-PRESERVATION-MATRIX
============================================================

BEVOR du produktiven UI-Code änderst:

Erstelle eine vollständige Feature-Preservation-Matrix.

Jede bestehende Endnutzerfunktion muss genau einem V2-Ziel zugeordnet werden.

Verwende diese Kategorien:

KEEP
= bleibt funktional und ungefähr am bisherigen Ort.

MOVE
= bleibt vollständig erhalten, erhält aber einen neuen UI-Ort.

REDESIGN
= Funktion bleibt erhalten, Darstellung/Bedienung wird modernisiert.

MERGE
= mehrere UI-Einstiege werden sinnvoll zusammengeführt, Funktion bleibt vollständig erhalten.

HIDE FROM NORMAL UI
= technische/fortgeschrittene Funktion bleibt vorhanden, wird aber z.B. unter Einstellungen > Erweitert / Diagnose verschoben.

REMOVE
= nur erlaubt, wenn es in diesem Auftrag ausdrücklich genehmigt wurde.

UNKNOWN / NEEDS DECISION
= nicht selbst entscheiden.

Wenn eine bestehende Funktion keinen eindeutigen V2-Zielort besitzt:

STOP.

Nicht löschen.
Nicht verstecken.
Nicht selbst erfinden.

Dokumentiere den Konflikt.


============================================================
5. KEIN FEATURE DARF WEGEN EINES MOCKUPS VERSCHWINDEN
============================================================

Wenn eine Funktion im Repository existiert, aber im HTML-Mockup nicht gezeigt wird:

DIE FUNKTION BLEIBT.

Das Fehlen im Mockup bedeutet NICHT, dass sie entfernt werden darf.

Finde innerhalb der V2-Informationsarchitektur einen passenden Ort.

Wenn das nicht eindeutig möglich ist:

STOP und dokumentieren.


============================================================
6. KEINE MOCKUP-FUNKTION ERFINDEN
============================================================

Wenn ein HTML-Mockup eine Funktion suggeriert, die das aktuelle Repository NICHT besitzt:

NICHT automatisch implementieren.

Beispiele:

- Fake-Backend-Funktion
- nicht vorhandene API
- nicht vorhandene Gmail-Schreibfunktion
- nicht vorhandene Routingberechnung
- Fake-Fortschrittswert
- vermeintliche neue Automatisierung

HTML ist dafür keine Autorisierung.

Nur bestehende oder ausdrücklich geplante Repository-Funktionalität implementieren.


============================================================
7. KEIN HTML-/TAILWIND-PORT
============================================================

Die HTML-Dateien werden NICHT technisch nachgebaut.

Insbesondere NICHT:

- HTML in die App einbetten
- Tailwind übernehmen
- Browser-UI simulieren
- WebView als Ersatz für PySide6 verwenden
- CSS 1:1 übertragen
- externe Google-Fonts zur Laufzeit laden
- Demo-Iconbibliotheken als Abhängigkeit übernehmen

KarriereKrake bleibt eine echte PySide6-Desktop-Anwendung.

Übersetze lediglich die VISUELLE SPRACHE der Mockups in saubere, wiederverwendbare PySide6-Komponenten.


============================================================
8. EIN EINZIGES PYSIDE6 DESIGN SYSTEM
============================================================

Erstelle NICHT pro Seite eigene Styles.

Baue EIN zentrales Designsystem.

Beispielsweise logisch getrennt in:

- Design Tokens
- Typography
- Colors
- Spacing
- Radius
- Shadows
- Buttons
- Inputs
- Cards
- Status Chips
- Tabs
- Tables
- Lists
- Sidebar
- Header
- Modal
- Drawer
- Toasts / Banners
- Empty States
- Loading States
- Error States

Bestehende Projektstruktur berücksichtigen.

Keine unnötige Architektur nur um der Architektur willen.

Aber:

Gleiche Komponente = gleiche Implementierung.


============================================================
9. VISUELLE ZIELSPRACHE
============================================================

Die bereits akzeptierte V2-Designsprache ist verbindlich.

Grundfarben:

Navy:
#132238

Teal:
#18A999

Teal Hover:
#148F82

Background:
#F8FAFC

White:
#FFFFFF

Orange:
#E86A45

Orange nur sparsam für Branding/Akzent.

Keine unnötigen zusätzlichen dominanten Markenfarben.


============================================================
10. TYPOGRAFIE
============================================================

Verwende für die echte App ein konsistentes Desktop-Typografiesystem.

Designziel:

Inter bzw. eine technisch saubere lokale/systemgeeignete Umsetzung mit passendem Fallback.

WICHTIG:

Keine externe Webfont-Abhängigkeit zur Laufzeit.

Falls Inter bereits sauber als Projektressource vorhanden ist, verwende sie.

Ansonsten sichere lokale/systembasierte Lösung wählen.

KEINE FONT-DATEIEN aus externen Quellen eigenmächtig ins Projekt kopieren, wenn das lizenz-/deploymentseitig nicht geklärt ist.

Definiere zentral:

- Page Title
- Page Subtitle
- Section Title
- Card Title
- Body
- Secondary Text
- Label
- Button
- Table Header
- Status Text

Desktop-first.

Keine riesigen SaaS-/Mobile-Headlines.


============================================================
11. BRANDING / ICONS
============================================================

Die HTML-Demo-Icons sind NICHT verbindlich.

Die echten KarriereKrake-Assets existieren bereits bzw. befinden sich im Projekt:

- Werbebild
- Logo/Icon
- App-Icon

Suche zuerst nach den tatsächlich vorhandenen Projektassets.

Bestehende Branding-Assets NICHT durch Demo-Platzhalter ersetzen.

Kein neues Logo erzeugen.

Kein neues App-Icon erzeugen.

Keine neue Markenidentität erfinden.

Für normale UI-Symbole:

verwende ein EINHEITLICHES internes System.

Nicht verschiedene Iconsets wild mischen.

Die Demo-SVGs dienen nur als visuelle Orientierung.


============================================================
12. HAUPTNAVIGATION V2
============================================================

Ziel-Hauptnavigation:

Übersicht
Jobs
Bewerbungen
Postfach
Profil

Unterer Sidebar-Bereich:

Einstellungen
Hilfe

Nicht mehr als eigene Hauptnavigation:

Lebenszyklus
Protokolle

ABER:

Die Funktionen dieser alten Bereiche dürfen NICHT verschwinden.

Sie müssen anhand der Feature-Preservation-Matrix sinnvoll verteilt werden.


============================================================
13. LEBENSZYKLUS-FUNKTIONEN VERTEILEN
============================================================

Der alte Bereich „Lebenszyklus“ soll nicht mehr als eigener Hauptbereich notwendig sein.

Seine tatsächlichen Funktionen werden kontextuell verteilt.

Beispiele:

Bewerbungsdetail:

- Timeline
- Status
- Follow-up
- Kommunikation
- Dokumente
- nächste Aktion
- Interviewinformationen
- relevante Lifecycle-Ereignisse

Postfach:

- eingehende Nachrichten
- automatische Zuordnung
- unsichere Zuordnung
- manuelle Zuordnung
- Antwortentwürfe

Interview:

- Vorbereitung
- Terminvorschläge
- Verfügbarkeit
- ICS
- Kalenderfreigabe

NIEMALS Lifecycle-Funktionen löschen, nur weil die alte Seite verschwindet.


============================================================
14. PROTOKOLLE / DIAGNOSE
============================================================

Technische Logs gehören nicht mehr in die Hauptnavigation.

Verschiebe/integriere sie sinnvoll unter:

Einstellungen
>
Erweitert / Diagnose

Bestehende Diagnosemöglichkeiten erhalten.

Technische Informationen dürfen vorhanden sein, sollen aber normalen Nutzern nicht permanent im Gesicht stehen.


============================================================
15. ÜBERSICHT / DASHBOARD
============================================================

Designziel:

ruhiges persönliches Bewerbungs-Cockpit.

Keine technische Kontrollzentrale.

Beibehalten:

- dominante Aktion „Jobs suchen“
- Action Queue / nächste wichtige Aktionen
- vier Haupt-KPIs

Vorgesehene Haupt-KPIs:

- Passende Jobs
- Prüfung nötig
- Bewerbungen
- Antworten

KEINE fest verdrahteten Demo-Werte.

KEIN fest verdrahtetes „75%“.

Werte dynamisch aus realem Zustand beziehen.

Technische Run-Statistiken nicht prominent darstellen.

Wenn sinnvoll:

Erweitert / Diagnose.


============================================================
16. SUCHE LÄUFT
============================================================

Keine erfundenen Fortschrittswerte.

NICHT:

„Günther sucht (45%)“

wenn das Backend keinen echten 45%-Fortschritt liefert.

Stattdessen:

- Günther sucht …
- Jobsuche läuft …
- Spinner
- indeterminate Progress
- echte Phasen / Quellenstatus

Beispiele nur wenn real verfügbar:

- Bundesagentur wird durchsucht
- Indeed abgeschlossen
- Treffer werden bewertet
- Duplikate werden geprüft

Abbrechen muss während eines abbrechbaren Laufs sichtbar und funktional bleiben.


============================================================
17. JOBS
============================================================

V2-Grundlayout:

ungefähr 60/40 Split.

Links:

Jobliste.

Rechts:

Detailansicht.

Oben:

kompakte Such-/Filterleiste.

Beibehalten bzw. aus Repo korrekt anbinden:

- Titel
- Firma
- Ort
- Quelle
- Match
- Distanz
- Arbeitsmodell
- Status
- Gehalt falls vorhanden
- Beschreibung
- Matchgründe
- Ablehnungs-/Gegenargumente
- Original öffnen
- Bewerbung vorbereiten
- reale bestehende Filter
- reale bestehende Sortierungen

Keine vorhandenen Filter verlieren.


============================================================
18. SUCHPARAMETER ≠ ERGEBNISFILTER ≠ SORTIERUNG
============================================================

Diese drei Dinge logisch trennen.

SUCHPARAMETER:

beeinflussen, wonach gesucht wird.

ERGEBNISFILTER:

beeinflussen, welche bereits gefundenen Jobs angezeigt werden.

SORTIERUNG:

ändert ausschließlich die Reihenfolge.

Sortierung darf niemals Ergebnisse verwerfen.


============================================================
19. SORTIERUNG
============================================================

Soweit vom realen Datenmodell unterstützt:

Match:
- hoch → niedrig
- niedrig → hoch

Entfernung:
- nah → weit
- weit → nah

Datum:
- neu → alt
- alt → neu

Gehalt:
- hoch → niedrig
- niedrig → hoch

Bei Gehalt:

Jobs ohne verwertbare Gehaltsdaten nach vorhandenen Gehaltswerten sortieren.

Keine Fantasiewerte erzeugen.


============================================================
20. ENTFERNUNG
============================================================

Prüfe den aktuellen Backend-Stand.

Solange tatsächlich Haversine/Luftlinie verwendet wird:

UI darf NICHT behaupten:

- Fahrstrecke
- Fahrzeit
- echter Arbeitsweg

Verwende:

- Entfernung
- Max. Entfernung
- 30 km · Luftlinie

Nur wenn inzwischen ein echtes Routing-Backend implementiert wurde, darf die UI entsprechend angepasst werden.


============================================================
21. KEINE-TREFFER-ZUSTAND
============================================================

Ein hilfreicher No-Result-State.

Wenn technisch verfügbar:

- Anzahl geprüfter Jobs
- Umkreis temporär erhöhen
- Filter anpassen
- verworfene Jobs ansehen

Wenn „Umkreis +5 km“ verwendet wird:

nur aktuellen Suchlauf beeinflussen, sofern der Nutzer die Änderung nicht ausdrücklich dauerhaft speichert.

Keine stillen Preference-Änderungen.


============================================================
22. BEWERBUNGSVORSCHAU
============================================================

Zwei klar getrennte Ebenen:

A)
WAS AN DEN ARBEITGEBER GEHT

z.B.:

- Formularwerte
- Anschreiben
- CV
- Dokumente
- tatsächliche übermittelte Angaben

B)
INTERNE KARRIEREKRAKE-HINWEISE

z.B.:

- Match
- Warnungen
- fehlende Informationen
- Validierung
- Ansprechpartnerstatus
- Hinweise

Technische Rohdaten nur sekundär / eingeklappt / Diagnose.

Keine Backend-Interna permanent in der normalen Vorschau anzeigen.


============================================================
23. BEWERBUNGEN
============================================================

Standardansicht muss auch bei vielen Bewerbungen funktionieren.

Bevorzugt:

kompakte Liste/Tabelle.

Bestehende Statusfilter und Funktionen vollständig erhalten.

Statusnamen nutzerfreundlich darstellen.

Keine internen Enums ungefiltert anzeigen.


============================================================
24. BEWERBUNGSDETAIL
============================================================

Das Bewerbungsdetail wird zentraler Kontextbereich.

Je nach real vorhandener Funktionalität:

- Jobdaten
- Status
- Timeline
- Dokumente
- Kommunikation
- Follow-up
- Erinnerungen
- Ansprechpartner
- Antworten
- nächste Aktion
- Interview
- relevante Lifecycle-Ereignisse

Alles aus dem tatsächlichen Repo ableiten.


============================================================
25. POSTFACH
============================================================

Postfach wird ein vollwertiger Hauptbereich.

Darstellen:

- eingehende Bewerbungsnachrichten
- Zuordnungsstatus
- zugehörige Bewerbung
- Nachricht
- Entwurf / nächste Aktion

Bestehende automatische Zuordnung erhalten.

Unsicherheit NICHT verstecken.

Bei mehrdeutiger Zuordnung:

keine stille Best-Match-Entscheidung.

Nutzerreview beibehalten.


============================================================
26. GMAIL
============================================================

Prüfe den tatsächlichen aktuellen Integrationsstand im Repository.

Wenn Gmail weiterhin read-only ist:

KEINE Schreib-/Sendefunktion vortäuschen.

NICHT:

„In Gmail senden“

oder ähnliche Funktion, wenn keine echte Backend-Funktion existiert.

Stattdessen z.B.:

- Entwurf vorbereiten
- Entwurf übernehmen
- Text kopieren

Nur echte vorhandene Fähigkeiten darstellen.


============================================================
27. KONSEQUENTIELLE AKTIONEN
============================================================

Besonders sensible Aktionen müssen vorhandene Safety-/Review-Regeln respektieren.

Beispiele:

- Bewerbung absenden
- Bewerbung zurückziehen
- Angebot ablehnen
- Kalender schreiben
- Daten löschen

Nicht versehentlich durch das Redesign bestehende Sicherheitsgates umgehen.


============================================================
28. INTERVIEW
============================================================

Bestehende Interviewfunktionen kontextuell und ruhig darstellen.

Je nach aktuellem Backend:

- erkannte Interviewanfrage
- Vorbereitung
- Talking Points
- Fragen
- Zeitfenster
- vorgeschlagene Slots
- Verfügbarkeitsprüfung
- Kalender
- ICS
- Antwortentwurf

Keine Termine erfinden.

Keine Kalenderaktion ohne erforderliche Freigabe.


============================================================
29. PROFIL
============================================================

V2-Prinzip:

READ-FIRST.

NICHT:

riesige Formularwand.

Standardansicht:

übersichtliche Karten / Abschnitte.

Bearbeitung nur bei Bedarf über:

- Edit Mode
- Drawer
- Modal
- strukturierte Editor-Komponenten

Bestehende Profilfelder vollständig erhalten.

Keine Datenfelder verlieren, nur weil sie im Mockup nicht gezeigt wurden.


============================================================
30. SUCHINTENT UND PROFIL NICHT VERWECHSELN
============================================================

Profilinformationen und operative Jobsuche sind nicht automatisch dasselbe.

Bestehende Trennung im Backend respektieren.

Profilbeweise/Qualifikationen dürfen nicht still Suchrollen erweitern.

Suchparameter gehören primär in den Jobs-/Suchbereich.

Profil bleibt Nutzerprofil.


============================================================
31. CV IMPORT
============================================================

Bestehende Replace-/Merge-Funktionalität erhalten.

Konflikte nicht still überschreiben.

Manuell gepflegte Daten bevorzugt schützen, sofern dies der bestehenden Logik entspricht.

Import klar und verständlich darstellen.

Technische Confidence-Werte nicht unnötig als Hauptinformation zeigen.


============================================================
32. EINSTELLUNGEN
============================================================

Settings sollen nur Einstellungen enthalten, die wirklich zur App/System-/Automationskonfiguration gehören.

Sinnvolle Bereiche:

- Allgemein
- Automation
- Kommunikation & Termine
- Integrationen
- Daten & Datenschutz
- Erweitert / Diagnose

Suchparameter gehören überwiegend zur Jobsuche, nicht in allgemeine Settings.


============================================================
33. GÜNTHER
============================================================

Günther ist Bestandteil von KarriereKrake.

Nicht als separates Produkt behandeln.

Kein großer Chatbot-UI-Zwang.

Keine normale Nutzeroption:

„Günther an/aus“

wenn Günther systemisch benötigt wird.

Keine LLM-Modellauswahl im normalen UI.

Keine Begriffe wie:

- Phi
- Qwen
- GGUF-Modell

im normalen Nutzerinterface.

Technische Modellinformationen höchstens Diagnose/Entwicklung, wenn überhaupt nötig.


============================================================
34. GÜNTHER-STATUS
============================================================

Nur anzeigen, wenn sinnvoll.

Beispiele:

- Günther arbeitet …
- Aktion benötigt
- Offline
- Fehler

Idle darf sehr dezent oder gar nicht dargestellt werden.

Keine permanente Animation, die Aktivität vortäuscht.


============================================================
35. ONBOARDING
============================================================

Bestehenden First-Run-Wizard respektieren.

V2 soll ihn vereinfachen, nicht funktional zerstören.

Grundidee:

1. Profil / CV
2. Suchziel
3. Arbeitsweise / Start

Keine gefährliche Vollautomation als ungefragter Default.

Bestehende Safety-Mechanismen und Dry-Run-Regeln respektieren.


============================================================
36. STATES
============================================================

Jeder wichtige Bereich braucht saubere Zustände.

Mindestens prüfen:

- First Use
- No Data
- No Results
- Loading
- Success
- Warning
- Error
- Offline
- Partial Failure
- Review Required
- Disabled
- Empty Integration

State-Gallery-Mockups dienen hierfür als visuelle Referenz.


============================================================
37. DESIGN SYSTEM DETAILS
============================================================

Grundstil:

- ruhiges Desktop-UI
- kompakt
- professionell
- wenig visuelles Rauschen
- klare Hierarchie
- progressive disclosure
- technische Details nur bei Bedarf

Cards:

- White
- dezente Border
- subtile Shadows
- ungefähr 12px Radius

Controls:

- ungefähr 8px Radius
- konsistente Höhe
- konsistenter Focus Ring

Spacing:

verwende eine konsistente Skala, z.B.:

4
8
12
16
24
32
40

Nicht jede Seite individuell erfinden.


============================================================
38. BUTTON-HIERARCHIE
============================================================

Zentral definieren:

PRIMARY

SECONDARY

TERTIARY / GHOST

DESTRUCTIVE

Pro Bereich normalerweise nur eine dominante Primary Action.

Nicht zehn gleich starke Buttons nebeneinander.


============================================================
39. ACCESSIBILITY
============================================================

Achte auf:

- sichtbaren Keyboard Focus
- sinnvolle Tab-Reihenfolge
- ausreichenden Kontrast
- keine Information nur durch Farbe
- sinnvolle Klickflächen
- keine wichtige Funktion ausschließlich über Hover
- lesbare Schriftgrößen
- sinnvolle Tooltips

Mouse Wheel darf bei fokussierten Number Controls nicht ungewollt kritische Werte verändern, wenn dies vermeidbar ist.


============================================================
40. RESPONSIVE / ADAPTIVE DESKTOP UI
============================================================

KarriereKrake ist Desktop-first.

Die UI soll ungefähr bei typischen Größen wie:

1180 × 760

gut funktionieren.

Aber auch kleinere Fenster wie ungefähr:

900 × 650

dürfen nicht unbenutzbar werden.

Verwende:

- Splitter
- Scrollbereiche
- vernünftige Mindestgrößen
- adaptive Breiten

Keine abgeschnittenen kritischen Aktionen.


============================================================
41. TECHNISCHE DATEN NICHT VERSTECKEN, SONDERN RICHTIG PLATZIEREN
============================================================

Wichtige Diagnoseinformationen dürfen weiterhin existieren.

Aber:

Komplexität darf im Programm existieren, ohne permanent im Gesicht des Nutzers zu sein.

Leitsatz:

„Die V2-UI darf niemals Backend-Konfiguration einfach sichtbar machen, nur weil sie existiert.“

Technische Details gehören:

- unter Erweitert
- Diagnose
- ausklappbare Details
- Logs

nicht in normale Primäransichten.


============================================================
42. TRAY / WINDOW BEHAVIOR
============================================================

Bestehendes Tray- und Window-Verhalten erhalten.

Zum Beispiel, sofern aktuell vorhanden:

- Minimieren in Tray
- Suche starten
- Pause
- Resume
- Exit
- Close Confirmation während laufender Prozesse
- Window State Persistence

UI-Redesign darf diese Funktionen nicht beschädigen.


============================================================
43. KEINE PARALLELEN KONFLIKT-REFACTORS
============================================================

Diesen UI-Umbau NICHT als mehrere gleichzeitig konkurrierende große UI-PRs durchführen.

Keine parallelen Agenten, die gleichzeitig dieselben:

- Pages
- Shared Widgets
- Styles
- Navigation
- Main Window

ändern.

Arbeite sequenziell und kontrolliert.

Der UI-Refactor besitzt viele gemeinsame Abhängigkeiten.

Merge-Konflikte und unterschiedliche Interpretationen des Designsystems müssen vermieden werden.


============================================================
44. EMPFOHLENE IMPLEMENTIERUNGSREIHENFOLGE
============================================================

PHASE 0
Repository prüfen.

- aktueller Main
- Tests
- Working Tree sauber
- bestehenden Funktionsumfang inventarisieren

PHASE 1
Feature-Preservation-Matrix erstellen.

Noch KEINE UI löschen.

PHASE 2
Zentrales PySide6 Designsystem erstellen.

- Tokens
- Typography
- Colors
- Shared Widgets
- Sidebar
- Header
- Buttons
- Inputs
- Cards
- Chips
- States

PHASE 3
App Shell / Navigation migrieren.

PHASE 4
Übersicht migrieren.

PHASE 5
Jobs migrieren.

PHASE 6
Bewerbungen + Bewerbungsdetail migrieren.

PHASE 7
Postfach + Zuordnung + Antwortentwürfe migrieren.

PHASE 8
Interviewfunktionen integrieren.

PHASE 9
Profil + Edit + CV Import migrieren.

PHASE 10
Settings + Diagnose migrieren.

PHASE 11
Onboarding migrieren.

PHASE 12
Alle Empty/Loading/Error/Offline/Review States.

PHASE 13
Regression / E2E / Accessibility / Window Sizes.

Nicht alles blind auf einmal ersetzen.


============================================================
45. NACH JEDER PHASE TESTEN
============================================================

Nach jeder Phase:

- App startet
- Navigation funktioniert
- keine Import Errors
- keine Signal/Slot-Fehler
- keine verlorenen Funktionen
- relevante Tests laufen
- betroffener Workflow manuell/synthetisch prüfbar
- keine offensichtlich defekten Widgets

Erst danach nächste Phase.


============================================================
46. KEINE BLINDEN DELETE-AKTIONEN
============================================================

Bevor alte:

- Page
- Widget
- Setting
- Button
- Signal
- Slot
- Helper
- Backend Function

entfernt werden:

Dependency Check.

Suche nach:

- imports
- references
- signals
- callbacks
- tests
- config keys
- database relations
- tray hooks
- automation hooks

Erst löschen, wenn sicher kein benötigter Pfad mehr davon abhängt.


============================================================
47. KEINE FUNKTION DURCH „SCHÖNERES UX“ VEREINFACHEN
============================================================

Beispiele:

Nicht:

„Dieser Filter macht die UI voll, also entfernen.“

Sondern:

„Dieser Filter bleibt, wird aber unter Weitere Filter verschoben.“

Nicht:

„Dieser technische Zustand sieht hässlich aus, also verstecken.“

Sondern:

„Nutzerfreundlichen Zustand anzeigen und Details optional zugänglich machen.“

Form follows function.


============================================================
48. KEINE HARD-CODED DEMO-WERTE
============================================================

Insbesondere NICHT hardcoden:

75%
60%
45%
30 km
Firmen
Personen
Jobs
Antwortzahlen
Bewerbungszahlen
Statuszahlen

Mockupwerte sind Beispiele.

UI muss reale Werte aus App State / DB / Config verwenden.


============================================================
49. SHARED COMPONENTS
============================================================

Die Datei:

20_global_components.html

dient als visuelle Komponentenreferenz.

Aber:

NICHT technisch kopieren.

Erstelle die entsprechenden zentralen PySide6-Komponenten.

Normale Pages dürfen nicht jeweils eigene leicht andere Varianten erzeugen.


============================================================
50. AKZEPTANZKRITERIUM VISUELLE KONSISTENZ
============================================================

Vergleiche am Ende mindestens:

- Übersicht
- Jobs
- Bewerbungen
- Bewerbungsdetail
- Postfach
- Profil
- Einstellungen

Frage:

„Würde ein Nutzer sofort erkennen, dass alle Screens aus exakt derselben Desktop-Anwendung stammen?“

Es müssen konsistent sein:

- Sidebar
- Typography
- Header
- Buttons
- Inputs
- Cards
- Chips
- Tables
- Tabs
- Modals
- Drawer
- Focus States
- Spacing
- Radius
- Shadows
- Empty States
- Loading States


============================================================
51. AKZEPTANZKRITERIUM FUNKTIONSERHALT
============================================================

Am Ende muss jede Funktion der Feature-Preservation-Matrix einen überprüften Status besitzen.

Keine:

UNKNOWN

Keine:

LOST

Keine:

ACCIDENTALLY REMOVED

Kein bestehender Workflow darf allein wegen des Redesigns verschwunden sein.


============================================================
52. REGRESSIONSTEST
============================================================

Nach kompletter UI-Migration den gesamten Nutzerfluss prüfen:

START / ONBOARDING

→ PROFIL

→ JOBSUCHE

→ MATCHING

→ JOB AUSWÄHLEN

→ BEWERBUNG VORBEREITEN

→ REVIEW / FREIGABE

→ BEWERBUNGSSTATUS

→ EINGEHENDE MAIL

→ MAIL ZUORDNEN

→ ANTWORTENTWURF

→ FOLLOW-UP / REMINDER

→ INTERVIEW

→ TERMIN / ICS / KALENDERFREIGABE

→ LIFECYCLE / ABSCHLUSS

Zusätzlich:

- Fehlerzustände
- Offline
- Teilfehler
- Abbruch
- Pause
- Tray
- Neustart
- Persistenz
- Diagnose


============================================================
53. KEINE AUTOMATISCHE „ERFOLG“-BEHAUPTUNG
============================================================

Am Ende NICHT einfach schreiben:

„Alles fertig.“

Belege den Abschluss.

Liefere:

1. Feature-Preservation-Matrix final
2. geänderte Dateien
3. entfernte Dateien + Begründung
4. Tests
5. E2E-Ergebnisse
6. bekannte Restprobleme
7. manuell zu testende Punkte
8. Screens/Pages, die erfolgreich migriert wurden
9. Bestätigung, dass keine UNKNOWN-Matrix-Einträge verbleiben

Wenn etwas nicht verifiziert werden konnte:

klar als UNVERIFIED markieren.


============================================================
54. WICHTIGER ARBEITSGRUNDSATZ
============================================================

KarriereKrake soll sich für den Nutzer einfach anfühlen, obwohl intern viel passiert.

Leitsatz:

„Die Komplexität darf im Programm existieren – aber sie muss nicht im Gesicht des Nutzers existieren.“

UND:

„Die V2-UI darf niemals Backend-Konfiguration einfach sichtbar machen, nur weil sie existiert.“

UND:

„Gemini zeigt, wie KarriereKrake aussehen und sich anfühlen soll.
Das Repository sagt, was KarriereKrake können muss.
Die V2-Implementierung verbindet beides.“


============================================================
55. START
============================================================

Beginne NICHT sofort mit dem Umschreiben der Pages.

Dein erster Schritt ist:

1. aktuellen Repository-Stand analysieren
2. existierende UI + Funktionen inventarisieren
3. Feature-Preservation-Matrix erstellen
4. Zielarchitektur für gemeinsame PySide6-Komponenten festlegen
5. Konflikte/UNKNOWN-Einträge identifizieren

Wenn keine blockierenden UNKNOWN-Punkte existieren:

beginne anschließend sequenziell mit der Implementierung.

Wenn blockierende UNKNOWN-Punkte existieren:

STOP vor destruktiven Änderungen und liste ausschließlich diese Entscheidungen auf.

Keine bestehenden Funktionen eigenmächtig entfernen.

BEGINNE JETZT MIT PHASE 0.