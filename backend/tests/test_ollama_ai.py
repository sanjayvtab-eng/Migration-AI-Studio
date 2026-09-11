from types import SimpleNamespace

from app.services import ai_remediation


class FakeResponse:
    def __init__(self, payload, status_code=200, text=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else str(payload)

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.is_success:
            import httpx
            request = httpx.Request('GET', 'http://127.0.0.1:11434/test')
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError('error', request=request, response=response)


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, headers=None):
        if url.endswith('/api/version'):
            return FakeResponse({'version': '0.test'})
        if url.endswith('/api/tags'):
            return FakeResponse({'models': [{'name': 'qwen2.5-coder:3b'}, {'name': 'qwen2.5-coder:1.5b'}]})
        raise AssertionError(url)

    def post(self, url, headers=None, json=None):
        assert url == 'http://127.0.0.1:11434/api/chat'
        assert json['model'] == 'qwen2.5-coder:3b'
        assert json['stream'] is False
        assert json['format'] == 'json'
        assert json['options']['temperature'] == 0
        return FakeResponse({'message': {'content': '{"conversion_strategy":"TEST","generated_candidate":"SELECT 1","confidence":0.8,"assumptions":[],"risks":[],"validation_plan":[]}'}})


def cfg(**overrides):
    values = dict(
        llm_enabled=True,
        llm_provider='OLLAMA',
        llm_base_url=None,
        llm_api_key=None,
        llm_model='qwen2.5-coder:3b',
        llm_timeout_seconds=30,
        llm_max_attempts=3,
        llm_num_ctx=8192,
        llm_num_predict=2048,
        llm_max_prompt_chars=160000,
        ollama_keep_alive='5m',
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_ollama_status_uses_local_default_without_api_key(monkeypatch):
    monkeypatch.setattr(ai_remediation, 'get_settings', lambda: cfg())
    status = ai_remediation.provider_status()
    assert status['provider'] == 'OLLAMA'
    assert status['base_url'] == 'http://127.0.0.1:11434'
    assert status['configured'] is True
    assert status['api_key_required'] is False
    assert status['candidate_auto_deployment'] is False


def test_ollama_connection_detects_selected_model(monkeypatch):
    monkeypatch.setattr(ai_remediation, 'get_settings', lambda: cfg())
    monkeypatch.setattr(ai_remediation.httpx, 'Client', FakeClient)
    result = ai_remediation.test_provider_connection()
    assert result['reachable'] is True
    assert result['model_available'] is True
    assert result['version'] == '0.test'
    assert 'qwen2.5-coder:3b' in result['models']
    assert result['ready'] is True


def test_ollama_llm_call_is_json_local_and_zero_temperature(monkeypatch):
    monkeypatch.setattr(ai_remediation, 'get_settings', lambda: cfg())
    monkeypatch.setattr(ai_remediation.httpx, 'Client', FakeClient)
    payload, provider, model = ai_remediation._call_llm('safe prompt')
    assert provider == 'OLLAMA'
    assert model == 'qwen2.5-coder:3b'
    assert payload['conversion_strategy'] == 'TEST'


def test_prompt_limit_fails_safely_before_provider_call(monkeypatch):
    monkeypatch.setattr(ai_remediation, 'get_settings', lambda: cfg(llm_max_prompt_chars=10))
    try:
        ai_remediation._call_llm('this prompt is too long')
        assert False, 'expected RuntimeError'
    except RuntimeError as exc:
        assert 'exceeding governed limit' in str(exc)


def test_transient_provider_503_is_retried_and_then_succeeds(monkeypatch):
    calls = {'count': 0}

    class TransientClient(FakeClient):
        def post(self, url, headers=None, json=None):
            calls['count'] += 1
            if calls['count'] < 3:
                import httpx
                request = httpx.Request('POST', url)
                return httpx.Response(503, request=request, json={
                    'error': {'code': 503, 'status': 'UNAVAILABLE'}
                })
            return super().post(url, headers=headers, json=json)

    delays = []
    monkeypatch.setattr(ai_remediation, 'get_settings', lambda: cfg())
    monkeypatch.setattr(ai_remediation.httpx, 'Client', TransientClient)
    monkeypatch.setattr(ai_remediation.time, 'sleep', delays.append)

    payload, provider, _ = ai_remediation._call_llm('safe prompt')
    assert provider == 'OLLAMA'
    assert payload['conversion_strategy'] == 'TEST'
    assert calls['count'] == 3
    assert delays == [1.0, 2.0]


def test_exhausted_provider_503_returns_clear_retry_message(monkeypatch):
    class UnavailableClient(FakeClient):
        def post(self, url, headers=None, json=None):
            import httpx
            request = httpx.Request('POST', url)
            return httpx.Response(503, request=request, json={
                'error': {'code': 503, 'message': 'temporary high demand', 'status': 'UNAVAILABLE'}
            })

    monkeypatch.setattr(ai_remediation, 'get_settings', lambda: cfg())
    monkeypatch.setattr(ai_remediation.httpx, 'Client', UnavailableClient)
    monkeypatch.setattr(ai_remediation.time, 'sleep', lambda _: None)

    try:
        ai_remediation._call_llm('safe prompt')
        assert False, 'expected RuntimeError'
    except RuntimeError as exc:
        message = str(exc)
        assert 'temporarily unavailable after 3 attempts' in message
        assert 'No remediation candidate was accepted' in message


def test_quota_429_starts_cooldown_without_duplicate_provider_calls(monkeypatch):
    calls = {'count': 0}

    class QuotaClient(FakeClient):
        def post(self, url, headers=None, json=None):
            calls['count'] += 1
            import httpx
            request = httpx.Request('POST', url)
            return httpx.Response(429, request=request, json={
                'error': {
                    'code': 429,
                    'status': 'RESOURCE_EXHAUSTED',
                    'details': [{
                        '@type': 'type.googleapis.com/google.rpc.RetryInfo',
                        'retryDelay': '51s',
                    }],
                }
            })

    ai_remediation._PROVIDER_COOLDOWNS.clear()
    monkeypatch.setattr(ai_remediation, 'get_settings', lambda: cfg(
        llm_provider='GEMINI', llm_api_key='not-a-real-key', llm_model='gemini-2.5-flash'
    ))
    monkeypatch.setattr(ai_remediation.httpx, 'Client', QuotaClient)

    for expected in ('Retry after approximately 51s', 'No provider request was sent'):
        try:
            ai_remediation._call_llm('safe prompt')
            assert False, 'expected RuntimeError'
        except RuntimeError as exc:
            assert expected in str(exc)
    assert calls['count'] == 1
    ai_remediation._PROVIDER_COOLDOWNS.clear()


def test_ai_provider_endpoints_are_authenticated_and_return_governed_shape(client, auth_headers, monkeypatch):
    from app.api import routes
    fake = {
        'enabled': True, 'configured': True, 'ready': True, 'provider': 'OLLAMA',
        'base_url': 'http://127.0.0.1:11434', 'model': 'qwen2.5-coder:3b',
        'deterministic_first': True, 'api_key_required': False, 'api_key_configured': False,
        'max_attempts': 3, 'num_ctx': 8192, 'num_predict': 4096, 'max_prompt_chars': 160000,
        'candidate_auto_approval': False, 'candidate_auto_deployment': False,
        'production_mutation_allowed': False, 'reachable': True, 'model_available': True,
        'models': ['qwen2.5-coder:3b'], 'version': '0.test', 'latency_ms': 1.0, 'error': None,
    }
    monkeypatch.setattr(routes, 'test_provider_connection', lambda: dict(fake))
    monkeypatch.setattr(routes, 'list_provider_models', lambda: {
        'provider': 'OLLAMA', 'base_url': 'http://127.0.0.1:11434', 'reachable': True,
        'selected_model': 'qwen2.5-coder:3b', 'model_available': True,
        'models': ['qwen2.5-coder:3b'], 'error': None,
    })
    r = client.post('/api/ai/provider-test', headers=auth_headers)
    assert r.status_code == 200
    assert r.json()['provider'] == 'OLLAMA'
    assert r.json()['candidate_auto_deployment'] is False
    m = client.get('/api/ai/models', headers=auth_headers)
    assert m.status_code == 200
    assert m.json()['model_available'] is True
