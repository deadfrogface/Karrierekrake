# Offline-Suchfixtures (synthetisch)

Diese Dateien sind **synthetische** Antworten im Format, das der gepinnte
`python-jobspy==1.3.0`-Parser erwartet (Indeed GraphQL `apis.indeed.com/graphql`,
LinkedIn Guest-HTML `jobs-guest/jobs/api/seeMoreJobPostings/search`).

- Kein Mitschnitt einer echten Anbieterantwort, keine echte Suche, keine realen
  Firmen, Personen oder Stellen.
- Struktur aus dem JobSpy-1.3.0-Quellcode (`jobspy/indeed/__init__.py`,
  `jobspy/linkedin/__init__.py`) abgeleitet, nicht aus Live-Traffic.
- Verwendet von `tests/test_search_offline_fixture_pipeline.py` bei blockiertem
  Netzwerk (Socket/DNS/libcurl).
