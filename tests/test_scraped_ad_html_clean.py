"""Synthetic HTML regressions for the scraped-ad text cleaner.

SYNTHETIC corpus. The snippets imitate StepStone, Indeed, and LinkedIn
markup (nested lists, br, entities, scripts, cookie banners, apply buttons,
share widgets, similar-job blocks, tracking pixels, emoji bullets). Companies
are fictional. Nothing here was fetched from the network.

The cleaner on current main is ``search.jsonld.job_from_job_posting``:
``BeautifulSoup(description, "lxml").get_text("\\n", strip=True)``.
``search/jsonld.py`` is in the diff of open PR #67 (cleaning moves to
``search/job_schema.py`` ``strip_markup``), so this file does not patch it.
Cases the cleaner already fails are strict xfails with that note.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.job_sections import split_job_sections
from search.jsonld import job_from_job_posting

# search/jsonld.py is changed by open PR #67. Do not patch it here.
_XFAIL_CHROME = (
    "Existing scraped-ad cleaner is BeautifulSoup.get_text in "
    "search.jsonld.job_from_job_posting. Visible chrome stays in the text: "
    "cookie banners, Jetzt bewerben / Apply now, share widgets, and "
    "Ähnliche Jobs blocks. search/jsonld.py is modified by open PR #67 "
    "(cleaning moves to search.job_schema.strip_markup), so this PR does not "
    "patch it. Planned integration: drop that chrome inside strip_markup / "
    "job_from_job_posting after #67 lands."
)


@dataclass(frozen=True)
class HtmlCase:
    case_id: str
    portal: str
    html: str
    exact_lines: tuple[str, ...] = ()
    must_contain: tuple[str, ...] = ()
    must_absent: tuple[str, ...] = ()
    forbid_nbsp: bool = False


def _cleaned(html: str) -> str:
    job = job_from_job_posting(
        {
            "title": "Datenpfleger fuer fiktive Bojen",
            "url": "https://jobs.example.test/synthetic/1",
            "hiringOrganization": {"name": "Nordlicht Beispiel GmbH"},
            "description": html,
        },
        source="stepstone",
    )
    assert job is not None
    return job.description


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _assert_case(case: HtmlCase) -> None:
    text = _cleaned(case.html)
    assert "<" not in text and ">" not in text
    assert "&nbsp;" not in text
    assert "&amp;" not in text
    assert "&quot;" not in text
    for line in case.exact_lines:
        assert line in _lines(text), text
    for snippet in case.must_contain:
        assert snippet in text, text
    for snippet in case.must_absent:
        assert snippet not in text, text
    if case.forbid_nbsp:
        assert "\u00a0" not in text
        assert "Kenntnisse in Python" in text


# Each snippet is handwritten and marked synthetic. Fictional employers only.
SYNTHETIC_CORPUS: tuple[HtmlCase, ...] = (
    HtmlCase(
        case_id="stepstone_nested_lists_and_br",
        portal="stepstone",
        html="""
        <!-- SYNTHETIC StepStone-like fragment. Fictional Nordlicht Beispiel GmbH. -->
        <article class="job-ad">
          <h2>Ihre Aufgaben</h2>
          <ul>
            <li>Analysieren<br>und dokumentieren</li>
            <li>Mit dem Team abstimmen
              <ul><li>Daily vorbereiten</li></ul>
            </li>
          </ul>
        </article>
        """,
        exact_lines=(
            "Ihre Aufgaben",
            "Analysieren",
            "und dokumentieren",
            "Mit dem Team abstimmen",
            "Daily vorbereiten",
        ),
        must_absent=("<li>", "<br", "SYNTHETIC"),
    ),
    HtmlCase(
        case_id="indeed_entities_amp_quot",
        portal="indeed",
        html="""
        <!-- SYNTHETIC Indeed-like fragment. Fictional Harbor Labs Example. -->
        <div id="jobDescriptionText">
          <p>Kenntnisse in Python &amp; SQL &quot;gut&quot; &#8211; Erfahrung</p>
          <ul><li>Eins</li><li>Zwei</li></ul>
        </div>
        """,
        exact_lines=("Eins", "Zwei"),
        must_contain=('Python & SQL "gut"', "Erfahrung"),
        must_absent=("jobDescriptionText",),
    ),
    HtmlCase(
        case_id="linkedin_scripts_styles_pixels",
        portal="linkedin",
        html="""
        <!-- SYNTHETIC LinkedIn-like fragment. Fictional Fjord Beispiel AG. -->
        <style>.synth-banner{display:none;color:red}</style>
        <script type="text/javascript">var SYNTH_TRACK="pixel-id-999";</script>
        <script type="application/ld+json">{"secret":"SHOULD_NOT_LEAK"}</script>
        <noscript>Enable JavaScript SYNTH_NOSCRIPT_VISIBLE</noscript>
        <img src="https://track.example/pixel.gif" width="1" height="1" alt="">
        <img src="https://track.example/beacon.gif" alt="tracking pixel">
        <p>Sichtbarer Text der Fjord Beispiel AG</p>
        """,
        must_contain=("Sichtbarer Text der Fjord Beispiel AG",),
        must_absent=(
            "SYNTH_TRACK",
            "pixel-id-999",
            "SHOULD_NOT_LEAK",
            "display:none",
            "track.example",
            "tracking pixel",
            "<script",
            "<style",
        ),
    ),
    HtmlCase(
        case_id="emoji_bullets_stay_on_lines",
        portal="stepstone",
        html="""
        <!-- SYNTHETIC. Fictional Nordlicht Beispiel GmbH. -->
        <h2>Qualifications</h2>
        <ul>
          <li>✅ Studium der Informatik</li>
          <li>🔹 Berufserfahrung</li>
        </ul>
        """,
        exact_lines=(
            "Qualifications",
            "✅ Studium der Informatik",
            "🔹 Berufserfahrung",
        ),
    ),
    HtmlCase(
        case_id="ordered_and_unordered_lists",
        portal="indeed",
        html="""
        <!-- SYNTHETIC Indeed-like lists. Fictional Harbor Labs Example. -->
        <ul><li>Listenpunkt A</li><li>Listenpunkt B</li></ul>
        <ol><li>Listenpunkt C</li></ol>
        """,
        exact_lines=("Listenpunkt A", "Listenpunkt B", "Listenpunkt C"),
    ),
)


# Further synthetic fixtures used by the xfail and section-split tests.
# Same cleaner path as SYNTHETIC_CORPUS. Fictional employers only.
EXTRA_REGRESSION_CASES: tuple[HtmlCase, ...] = (
    HtmlCase(
        case_id="nbsp",
        portal="indeed",
        html="""
        <!-- SYNTHETIC Indeed-like entities. Fictional Harbor Labs Example. -->
        <p>Kenntnisse&nbsp;in&nbsp;Python &amp; SQL</p>
        """,
        forbid_nbsp=True,
        must_contain=("Python & SQL",),
    ),
    HtmlCase(
        case_id="stepstone_cookie",
        portal="stepstone",
        html="""
        <!-- SYNTHETIC StepStone-like cookie bar. Fictional Nordlicht Beispiel GmbH. -->
        <div id="onetrust-consent-sdk" class="cookie-banner">
          Diese Website verwendet Cookies. Alle akzeptieren
        </div>
        <noscript>Cookie-Hinweis SYNTH_COOKIE_NOSCRIPT</noscript>
        <article>
          <h2>Ihr Profil</h2>
          <ul>
            <li>Abgeschlossenes Studium</li>
            <li>Python</li>
          </ul>
        </article>
        """,
        exact_lines=("Abgeschlossenes Studium", "Python"),
        must_absent=(
            "Diese Website verwendet Cookies",
            "Alle akzeptieren",
            "SYNTH_COOKIE_NOSCRIPT",
            "onetrust",
        ),
    ),
    HtmlCase(
        case_id="indeed_apply",
        portal="indeed",
        html="""
        <!-- SYNTHETIC Indeed-like apply bar. Fictional Harbor Labs Example. -->
        <div class="jobsearch-ApplyButton">
          <button type="button">Jetzt bewerben</button>
          <a href="https://jobs.example.test/apply">Apply now</a>
        </div>
        <div id="jobDescriptionText">
          <p>Responsibilities</p>
          <ul>
            <li>Design APIs</li>
            <li>Review pull requests</li>
          </ul>
        </div>
        """,
        exact_lines=("Design APIs", "Review pull requests"),
        must_absent=("Jetzt bewerben", "Apply now", "jobsearch-ApplyButton"),
    ),
    HtmlCase(
        case_id="linkedin_share",
        portal="linkedin",
        html="""
        <!-- SYNTHETIC LinkedIn-like share widget. Fictional Fjord Beispiel AG. -->
        <div class="share-widget">
          <span>Share this job</span>
          <button>Teilen</button>
          <a>Auf Xing teilen</a>
        </div>
        <p>Anforderung im Text: Studium der Informatik</p>
        """,
        must_contain=("Studium der Informatik",),
        must_absent=("Share this job", "Auf Xing teilen", "share-widget"),
    ),
    HtmlCase(
        case_id="stepstone_similar",
        portal="stepstone",
        html="""
        <!-- SYNTHETIC StepStone-like similar-jobs rail. Fictional companies. -->
        <section>
          <h2>Anforderungen</h2>
          <ul><li>DATEV-Kenntnisse</li></ul>
        </section>
        <aside class="similar-jobs">
          <h2>Ähnliche Jobs</h2>
          <ul><li>Controller bei Fremde Beispiel KG</li></ul>
        </aside>
        """,
        exact_lines=("DATEV-Kenntnisse",),
        must_absent=("Ähnliche Jobs", "Fremde Beispiel KG", "similar-jobs"),
    ),
    HtmlCase(
        case_id="cookie_keeps_requirements",
        portal="stepstone",
        html="""
        <!-- SYNTHETIC. Fictional Nordlicht Beispiel GmbH. -->
        <div class="cookie-banner">Diese Website verwendet Cookies</div>
        <h2>Ihr Profil</h2>
        <ul>
          <li>Abgeschlossenes Studium</li>
          <li>Python und SQL</li>
        </ul>
        """,
    ),
    HtmlCase(
        case_id="stepstone_full_ad",
        portal="stepstone",
        html="""
        <!-- SYNTHETIC StepStone-like ad. Fictional Nordlicht Beispiel GmbH. -->
        <p>Die Nordlicht Beispiel GmbH baut fiktive Bojen.</p>
        <h2>Ihre Aufgaben</h2>
        <ul>
          <li>Bojen prüfen</li>
          <li>Berichte schreiben</li>
        </ul>
        <h2>Ihr Profil</h2>
        <ul>
          <li>Abgeschlossenes Studium</li>
          <li>Python und SQL</li>
        </ul>
        <h2>Wir bieten</h2>
        <ul><li>30 Tage Urlaub</li></ul>
        <h2>Ansprechpartner</h2>
        <p>Ada Beispiel</p>
        """,
    ),
    HtmlCase(
        case_id="qualifications_br_nested",
        portal="indeed",
        html="""
        <!-- SYNTHETIC. Fictional Harbor Labs Example. -->
        <h2>Qualifications</h2>
        <ul>
          <li>Analysieren<br>und dokumentieren</li>
          <li>Degree
            <ul><li>Computer science</li></ul>
          </li>
          <li>Python</li>
        </ul>
        """,
    ),
)

REGRESSION_CASES: tuple[HtmlCase, ...] = SYNTHETIC_CORPUS + EXTRA_REGRESSION_CASES
_CASES_BY_ID = {case.case_id: case for case in REGRESSION_CASES}

PASSING = [case for case in SYNTHETIC_CORPUS]


def regression_case(case_id: str) -> HtmlCase:
    return _CASES_BY_ID[case_id]


@pytest.mark.parametrize("case", PASSING, ids=lambda case: case.case_id)
def test_synthetic_html_cleaner_keeps_lines_and_drops_tags(case: HtmlCase):
    _assert_case(case)


def test_nbsp_is_a_normal_space():
    """&nbsp; between words should not survive as U+00A0."""
    _assert_case(regression_case("nbsp"))


@pytest.mark.xfail(reason=_XFAIL_CHROME, strict=True)
def test_cookie_banner_is_removed():
    _assert_case(regression_case("stepstone_cookie"))


@pytest.mark.xfail(reason=_XFAIL_CHROME, strict=True)
def test_apply_buttons_are_removed():
    _assert_case(regression_case("indeed_apply"))


@pytest.mark.xfail(reason=_XFAIL_CHROME, strict=True)
def test_share_widget_is_removed():
    _assert_case(regression_case("linkedin_share"))


@pytest.mark.xfail(reason=_XFAIL_CHROME, strict=True)
def test_similar_jobs_block_is_removed():
    _assert_case(regression_case("stepstone_similar"))


def test_cookie_banner_does_not_destroy_requirement_lines():
    """List structure still reaches the section splitter even while chrome remains."""
    text = _cleaned(regression_case("cookie_keeps_requirements").html)
    assert "Abgeschlossenes Studium" in _lines(text)
    assert "Python und SQL" in _lines(text)
    sections = split_job_sections(text)
    assert sections.requirements == ["Abgeschlossenes Studium", "Python und SQL"]


def test_cleaned_stepstone_like_ad_splits_into_sections():
    text = _cleaned(regression_case("stepstone_full_ad").html)
    assert "<" not in text
    sections = split_job_sections(text)
    assert "Nordlicht Beispiel" in sections.company_intro
    assert "Bojen prüfen" in sections.tasks
    assert "Berichte schreiben" in sections.tasks
    assert sections.requirements == ["Abgeschlossenes Studium", "Python und SQL"]
    assert "30 Tage Urlaub" in sections.benefits
    assert "Ada Beispiel" in sections.contact


def test_br_and_nested_list_become_requirement_items():
    text = _cleaned(regression_case("qualifications_br_nested").html)
    sections = split_job_sections(text)
    assert "Analysieren und dokumentieren" in sections.requirements
    assert "Degree" in sections.requirements
    assert "Computer science" in sections.requirements
    assert "Python" in sections.requirements
