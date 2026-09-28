# Anschreiben-Gold: erzeugte Briefe

Die Briefe wurden auf Commit `d8f21c19be0e4609c82303a19e1f4e64a078778e` erzeugt.
Das ist der Stand des Codes, aus dem die Texte kommen.
Der Dump-Commit ändert nur diese Datei; sein Eltern-Commit ist dieser SHA.

Enthalten ist jeder Gold-Fall mit Ausgang `interview`.
Anzeige (Titel, Firma, Beschreibung) und Profilfakten stehen wörtlich aus der Fixture.
Der Brief ist `compose_cover_letter(...).text`, also der Text,
den `approve_cover_letter` ohne nachträgliche Änderung speichert.

## cl-01-dispatch-hafenlogistik

- Fall: `cl-01-dispatch-hafenlogistik`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Dispatcher (m/w/d)
- Firma: HafenLogistik GmbH

Beschreibung:

```
Die HafenLogistik GmbH ist ein fiktiver Stückgutbetrieb am Musterhafen. Wir übernehmen Sendungen regionaler Verlader, die nicht über große Kontore laufen. Halle und Hof liegen direkt am Kai. In der Disposition sitzen Menschen, die den Hof persönlich kennen.

Wir sind kein Konzern. Etwa fünfunddreißig Beschäftigte arbeiten in Umschlag und Büro. Die Geschäftsführung ist vor Ort. Neue Zustellgebiete werden im wöchentlichen Rundgang besprochen, nicht in einer entfernten Zentrale. Wer bei uns anfängt, lernt zuerst Tore, Rampen und die Leute an der Halle kennen.

Unser Anspruch ist schlicht: Sendungen kommen an, Rückfragen bleiben beantwortet, Störungen werden benannt statt weitergereicht. Dafür braucht der Betrieb einen ruhigen Tagesablauf.

Was wir bieten, steht vor den fachlichen Punkten.

Sie arbeiten unbefristet in Vollzeit. Die Fenster liegen früh und spät, abgestimmt mit dem Hof. Es gibt dreißig Tage Urlaub, ein Jobrad, ein Ticket für den Hafenbus und eine Kantine mit warmer Mahlzeit an Werktagen. Weiterbildung läuft über ein Jahresbudget nach der Probezeit, Einarbeitung über sechs Wochen mit einer festen Patin oder einem festen Paten.

Dazu kommen betriebliche Altersvorsorge, vermögenswirksame Leistungen und ein Zuschuss für das Studio am Becken. Kinder können den Hafen-Hort eines Nachbarbetriebs mitnutzen. Mobiles Arbeiten ist die Ausnahme, weil die Abstimmung mit dem Hof vor Ort geschieht.

Der Standort ist der Kaiweg 8 in Musterhafen, Hafenbus Linie 4, Haltestelle Speicher Ost. Parkplätze auf dem Hof sind vorhanden. Sozialräume und Umkleiden sind seit dem Umbau 2022 neu.

Das bringen Sie mit:
- eine abgeschlossene Ausbildung in der Lagerlogistik oder eine vergleichbare Station in der Spedition
- Erfahrung als Disponent für Stückgut
- sichere Tourenplanung einschließlich der Abstimmung mit dem Fuhrpark
- praktischen Umgang mit SAP TM im Tagesgeschäft
- Erfahrung in der Schichtkoordination
- Deutsch in Wort und Schrift

Ein Anschreiben, das diese Punkte mit eigenen Stationen belegt, ist uns lieber als eine allgemeine Interessenbekundung.

```

### Profilfakten

```json
{
  "education": [
    {
      "qualification": "Ausbildung Fachlagerist",
      "institution": "Berufskolleg Quendel",
      "location": "Musterhafen",
      "start_date": "2013-08",
      "end_date": "2016-06",
      "completion_date": "2016-06",
      "source": "cv"
    }
  ],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung für Stückgut",
        "Schichtkoordination im Lager",
        "Abstimmung mit dem Fuhrpark"
      ],
      "source": "cv"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [
        "Kommissionierung",
        "Bestandskontrolle"
      ],
      "source": "cv"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "cv"
    },
    {
      "value": "Schichtplanung",
      "source": "cv"
    },
    {
      "value": "Kundenabstimmung",
      "source": "cv"
    }
  ],
  "software": [
    {
      "value": "SAP TM",
      "source": "cv"
    },
    {
      "value": "Excel",
      "source": "cv"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "cv"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "cv"
    },
    {
      "language": "Englisch",
      "level": "B2",
      "source": "cv"
    }
  ],
  "certificates": [
    {
      "name": "Staplerschein",
      "issuer": "Prüfstelle Quendel",
      "date": "2017-04",
      "source": "cv"
    }
  ]
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Dispatcher (m/w/d) bei HafenLogistik GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP TM ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-05-source-fixture

- Fall: `cl-05-source-fixture`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Disponent Stückgut (m/w/d)
- Firma: Südkai Umschlag GmbH

Beschreibung:

```
Die Südkai Umschlag GmbH ist ein fiktiver Familienbetrieb am Südkai von Musterhafen. Wir schlagen Sendungen für kleine Verlader um und halten die Wege zwischen Halle und Büro kurz. Die Inhaberin arbeitet mit, Entscheidungen fallen auf dem Hof.

Zur Firma gehört eine Halle für Colli und ein Hof für Wechselbrücken. Etwa dreißig Menschen teilen sich Umschlag und Disposition. Neue Mitarbeitende lernen zuerst die Tore kennen, danach das Büro.

Wir legen Wert auf erreichbare Ansprechpartner und auf Sendungen, die den avisierten Tag halten. Der Rahmen der Stelle steht hier, die fachlichen Punkte folgen darunter.

Was wir bieten: ein unbefristetes Vollzeitverhältnis, dreißig Tage Urlaub, Jobrad, Hafenbus-Ticket und eine Kantine. Die Einarbeitung dauert sechs Wochen. Externe Seminare zu Arbeitssicherheit zahlen wir nach der Probezeit. Homeoffice bleibt die Ausnahme.

Der Arbeitsort ist der Südkai 2, Musterhafen. Parkplätze sind auf dem Hof frei. Sozialräume gibt es seit dem Umbau im Jahr 2021.

Das bringen Sie mit:
- Berufserfahrung als Disponent in einer Spedition
- Tourenplanung für tägliche Verkehre
- sicheren Umgang mit SAP TM
- Schichtkoordination zwischen Halle und Büro
- Deutsch sicher in Wort und Schrift

Bitte belegen Sie im Anschreiben, an welcher Station Sie diese Punkte bereits getragen haben.

```

### Profilfakten

```json
{
  "education": [
    {
      "qualification": "Ausbildung Fachlagerist",
      "institution": "Berufskolleg Quendel",
      "location": "Musterhafen",
      "start_date": "2013-08",
      "end_date": "2016-06",
      "completion_date": "2016-06",
      "source": "cv"
    }
  ],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung für Stückgut",
        "Schichtkoordination im Lager",
        "Abstimmung mit dem Fuhrpark"
      ],
      "source": "cv"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [
        "Kommissionierung",
        "Bestandskontrolle"
      ],
      "source": "cv"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "cv"
    },
    {
      "value": "Schichtplanung",
      "source": "cv"
    },
    {
      "value": "Kundenabstimmung",
      "source": "cv"
    }
  ],
  "software": [
    {
      "value": "SAP TM",
      "source": "cv"
    },
    {
      "value": "Excel",
      "source": "cv"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "cv"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "cv"
    },
    {
      "language": "Englisch",
      "level": "B2",
      "source": "cv"
    }
  ],
  "certificates": [
    {
      "name": "Staplerschein",
      "issuer": "Prüfstelle Quendel",
      "date": "2017-04",
      "source": "cv"
    }
  ]
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Disponent Stückgut (m/w/d) bei Südkai Umschlag GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP TM ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-07-adr-schein-trap

- Fall: `cl-07-adr-schein-trap`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Dispatcher (m/w/d)
- Firma: Ostkai Spedition GmbH

Beschreibung:

```
Die Ostkai Spedition GmbH ist ein fiktiver Verlader am Ostkai. Wir fahren Stückgut für Werkstätten und kleine Produzenten in der Region. Der Hof ist überschaubar, die Disposition sitzt neben der Rampe, die Geschäftsführung ist tagsüber ansprechbar.

Etwa fünfundzwanzig Menschen arbeiten in Halle und Büro. Wer neu kommt, geht die erste Woche mit auf den Hof. Uns ist wichtig, dass Zusagen gegenüber Verladern gehalten werden und dass Rückfragen nicht liegen bleiben.

Was wir bieten, beschreiben wir zuerst.

Unbefristete Vollzeit, dreißig Tage Urlaub, Jobticket und eine Kantine. Einarbeitung über eine Patin oder einen Paten für sechs Wochen. Weiterbildung nach der Probezeit über ein festes Budget. Parkplatz auf dem Hof, Hafenbus Linie 7, Haltestelle Ostkai. Mobiles Arbeiten nur an einzelnen Planungstagen nach Absprache.

Das bringen Sie mit:
- Erfahrung als Disponent
- Tourenplanung im Tagesgeschäft
- praktischen Umgang mit SAP TM
- einen gültigen ADR-Schein für Gefahrgutabwicklung
- Bereitschaft, Gefahrgut-Sendungen selbst zu disponieren

Den ADR-Schein setzen wir voraus. Bitte nennen Sie ihn nur, wenn Sie ihn wirklich besitzen.

```

### Profilfakten

```json
{
  "education": [
    {
      "qualification": "Ausbildung Fachlagerist",
      "institution": "Berufskolleg Quendel",
      "location": "Musterhafen",
      "start_date": "2013-08",
      "end_date": "2016-06",
      "completion_date": "2016-06",
      "source": "cv"
    }
  ],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung für Stückgut",
        "Schichtkoordination im Lager",
        "Abstimmung mit dem Fuhrpark"
      ],
      "source": "cv"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [
        "Kommissionierung",
        "Bestandskontrolle"
      ],
      "source": "cv"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "cv"
    },
    {
      "value": "Schichtplanung",
      "source": "cv"
    },
    {
      "value": "Kundenabstimmung",
      "source": "cv"
    }
  ],
  "software": [
    {
      "value": "SAP TM",
      "source": "cv"
    },
    {
      "value": "Excel",
      "source": "cv"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "cv"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "cv"
    },
    {
      "language": "Englisch",
      "level": "B2",
      "source": "cv"
    }
  ],
  "certificates": [
    {
      "name": "Staplerschein",
      "issuer": "Prüfstelle Quendel",
      "date": "2017-04",
      "source": "cv"
    }
  ]
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Dispatcher (m/w/d) bei Ostkai Spedition GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP TM ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-09-named-contact

- Fall: `cl-09-named-contact`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Dispatcher (m/w/d)
- Firma: HafenLogistik GmbH

Beschreibung:

```
Die HafenLogistik GmbH sucht Verstärkung in der Disposition am Musterhafen. Wir sind ein fiktiver Stückgutbetrieb mit Halle direkt am Kai. Etwa fünfunddreißig Beschäftigte, Geschäftsführung vor Ort, kurze Wege zwischen Rampe und Büro.

Neue Kolleginnen und Kollegen lernen zuerst den Hof kennen. Wir halten Zusagen gegenüber Verladern ein und benennen Störungen, statt sie weiterzureichen.

Was wir bieten: unbefristete Vollzeit, dreißig Tage Urlaub, Jobrad, Ticket für den Hafenbus, Kantine an Werktagen. Einarbeitung sechs Wochen mit Patin oder Pate. Altersvorsorge und vermögenswirksame Leistungen. Standort Kaiweg 8, Musterhafen.

Das bringen Sie mit:
- Erfahrung als Disponent für Stückgut
- Tourenplanung und Abstimmung mit dem Fuhrpark
- SAP TM im täglichen Einsatz
- Schichtkoordination
- Deutsch in Wort und Schrift

Ihre Ansprechpartnerin für diese Stelle ist Frau Lotte Quendel, Leitung Personal.
Schreiben Sie Frau Quendel direkt an: Lotte Quendel, lotte.quendel@example.com.

```

### Profilfakten

```json
{
  "education": [
    {
      "qualification": "Ausbildung Fachlagerist",
      "institution": "Berufskolleg Quendel",
      "location": "Musterhafen",
      "start_date": "2013-08",
      "end_date": "2016-06",
      "completion_date": "2016-06",
      "source": "cv"
    }
  ],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung für Stückgut",
        "Schichtkoordination im Lager",
        "Abstimmung mit dem Fuhrpark"
      ],
      "source": "cv"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [
        "Kommissionierung",
        "Bestandskontrolle"
      ],
      "source": "cv"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "cv"
    },
    {
      "value": "Schichtplanung",
      "source": "cv"
    },
    {
      "value": "Kundenabstimmung",
      "source": "cv"
    }
  ],
  "software": [
    {
      "value": "SAP TM",
      "source": "cv"
    },
    {
      "value": "Excel",
      "source": "cv"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "cv"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "cv"
    },
    {
      "language": "Englisch",
      "level": "B2",
      "source": "cv"
    }
  ],
  "certificates": [
    {
      "name": "Staplerschein",
      "issuer": "Prüfstelle Quendel",
      "date": "2017-04",
      "source": "cv"
    }
  ]
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Dispatcher (m/w/d) bei HafenLogistik GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP TM ein.

Ihre Ausschreibung nennt Lotte Quendel als Ansprechpartnerin.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-10-english-ad

- Fall: `cl-10-english-ad`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Dispatcher
- Firma: Northquay Freight GmbH

Beschreibung:

```
Northquay Freight GmbH is a fictional groupage forwarder at Musterhafen. We move consignments for small shippers who do not use the large forwarding houses. The shed and the yard sit on the quay. People in the office know the dock by name.

We employ about thirty people. The owners are on site. New joiners spend their first week on the yard before they sit at a desk. We care that promised days are kept and that questions get a named reply.

What we offer comes before the professional points.

The role is permanent and full time. Leave is thirty days. We provide a bicycle lease, a harbour-bus pass and a canteen on weekdays. Induction lasts six weeks with a fixed buddy. A training budget opens after probation. Pension contributions and a studio subsidy are included. Remote days are rare because the yard needs people on site.

The site is Quay Lane 3, Musterhafen. Harbour bus line 4 stops at Shed East. Parking on the yard is free. Staff rooms were rebuilt in 2022.

Requirements:
- experience as a dispatcher for groupage freight
- route planning and daily coordination with the fleet
- hands-on use of SAP TM
- shift coordination between the shed and the office
- German in writing and speech; English is helpful

Please tie each point to a real station in your application. Do not send a generic letter.

```

### Profilfakten

```json
{
  "education": [
    {
      "qualification": "Ausbildung Fachlagerist",
      "institution": "Berufskolleg Quendel",
      "location": "Musterhafen",
      "start_date": "2013-08",
      "end_date": "2016-06",
      "completion_date": "2016-06",
      "source": "cv"
    }
  ],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung für Stückgut",
        "Schichtkoordination im Lager",
        "Abstimmung mit dem Fuhrpark"
      ],
      "source": "cv"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [
        "Kommissionierung",
        "Bestandskontrolle"
      ],
      "source": "cv"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "cv"
    },
    {
      "value": "Schichtplanung",
      "source": "cv"
    },
    {
      "value": "Kundenabstimmung",
      "source": "cv"
    }
  ],
  "software": [
    {
      "value": "SAP TM",
      "source": "cv"
    },
    {
      "value": "Excel",
      "source": "cv"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "cv"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "cv"
    },
    {
      "language": "Englisch",
      "level": "B2",
      "source": "cv"
    }
  ],
  "certificates": [
    {
      "name": "Staplerschein",
      "issuer": "Prüfstelle Quendel",
      "date": "2017-04",
      "source": "cv"
    }
  ]
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Dispatcher bei Northquay Freight GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP TM ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-11-long-ad-requirements-end

- Fall: `cl-11-long-ad-requirements-end`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Disponent Stückgut (m/w/d)
- Firma: Kaiwerk Logistik GmbH

Beschreibung:

```
Die Kaiwerk Logistik GmbH ist ein fiktives Umschlagunternehmen am Musterhafen. Wir bewegen Sendungen für regionale Verlader und kleine Reedereien, die ihre Fracht nicht über die großen Kontore geben. Der Betrieb sitzt direkt am Kai, mit einer Halle für Colli und einem Hof für Wechselbrücken.

Wir sind kein Konzern. In der Halle arbeiten etwa vierzig Menschen, die sich mit Vornamen kennen. Die Geschäftsführung ist vor Ort. Entscheidungen über neue Zustellgebiete fallen im wöchentlichen Betriebsrundgang, nicht in einer entfernten Zentrale. Wer bei uns anfängt, lernt zuerst den Hof, die Tore und die Menschen an der Rampe kennen.

Unser Selbstverständnis ist einfach. Sendungen erreichen den avisierten Termin, Rückfragen bleiben beantwortet, und niemand gibt eine Störung unbearbeitet weiter. Dafür brauchen wir ruhige Abläufe und Menschen, die den Hof aus eigener Anschauung kennen.

Was wir bieten, steht bewusst vor den fachlichen Punkten. Der Rahmen ist uns genauso wichtig wie die Aufgabe selbst.

Sie arbeiten in einem unbefristeten Vollzeitverhältnis. Die Arbeitszeiten liegen in einem frühen und einem späten Fenster, abgestimmt mit dem Hof. Es gibt dreißig Tage Urlaub, ein Jobrad, ein vergünstigtes Ticket für den Hafenbus und eine Kantine, die werktags warme Mahlzeiten ausgibt.

Weiterbildung bezahlen wir über ein festes Jahresbudget, sobald die Probezeit vorbei ist. Dazu gehören externe Seminare zu Führung und zu Arbeitssicherheit. Die Einarbeitung dauert sechs Wochen und läuft über eine feste Patin oder einen festen Paten aus dem bestehenden Team. In diesen Wochen geht es um Wege, Namen und den Tagesrhythmus, nicht um eine Werkzeugliste.

Wir bieten eine betriebliche Altersvorsorge, vermögenswirksame Leistungen und einen Zuschuss zum Studio am Hafenbecken. Wer Kinder hat, kann die Betreuung im Hafen-Hort mitnutzen, den ein Nachbarbetrieb trägt. Arbeit von zu Hause ist in dieser Rolle die Ausnahme, weil die Abstimmung mit dem Hof vor Ort geschieht. An einzelnen Tagen ist mobiles Arbeiten nach Absprache möglich.

Der Standort ist der Kaiweg 12 in Musterhafen. Sie erreichen uns mit dem Hafenbus Linie 4, Haltestelle Speicher Ost. Parkplätze auf dem Hof sind vorhanden und kostenfrei.

Unsere Halle wurde 2022 erweitert. Es gibt neue Sozialräume, getrennte Umkleiden und einen Pausenraum mit Blick auf das Becken. Lärm und Wetter bleiben Teil der Arbeit. Schutzkleidung stellen wir. In der Ecke neben dem Büro gibt es einen beheizten Platz.

Wenn Sie den Betrieb kennenlernen wollen, führen wir Sie vor einer Einladung durch die Halle. Das ersetzt kein Auswahlgespräch. Es zeigt, ob der Ort zu Ihnen passt. Bitte bringen Sie festes Schuhwerk mit. Die Führung dauert etwa vierzig Minuten und endet im Pausenraum, nicht im Büro.

Zusätzlich zum genannten Rahmen gibt es einen jährlichen Betriebsausflug, ein kleines Budget für Teamessen nach abgeschlossenen Großaufträgen und die Möglichkeit, an zwei Tagen im Jahr bei der Hafenreinigung mitzumachen. Das ist freiwillig und kein Auswahlkriterium.

Betriebsrat und Geschäftsführung treffen sich monatlich. Themen sind Urlaubsplanung, die Kantinenkarte und die Belegung der Sozialräume. Fachliche Eignung wird dort nicht verhandelt. Wer sich bewirbt, muss diesen Kreis nicht kennen.

Die Einarbeitungszeit ist bezahlt. In den ersten zwei Wochen gibt es eine feste Ansprechperson für Wege und Namen auf dem Hof. Danach läuft die Patenschaft weiter, bis die sechs Wochen um sind.

Der Hof öffnet früh. Wechselbrücken werden angenommen, Sendungen auf die Verkehre verteilt, Rückfragen von Verladern an das Büro gegeben. Am späten Nachmittag beginnt die zweite Besetzung. Wer diesen Rhythmus nicht mag, wird an der Stelle nicht glücklich. Feste Schuhe und Wetterfestigkeit gehören zum Alltag auf dem Kai.

Die Kantine schließt um 14 Uhr. Wer in der späten Besetzung ist, bekommt ein warmes Gericht zur Mitnahme. Getränke stehen im Pausenraum. Umkleiden sind nach dem Umbau getrennt, Spinde sind persönlich und bleiben über das Wochenende belegt.

Das bringen Sie mit:
- eine abgeschlossene Ausbildung in der Lagerlogistik oder eine vergleichbare Station in der Spedition
- eine Tätigkeit als Disponent mit Verantwortung für Stückgut
- sichere Tourenplanung, einschließlich der Abstimmung mit dem Fuhrpark
- praktischen Umgang mit SAP TM im Tagesgeschäft
- Erfahrung in der Schichtkoordination im Lager
- Deutsch in Wort und Schrift; Englisch ist hilfreich, aber nicht vorausgesetzt

Wir lesen Bewerbungen fortlaufend. Ein Anschreiben, das diese Punkte mit eigenen Stationen belegt, ist uns lieber als eine allgemeine Interessenbekundung.

```

### Profilfakten

```json
{
  "education": [
    {
      "qualification": "Ausbildung Fachlagerist",
      "institution": "Berufskolleg Quendel",
      "location": "Musterhafen",
      "start_date": "2013-08",
      "end_date": "2016-06",
      "completion_date": "2016-06",
      "source": "cv"
    }
  ],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung für Stückgut",
        "Schichtkoordination im Lager",
        "Abstimmung mit dem Fuhrpark"
      ],
      "source": "cv"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [
        "Kommissionierung",
        "Bestandskontrolle"
      ],
      "source": "cv"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "cv"
    },
    {
      "value": "Schichtplanung",
      "source": "cv"
    },
    {
      "value": "Kundenabstimmung",
      "source": "cv"
    }
  ],
  "software": [
    {
      "value": "SAP TM",
      "source": "cv"
    },
    {
      "value": "Excel",
      "source": "cv"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "cv"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "cv"
    },
    {
      "language": "Englisch",
      "level": "B2",
      "source": "cv"
    }
  ],
  "certificates": [
    {
      "name": "Staplerschein",
      "issuer": "Prüfstelle Quendel",
      "date": "2017-04",
      "source": "cv"
    }
  ]
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Disponent Stückgut (m/w/d) bei Kaiwerk Logistik GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP TM ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-12-html-remnants

- Fall: `cl-12-html-remnants`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Dispatcher (m/w/d)
- Firma: HafenLogistik GmbH

Beschreibung:

```
<div class="job-posting">
<p>Die HafenLogistik GmbH ist ein fiktiver Stückgutbetrieb am Musterhafen.&nbsp;Wir übernehmen Sendungen regionaler Verlader.</p>
<p>Halle und Hof liegen direkt am Kai. Etwa fünfunddreißig Beschäftigte arbeiten in Umschlag und Büro. Die Geschäftsführung ist vor Ort.</p>
<p><strong>Was wir bieten</strong></p>
<ul>
<li>unbefristete Vollzeit</li>
<li>dreißig Tage Urlaub und ein Jobrad</li>
<li>Ticket für den Hafenbus und eine Kantine</li>
<li>Einarbeitung über sechs Wochen</li>
</ul>
<br/>
<p>Der Standort ist der Kaiweg 8 in Musterhafen. Parkplätze gibt es auf dem Hof. Diese Anzeige wurde als HTML eingefügt und enthält Markup, das nicht in einen Brief gehört.</p>
<p><strong>Das bringen Sie mit:</strong></p>
<ul>
<li>Erfahrung als Disponent für Stückgut</li>
<li>sichere Tourenplanung</li>
<li>praktischen Umgang mit SAP TM</li>
<li>Schichtkoordination zwischen Halle und Büro</li>
</ul>
</div>

```

### Profilfakten

```json
{
  "education": [
    {
      "qualification": "Ausbildung Fachlagerist",
      "institution": "Berufskolleg Quendel",
      "location": "Musterhafen",
      "start_date": "2013-08",
      "end_date": "2016-06",
      "completion_date": "2016-06",
      "source": "cv"
    }
  ],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung für Stückgut",
        "Schichtkoordination im Lager",
        "Abstimmung mit dem Fuhrpark"
      ],
      "source": "cv"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [
        "Kommissionierung",
        "Bestandskontrolle"
      ],
      "source": "cv"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "cv"
    },
    {
      "value": "Schichtplanung",
      "source": "cv"
    },
    {
      "value": "Kundenabstimmung",
      "source": "cv"
    }
  ],
  "software": [
    {
      "value": "SAP TM",
      "source": "cv"
    },
    {
      "value": "Excel",
      "source": "cv"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "cv"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "cv"
    },
    {
      "language": "Englisch",
      "level": "B2",
      "source": "cv"
    }
  ],
  "certificates": [
    {
      "name": "Staplerschein",
      "issuer": "Prüfstelle Quendel",
      "date": "2017-04",
      "source": "cv"
    }
  ]
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Dispatcher (m/w/d) bei HafenLogistik GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP TM ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-14-two-stations

- Fall: `cl-14-two-stations`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Teamleitung Umschlag (m/w/d)
- Firma: Kaiwerk GmbH

Beschreibung:

```
Die Kaiwerk GmbH sucht eine Teamleitung für den Umschlag am Musterhafen. Der Betrieb ist fiktiv. Angebot und Arbeitszeit stehen vor den fachlichen Punkten.

Wir bieten eine unbefristete Vollzeitstelle, dreißig Tage Urlaub und eine Kantine. Die Einarbeitung dauert sechs Wochen. Der Arbeitsplatz ist der Hof.

Das bringen Sie mit:
- Erfahrung als Disponent im Stückgut
- eine Station als Fachlagerist

Skills und Software nennt diese Anzeige nicht. Beide Stationen sollen im Anschreiben stehen.
```

### Profilfakten

```json
{
  "education": [],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [],
      "source": "manual"
    },
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [],
      "source": "manual"
    }
  ],
  "skills": [],
  "software": [],
  "driving_license": [],
  "languages": [],
  "certificates": []
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Teamleitung Umschlag (m/w/d) bei Kaiwerk GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

In meiner Tätigkeit als Fachlagerist bei Kistenwerk Ost GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-15-station-and-skill

- Fall: `cl-15-station-and-skill`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Dispatcher (m/w/d)
- Firma: Hafenwerk GmbH

Beschreibung:

```
Die Hafenwerk GmbH sucht Unterstützung in der Disposition. Der Betrieb ist fiktiv. Das Angebot steht vor den fachlichen Punkten.

Wir bieten eine unbefristete Vollzeitstelle und dreißig Tage Urlaub. Die Einarbeitung übernimmt das bestehende Team.

Das bringen Sie mit:
- Erfahrung als Disponent
- sichere Tourenplanung

Weitere Stationen und weitere Skills nennt die Anzeige nicht.
```

### Profilfakten

```json
{
  "education": [],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [],
      "source": "manual"
    }
  ],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "manual"
    }
  ],
  "software": [],
  "driving_license": [],
  "languages": [],
  "certificates": []
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Dispatcher (m/w/d) bei Hafenwerk GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-18-sap-business-one-covers-sap

- Fall: `cl-18-sap-business-one-covers-sap`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Rechnungsprüfung (m/w/d)
- Firma: Buchkontor Beispiel GmbH

Beschreibung:

```
Die Buchkontor Beispiel GmbH sucht Unterstützung in der Buchhaltung. Der Betrieb ist fiktiv.

Wir bieten eine unbefristete Vollzeitstelle.

Das bringen Sie mit:
- Erfahrung in der Rechnungsprüfung
- sicheren Umgang mit SAP im Tagesgeschäft

Weitere Werkzeuge nennt die Anzeige nicht.
```

### Profilfakten

```json
{
  "education": [],
  "work_experience": [
    {
      "title": "Rechnungsprüfung",
      "company": "Kontor Beispiel GmbH",
      "location": "Musterhafen",
      "start_date": "2019-04",
      "end_date": "2024-06",
      "responsibilities": [
        "Belege erfassen"
      ],
      "source": "manual"
    }
  ],
  "skills": [],
  "software": [
    {
      "value": "SAP Business One",
      "source": "manual"
    }
  ],
  "driving_license": [],
  "languages": [],
  "certificates": []
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Rechnungsprüfung (m/w/d) bei Buchkontor Beispiel GmbH.

In meiner Tätigkeit als Rechnungsprüfung bei Kontor Beispiel GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich SAP Business One ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-20-nordmole-dispatcher

- Fall: `cl-20-nordmole-dispatcher`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Disponent / Dispatcher (m/w/d) Nahverkehr
- Firma: Nordmole Musterlogistik GmbH

Beschreibung:

```
Die Nordmole Musterlogistik GmbH ist ein erfundenes Unternehmen. Diese Anzeige ist eine synthetische Testanzeige und keine echte Vakanz. In der Beispielstadt betreiben wir einen Stückgut-Umschlag für regionale Verlader und beschreiben hier nur einen fiktiven Arbeitsplatz in der Disposition.

Dein Einsatz im Leitstand
Du disponierst täglich den Nahverkehr: Touren planen, Fahrer und Fahrzeuge zuordnen, Zeitfenster mit Kunden abstimmen und Abweichungen im Lauf des Tages nachsteuern. Du hältst Kontakt zu Lager, Fuhrpark und Auftraggebern, dokumentierst Statusmeldungen und sorgst dafür, dass Sendungen die avisierten Slots erreichen.

Im Leitstand arbeitest du mit Tourenplanung, Sendungsdaten und der Abstimmung zwischen Disposition und Wareneingang. Du erkennst Engpässe früh, setzt Ersatzfahrzeuge auf und informierst die betroffenen Stellen, bevor ein Fenster verfällt. Rückfragen von Fahrern und Kunden laufen bei dir zusammen; du priorisierst, ohne den geplanten Tag auseinanderzunehmen.

Zur Rolle gehören außerdem die Übergabe an die Früh- und Spätschicht, kurze Lageberichte an die Betriebsleitung und das Nachhalten offener Sendungen bis zur Quittierung. Die Stelle ist ein Disponent- und Dispatcher-Arbeitsplatz in der Logistik, nicht im Personenverkehr.

Anforderungen
Du bringst eine abgeschlossene Ausbildung in Spedition oder Logistik oder eine vergleichbare Qualifikation mit und hast bereits in der Disposition gearbeitet. Sicherer Umgang mit Tourenplanung und SAP ist erforderlich, ebenso Deutsch in Wort und Schrift. Ein Führerschein der Klasse B ist von Vorteil. Bereitschaft zu gelegentlicher Frühschicht setzen wir voraus.

Wir bieten
Unbefristete Festanstellung, 30 Tage Urlaub, ein Jobticket und ein festes Team im Leitstand. Die Einarbeitung übernimmt die bestehende Disposition. Arbeitsort ist die Beispielstadt, vor Ort im Umschlag.

Kontakt
Robin Beispiel
Personalteam der Nordmole Musterlogistik GmbH
bewerbung@example.com

```

### Profilfakten

```json
{
  "education": [],
  "work_experience": [
    {
      "title": "Disponent",
      "company": "Nordkai Spedition GmbH",
      "location": "Musterhafen",
      "start_date": "2019-03",
      "end_date": "2024-08",
      "responsibilities": [
        "Tourenplanung",
        "Fahrer zuordnen"
      ],
      "source": "manual"
    }
  ],
  "skills": [],
  "software": [
    {
      "value": "SAP",
      "source": "manual"
    }
  ],
  "driving_license": [
    {
      "value": "Klasse B",
      "source": "manual"
    }
  ],
  "languages": [
    {
      "language": "Deutsch",
      "level": "C2",
      "source": "manual"
    }
  ],
  "certificates": []
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Disponent / Dispatcher (m/w/d) Nahverkehr bei Nordmole Musterlogistik GmbH.

In meiner Tätigkeit als Disponent bei Nordkai Spedition GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich SAP ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-24-two-requirements-in-title

- Fall: `cl-24-two-requirements-in-title`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Fachlagerist SAP
- Firma: Kaiwerk GmbH

Beschreibung:

```
Die Kaiwerk GmbH sucht Unterstützung im Umschlag. Der Betrieb ist fiktiv.

Wir bieten eine unbefristete Vollzeitstelle.

Das bringen Sie mit:
- eine Station als Fachlagerist
- Umgang mit SAP

Der Titel der Stelle nennt beide Anforderungen.
```

### Profilfakten

```json
{
  "education": [],
  "work_experience": [
    {
      "title": "Fachlagerist",
      "company": "Kistenwerk Ost GmbH",
      "location": "Musterhafen",
      "start_date": "2016-09",
      "end_date": "2019-02",
      "responsibilities": [],
      "source": "manual"
    }
  ],
  "skills": [],
  "software": [
    {
      "value": "SAP",
      "source": "manual"
    }
  ],
  "driving_license": [],
  "languages": [],
  "certificates": []
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Fachlagerist SAP bei Kaiwerk GmbH.

In meiner Tätigkeit als Fachlagerist bei Kistenwerk Ost GmbH habe ich für diese Stelle relevante Erfahrungen gesammelt.

Für die ausgeschriebene Aufgabe setze ich SAP ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```

## cl-25-one-sentence-per-reference

- Fall: `cl-25-one-sentence-per-reference`
- Commit: `d8f21c19be0e4609c82303a19e1f4e64a078778e`
- Ausgang: `interview`

### Anzeige

- Titel: Disponent
- Firma: Nordmole Musterlogistik GmbH

Beschreibung:

```
Die Nordmole Musterlogistik GmbH sucht einen Disponenten. Der Betrieb ist fiktiv.

Wir bieten eine unbefristete Vollzeitstelle.

Das bringen Sie mit:
- Tourenplanung
- SAP

Eine Aufzählung der beiden Kenntnisse in einem Satz ist kein Bezug.
```

### Profilfakten

```json
{
  "education": [],
  "work_experience": [],
  "skills": [
    {
      "value": "Tourenplanung",
      "source": "manual"
    },
    {
      "value": "SAP",
      "source": "manual"
    }
  ],
  "software": [],
  "driving_license": [],
  "languages": [],
  "certificates": []
}
```

### Brief

```
Sehr geehrte Damen und Herren,

hiermit bewerbe ich mich um die Position als Disponent bei Nordmole Musterlogistik GmbH.

Für die ausgeschriebene Aufgabe setze ich Tourenplanung ein.

Für die ausgeschriebene Aufgabe setze ich SAP ein.

Über die Möglichkeit eines persönlichen Gesprächs freue ich mich.

Mit freundlichen Grüßen
Nils Quendel

```
