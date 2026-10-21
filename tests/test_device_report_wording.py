"""Device report wording (Designer + Personaler): exactly one model line names a
choice, it is the setup wizard's model under the wizard's own name, and neither
it nor the bundled-model line makes a quality, speed or "outdated" claim."""
import re

import pytest

from desktop.i18n import TRANSLATIONS
from desktop.widgets.model_fit import adapt_setup_recommendation
from guenther import device_check
from guenther import setup_models as setup

DISK_OK = 100_000_000_000
FIT_PREFIX = {'de': 'Passendes Modell für dieses Gerät: ', 'en': 'Model that fits this device: '}
BUNDLED_PREFIX = {'de': 'Mitgeliefertes Modell: ', 'en': 'Bundled model: '}
RECOMMEND_WORD = re.compile(r'empfehl|recommend', re.IGNORECASE)
# The fit line only says the model fits: no quality or speed claim.
FIT_BANNED = re.compile(r'\b(beste\w*|best|empfohlen\w*|qualität\w*|quality|schnell\w*|fast\w*|'
                        r'besser\w*|better)\b', re.IGNORECASE)
# The bundled line is neutral: nothing outdated, worse, limited or replaced.
BUNDLED_BANNED = re.compile(r'\b(alt\w*|veraltet\w*|nur|statt|ersetzt\w*|schlechter\w*|old\w*|'
                            r'outdated|only|instead|replaced|worse|legacy)\b', re.IGNORECASE)


def _report(total, avail, cores, disk, language):
    check = device_check.recommend(total_gib=total, available_gib=avail, physical_cores=cores,
                                   free_disk_gb=disk / 1_000_000_000)
    return check, check.message(language).splitlines()


def _wizard_name(total, avail, cores, disk):
    """The name the setup wizard shows for its recommendation (adapter = wizard view)."""
    recommendation = setup.recommend_setup_model(total_gib=total, available_gib=avail,
                                                 physical_cores=cores, free_disk_bytes=disk)
    if recommendation.model_id is None:
        return None
    return adapt_setup_recommendation(recommendation).model(recommendation.model_id).display_name


@pytest.mark.parametrize('language', ['de', 'en'])
@pytest.mark.parametrize('total,avail,cores,disk', [
    (7.7, 3.0, 2, DISK_OK),      # 8 GB laptop -> 4B
    (7.7, 6.5, 2, DISK_OK),
    (15.6, 12.0, 4, DISK_OK),
    (31.6, 28.0, 8, DISK_OK),
    (64.0, 40.0, 16, DISK_OK),
])
def test_report_has_exactly_one_model_line_matching_the_wizard(total, avail, cores, disk, language):
    check, lines = _report(total, avail, cores, disk, language)
    fit_lines = [line for line in lines if line.startswith(FIT_PREFIX[language])]
    assert len(fit_lines) == 1, lines
    name = _wizard_name(total, avail, cores, disk)
    assert name is not None
    assert fit_lines[0] == FIT_PREFIX[language] + name
    assert check.setup_model_name == name
    # The old two "Empfehlung ..." lines are gone; no other line recommends.
    assert not [line for line in lines if RECOMMEND_WORD.search(line)], lines
    bundled = [line for line in lines if line.startswith(BUNDLED_PREFIX[language])]
    assert bundled == [BUNDLED_PREFIX[language] + 'Qwen3.5-4B Q4_K_M']


@pytest.mark.parametrize('language', ['de', 'en'])
def test_8gb_laptop_report_names_the_wizard_4b(language):
    _, lines = _report(7.7, 3.0, 2, DISK_OK, language)
    assert FIT_PREFIX[language] + 'Qwen 4B · kompakt' in lines
    assert _wizard_name(7.7, 3.0, 2, DISK_OK) == 'Qwen 4B · kompakt'


@pytest.mark.parametrize('language', ['de', 'en'])
def test_no_model_line_when_the_wizard_has_no_model(language):
    assert _wizard_name(3.8, 2.5, 2, DISK_OK) is None
    _, lines = _report(3.8, 2.5, 2, DISK_OK, language)
    assert not [line for line in lines if line.startswith(FIT_PREFIX[language])]
    assert not [line for line in lines if RECOMMEND_WORD.search(line)], lines


@pytest.mark.parametrize('language', ['de', 'en'])
def test_model_lines_make_no_quality_or_outdated_claim(language):
    fit_template = TRANSLATIONS[language]['device_report.fitting_model']
    bundled_template = TRANSLATIONS[language]['device_report.bundled_model']
    assert fit_template == FIT_PREFIX[language] + '{name}'
    assert bundled_template == BUNDLED_PREFIX[language] + '{name}'
    assert not FIT_BANNED.search(fit_template)
    assert not BUNDLED_BANNED.search(bundled_template)
    for name in (entry['display_name'] for entry in setup.SETUP_MODEL_CATALOG.values()):
        assert not FIT_BANNED.search(fit_template.format(name=name)), name
    _, lines = _report(7.7, 3.0, 2, DISK_OK, language)
    fit_line = next(line for line in lines if line.startswith(FIT_PREFIX[language]))
    bundled_line = next(line for line in lines if line.startswith(BUNDLED_PREFIX[language]))
    assert not FIT_BANNED.search(fit_line)
    assert not BUNDLED_BANNED.search(bundled_line)
