AUFGABE: CV-PARSER VOLLSTAENDIG PRUEFEN, REPARIEREN UND PHI OBJEKTIV BEWERTEN
================================================================================

Arbeite autonom im vorhandenen Karrierekrake-Repository. Analysiere nicht nur,
sondern fuehre den echten Parser aus, repariere die Ursachen gefundener Fehler,
schreibe Regressionstests und wiederhole den gesamten Test ab Schritt 1, bis der
gewaehlte Produktionspfad alle 10 PDFs fehlerfrei verarbeitet.

TESTDATEIEN
-----------
Nutze diese 10 PDFs als unveraenderliche Black-Box-Fixtures:

- DE_01_Klassisch.pdf
- DE_02_Zweispaltig_Trap.pdf
- DE_03_C1_Kontextfalle.pdf
- DE_04_Unvollstaendige_Kontaktdaten.pdf
- DE_05_Zweiseitig.pdf
- EN_01_Classic_Resume.pdf
- EN_02_Two_Column_Trap.pdf
- EN_03_Missing_Address_Fields.pdf
- EN_04_German_Address_English_CV.pdf
- EN_05_Skills_Heavy.pdf

Verbindliches vollstaendiges Loesungsblatt:
- CV_Parser_Sollwerte_Vollstaendig.txt

Das vorhandene expected_results.json darf als zusaetzliche alte Teil-Referenz
verwendet werden, ist aber nicht vollstaendig. Bei Abweichungen oder fehlenden
Feldern ist CV_Parser_Sollwerte_Vollstaendig.txt massgeblich.

UNVERHANDELBARE REGELN
----------------------
1. Veraendere weder die PDFs noch das Loesungsblatt, um Tests gruen zu bekommen.
2. Programmiere keine Namen, Dateinamen, Arbeitgeber, Ueberschriften, Adressen,
   exakten Testwerte oder dokumentbezogenen Sonderfaelle fest in den Parser.
3. Ein Fix muss allgemein fuer deutsche und englische Lebenslaeufe funktionieren.
4. Fehlende Werte bleiben null/leer. Es darf nichts erfunden, aus E-Mail/Ort/PLZ
   abgeleitet oder aus anderen Abschnitten uebernommen werden.
5. Dokumenttitel und Abschnittsueberschriften duerfen nicht als Werte erscheinen.
6. Behebe Ursachen im echten Produktionspfad. Kein separates Testskript, das die
   richtige Ausgabe am eigentlichen Parser vorbei konstruiert.
7. Bereits funktionierende PDFs duerfen durch einen Fix nicht schlechter werden.
8. Zaehle einen Test nur dann als bestanden, wenn alle Werte, Zuordnungen, leeren
   Felder und Listen stimmen - nicht nur Name, Kontaktangaben oder Listenanzahlen.

SCHRITT 1 - ECHTEN PARSERPFAD FINDEN
------------------------------------
- Ermittle den Einstiegspunkt, den die Anwendung beim realen CV-Import verwendet.
- Dokumentiere knapp: PDF-Textextraktion/OCR, Layoutbehandlung, regelbasierte
  Erkennung, Phi-Aufruf, Nachbearbeitung, Validierung und Mapping ins Profilmodell.
- Suche alle Konfigurationen, Feature-Flags und Fallbacks, die Phi aktivieren oder
  umgehen. Verwende fuer den A/B-Test denselben Produktionspfad und aendere nur
  Phi an/aus. Erfinde keine Phi-Integration, falls im Repository keine existiert.

SCHRITT 2 - REPRODUZIERBAREN BASELINE-TEST BAUEN
------------------------------------------------
- Fuehre alle 10 PDFs nacheinander durch den echten Parser.
- Starte mit sauberem temporaerem Zustand/Cache, damit kein frueheres Resultat
  wiederverwendet wird.
- Speichere fuer jedes Dokument die rohe Parserausgabe und eine normalisierte
  Vergleichsausgabe. Behalte dabei den Rohwert fuer die Fehlerdiagnose.
- Der Comparator darf nur technisch normalisieren: Gross-/Kleinschreibung,
  normale Leerzeichen, Bindestrichvarianten und gleichbedeutende Datumsformate.
  Er darf keine fehlenden Inhalte ergaenzen und keine falsche Zuordnung kaschieren.
- Vergleiche jedes atomare Feld aus dem Loesungsblatt, einschliesslich:
  Name, komplette Adresse, E-Mail, Telefon, Geburtsdatum, Profiltext,
  jede Berufsstation mit Zeitraum/Position/Arbeitgeber/Beschreibung,
  jede Ausbildung mit Zeitraum/Abschluss/Institution/Zusatz,
  Sprachen und Niveaus, Fuehrerscheine, Software, Zertifikate/Weiterbildungen,
  Skills, Mobilitaet und Projekt-/Sonderaufgaben.
- Pruefe auch alle mit NICHT VORHANDEN markierten Felder auf null/leer.
- Erstelle dauerhafte automatisierte Regressionstests im bestehenden Testsystem.

SCHRITT 3 - PHI A/B-TEST
------------------------
Fuehre den kompletten Korpus unter ansonsten identischen Bedingungen aus:

A: Phi AUS bzw. vollstaendig umgangen
B: Phi AN im realen vorgesehenen Pfad

Anforderungen an den Vergleich:
- Identische PDFs, Text-/OCR-Eingabe, Parserversion, Normalisierung und
  Konfiguration; einziger beabsichtigter Unterschied ist Phi an/aus.
- Wenn Phi stochastische Parameter besitzt: Temperatur 0, fester Seed soweit
  unterstuetzt. Fuehre jede Variante mindestens dreimal aus, wenn Ausgaben trotz
  deterministischer Einstellungen schwanken, und melde diese Instabilitaet.
- Erfasse je Variante mindestens:
  * exakt bestandene Dokumente von 10
  * korrekt erkannte erwartete atomare Werte
  * fehlende erwartete Werte
  * falsche Werte/falsche Zuordnungen
  * erfundene Werte in erwarteten Leerfeldern
  * falsche zusaetzliche Listeneintraege
  * Laufzeit pro PDF und gesamt
  * Abstuerze/Timeouts/ungueltige strukturierte Antworten
- Liste fuer jedes Feld, das Phi veraendert, den Wert ohne Phi, mit Phi und den
  Sollwert auf. Dadurch muss sichtbar werden, ob Phi einen Fehler repariert oder
  einen neuen Fehler erzeugt.

Entscheidungsregel:
- Phi "hilft" nur, wenn es die fachliche Genauigkeit messbar verbessert und dabei
  weder neue Falschwerte/Halluzinationen noch Regressionen in zuvor korrekten
  Dokumenten erzeugt.
- Bei gleicher Genauigkeit ist die stabilere, schnellere und einfachere Variante
  vorzuziehen.
- Ist der Parser ohne Phi bereits exakt oder ist Phi schlechter/instabiler, Phi
  im Standardpfad deaktivieren bzw. nur dann behalten, wenn ein klar abgegrenzter,
  getesteter Anwendungsfall nachweisbar profitiert.
- Ist Phi Bestandteil eines Fallbacks, darf dieser Fallback keine korrekten,
  hochsicheren regelbasierten Werte ueberschreiben.

SCHRITT 4 - FEHLER BEHEBEN
--------------------------
Erstelle nach jedem Lauf eine Feld-fuer-Feld-Differenz. Ordne jeden Fehler einer
Ursache zu, z. B.:

- falsche Lesereihenfolge bei Zweispaltenlayout
- Seite 2 verloren oder als neues Dokument behandelt
- Dokumenttitel/Ueberschrift als Name oder Wert erkannt
- Kontaktadresse mit Arbeitgeber-/Institutionsadresse verwechselt
- internationale/deutsche Adresse falsch zerlegt
- C1/B1/A2 ohne Abschnittskontext als Fuehrerschein erkannt
- Fuehrerschein C1 im echten Fuehrerscheinabschnitt faelschlich verworfen
- Abschnittsalias nicht erkannt
- Listentrenner, Zeilenumbruch oder Bullet falsch verarbeitet
- Eintraege ueber Abschnittsgrenzen hinweg vermischt
- fehlende Werte halluziniert
- Phi ueberschreibt bessere deterministische Ergebnisse

Behebe die allgemeine Ursache mit moeglichst kleinen, nachvollziehbaren Aenderungen.
Fuege fuer jeden behobenen Fehlertyp mindestens einen Regressionstest hinzu. Teste
nicht nur die zehn exakten Namen, sondern soweit sinnvoll auch kleine synthetische
Varianten, damit der Fix seine Generalisierung beweist.

SCHRITT 5 - KOMPLETT VON VORNE TESTEN UND WIEDERHOLEN
----------------------------------------------------
Nach jeder Codeaenderung:

1. Caches/temporaere Parserresultate entfernen oder sicher umgehen.
2. Unit- und Integrationstests ausfuehren.
3. Alle 10 Original-PDFs erneut durch den echten Produktionspfad schicken.
4. Jeden Wert erneut gegen das vollstaendige Loesungsblatt vergleichen.
5. Phi A/B erneut ausfuehren, wenn die Aenderung Parser-, Phi-, Merge-,
   Confidence- oder Postprocessing-Verhalten beeinflusst.
6. Bei irgendeinem Fehler wieder zu Schritt 4 gehen.

Hoere nicht nach einer Teilverbesserung auf. Der Zyklus endet erst bei einem
vollstaendigen gruenen Endlauf fuer den ausgewaehlten Produktionspfad.

BESONDERS ZU BESTEHENDE FALLEN
------------------------------
- DE_02 und EN_02: Zweispaltenlayout ohne Spaltenvermischung.
- DE_03: C1 bei Sprachen UND als echte Fuehrerscheinklasse korrekt einordnen.
- DE_04 und EN_03: fehlende Kontaktdaten leer lassen, nichts erfinden.
- DE_05: beide Seiten derselben Person zusammenfuehren und die drei Aufgaben von
  Seite 2 erfassen.
- EN_04: englisches Dokument mit deutscher Adresse korrekt zerlegen.
- Titel wie Lebenslauf, Resume, Curriculum Vitae, PROFILE und Bewerbungsprofil
  niemals als Personenname oder inhaltlichen Wert behandeln.

HARTE ABNAHMEKRITERIEN
----------------------
Der Auftrag ist erst fertig, wenn ALLE folgenden Punkte erfuellt sind:

- 10/10 PDFs bestehen den vollstaendigen semantischen Vergleich im gewaehlten
  Produktionsmodus.
- 0 fehlende erwartete Werte.
- 0 falsche Werte oder falsche Zuordnungen.
- 0 erfundene Werte in fehlenden Feldern.
- 0 zusaetzliche falsche Listeneintraege.
- Alle Mengen stimmen und alle Listenelemente sind der richtigen Kategorie
  zugeordnet.
- Alle Fallen oben sind durch Regressionstests abgedeckt.
- Die gesamte bestehende Testsuite bleibt gruen.
- Phi-an und Phi-aus wurden objektiv verglichen; die Entscheidung fuer den
  Standardpfad ist mit konkreten Zahlen belegt.
- Es gibt keine fixture-spezifischen Hardcodings und keine abgeschwaechten Tests.

ABSCHLUSSBERICHT
----------------
Gib am Ende kompakt aus:

1. Endergebnis je PDF (PASS/FAIL; erwartet werden 10 PASS).
2. Gesamtscore und Fehlerzahlen fuer Phi AUS und Phi AN.
3. Klare Entscheidung: Phi standardmaessig verwenden, nur als begrenzten Fallback
   verwenden oder deaktivieren - mit den gemessenen Gruenden.
4. Gefundene Grundursachen und die geaenderten Dateien.
5. Hinzugefuegte Tests und die ausgefuehrten Testbefehle.
6. Bestaetigung, dass der letzte Lauf sauber von vorne ueber alle 10 PDFs lief.

Wenn eine echte externe Blockade besteht (z. B. fehlende Modellgewichte oder eine
nicht installierbare Laufzeit), dokumentiere den exakten Blocker und fuehre alle
ohne diese Abhaengigkeit moeglichen Tests und Reparaturen trotzdem aus. Ein solcher
Blocker darf nicht als PASS oder als Beweis fuer/gegen Phi gewertet werden.
