import concurrent.futures
import pytest
from search.web_search_guard import WebSearchGuard, WebSearchPaused


def test_cache_survives_restart_and_does_not_store_query(tmp_path):
    path = tmp_path / 'guard.db'
    clock = [1000.0]
    guard = WebSearchGuard(path, clock=lambda: clock[0])
    calls = []
    def fetch():
        calls.append(True)
        return ['https://firma.example/karriere']
    assert guard.run('duckduckgo', 'Verkäufer Köln', fetch)
    assert WebSearchGuard(path, clock=lambda: clock[0]).run('duckduckgo', 'Verkäufer Köln', fetch)
    assert len(calls) == 1
    assert 'Verkäufer'.encode() not in path.read_bytes()
    clock[0] += 86401
    assert guard.run('duckduckgo', 'Verkäufer Köln', fetch)
    assert len(calls) == 2


def test_captcha_stops_provider_across_queries_and_restart(tmp_path):
    path = tmp_path / 'guard.db'
    calls = []
    def blocked():
        calls.append(True)
        raise RuntimeError('web_search_captcha')
    guard = WebSearchGuard(path, clock=lambda: 1000)
    with pytest.raises(WebSearchPaused, match='provider_blocked'):
        guard.run('duckduckgo', 'first', blocked)
    guard = WebSearchGuard(path, clock=lambda: 2000)
    with pytest.raises(WebSearchPaused, match='provider_paused'):
        guard.run('duckduckgo', 'another', blocked)
    assert len(calls) == 1
    # Separate provider retains its own budget.
    assert guard.run('brave', 'another', lambda: ['https://firma.example/job'])


def test_cached_jobs_remain_available_during_provider_pause(tmp_path):
    guard = WebSearchGuard(tmp_path / 'guard.db', clock=lambda: 1000)
    assert guard.run('brave', 'seller', lambda: ['https://firma.example/job'])
    with pytest.raises(WebSearchPaused):
        guard.run('brave', 'different', lambda: [])
    assert guard.run('brave', 'seller', lambda: pytest.fail('should not fetch'))


def test_concurrent_searches_only_reserve_one_request(tmp_path):
    path = tmp_path / 'guard.db'
    guard = WebSearchGuard(path, clock=lambda: 1000)
    calls = []
    def run(index):
        try:
            return guard.run('brave', str(index), lambda: calls.append(index) or [])
        except WebSearchPaused:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run, range(8)))
    assert len(calls) == 1


def test_hourly_limit_and_recovery(tmp_path):
    clock = [1000.0]
    guard = WebSearchGuard(tmp_path / 'guard.db', clock=lambda: clock[0])
    for i in range(6):
        guard.run('brave', str(i), lambda: [])
        clock[0] += 31
    with pytest.raises(WebSearchPaused):
        guard.run('brave', 'seventh', lambda: pytest.fail('must not request'))
    clock[0] += 3601
    assert guard.run('brave', 'seventh', lambda: ['https://firma.example/job'])


@pytest.mark.parametrize('status', [403, 429])
def test_http_block_stops_provider(tmp_path, status):
    import httpx
    guard = WebSearchGuard(tmp_path / 'guard.db', clock=lambda: 1000)
    def fetch():
        response = httpx.Response(status, request=httpx.Request('GET', 'https://example.org'))
        response.raise_for_status()
    with pytest.raises(WebSearchPaused, match='provider_blocked'):
        guard.run('brave', 'query', fetch)


def test_partial_jobs_are_preserved_when_provider_is_blocked(tmp_path):
    from search.base import PartialResultsError
    guard = WebSearchGuard(tmp_path / 'guard.db', clock=lambda: 1000)
    jobs = [object()]
    def fetch():
        raise PartialResultsError(jobs, 'HTTP 429')
    with pytest.raises(PartialResultsError) as error:
        guard.run('source:indeed', 'query', fetch)
    assert error.value.jobs == jobs
    with pytest.raises(WebSearchPaused):
        guard.run('source:indeed', 'different', lambda: [])


def test_portal_batch_is_cached_and_detached_from_matching_mutations(tmp_path, monkeypatch):
    from core.models import Job
    from search.base import JobSource, SearchQuery
    monkeypatch.setenv('KARRIEREKRAKE_DATA_DIR', str(tmp_path))
    class Portal(JobSource):
        source_id = 'indeed'
        calls = 0
        def search(self, queries):
            self.calls += 1
            return [Job(id='1', source='indeed', title='Verkäufer', url='https://firma.example/job')]
    source = Portal()
    queries = [SearchQuery('Verkäufer', 'Köln')]
    jobs, error, _ = source.safe_search(queries)
    assert error is None and len(jobs) == 1
    jobs[0].title = 'changed by caller'
    jobs, error, _ = source.safe_search(queries)
    assert error is None and jobs[0].title == 'Verkäufer' and source.calls == 1


def test_portal_stops_after_first_block(monkeypatch):
    import httpx
    from search.stepstone import StepstoneSource
    from search.base import SearchQuery
    source = StepstoneSource()
    calls = []
    def fetch(query):
        calls.append(query)
        response = httpx.Response(429, request=httpx.Request('GET', 'https://example.org'))
        response.raise_for_status()
    monkeypatch.setattr(source, '_search_one', fetch)
    with pytest.raises(RuntimeError):
        source.search([SearchQuery('seller'), SearchQuery('admin')])
    assert len(calls) == 1
