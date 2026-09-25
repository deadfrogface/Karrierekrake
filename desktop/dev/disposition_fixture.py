# Synthetic test ad — fictional company, not a real vacancy.
# source must stay "fixture" (never "demo"). The URL is on an example domain.
# Do not treat this row as a live job and do not submit an application from it.

"""Synthetic Disponent/Dispatcher vacancy for manual cover-letter checks.

Not loaded at startup and not inserted by "Jobs suchen". Use
``scripts/insert_disposition_fixture.py``.
"""

from __future__ import annotations

from core.models import Job, JobStatus

FIXTURE_JOB_ID = "fixture-nordmole-disponent"
FIXTURE_SOURCE = "fixture"
FIXTURE_URL = "https://jobs.example/fixture/nordmole-disponent"
FIXTURE_COMPANY = "Nordmole Musterlogistik GmbH"
FIXTURE_TITLE = "Disponent / Dispatcher (m/w/d) Nahverkehr"

# Requirements sit in the lower half, as on typical German job ads.
FIXTURE_DESCRIPTION = """\
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
"""


def build_fixture_job() -> Job:
    """Return the synthetic row. Calling this does not touch a database."""
    return Job(
        id=FIXTURE_JOB_ID,
        source=FIXTURE_SOURCE,
        source_job_id=FIXTURE_JOB_ID,
        title=FIXTURE_TITLE,
        company=FIXTURE_COMPANY,
        description=FIXTURE_DESCRIPTION,
        city="Beispielstadt",
        url=FIXTURE_URL,
        application_url=FIXTURE_URL,
        status=JobStatus.NEW.value,
        remote_type="onsite",
        employment_type="Vollzeit",
        match_score=80,
    )
