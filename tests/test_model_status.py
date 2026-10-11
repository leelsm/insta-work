import pytest
from test_studio import client
from studio.model_status import record_check


def row(client, provider='openai'):
    return next(r for r in client.get('/api/settings').json()['model_status'] if r['provider']==provider)


def test_metadata_view_never_reads_credentials_or_calls_network(client,monkeypatch):
    monkeypatch.setattr(client.app.state.vault,'get',lambda *args:pytest.fail('credential read'))
    monkeypatch.setattr('studio.llm.httpx.Client',lambda **kw:pytest.fail('network attempted'))
    r=client.get('/api/settings');assert r.status_code==200
    rows=r.json()['model_status']
    assert len(rows)==6 and sum(v['selected'] for v in rows)==1
    assert row(client)['model']=='gpt-4.1-mini'
    assert row(client)['key_registered'] is False
    assert row(client)['test_result']=='untested'
    assert row(client,'ollama')['key_registered'] is None
    assert row(client,'compatible')['configuration_complete'] is False


def test_success_persistence_and_invalidation(client,monkeypatch):
    monkeypatch.setattr('studio.llm.generate_json',lambda *a:({'ok':True},{}))
    saved=client.put('/api/settings',json={'secrets':{'openai_key':'never-echo-this-key'}}).json()
    assert client.post('/api/settings/test/llm').status_code==200
    assert row(client)['test_result']=='success' and row(client)['tested_at']
    saved=client.get('/api/settings').json()
    assert 'never-echo-this-key' not in str(saved)
    assert not any(k.startswith('_llm') for k in saved)
    assert client.app.state.store.settings()['_llm_checks']['openai']['result']=='success'
    client.put('/api/settings',json={**saved,'theme':'light'})
    assert row(client)['test_result']=='success'
    client.put('/api/settings',json={**saved,'model':'changed-model'})
    assert row(client)['test_result']=='untested'


@pytest.mark.parametrize('change',[{'secrets':{'openai_key':'replacement'}},{'secrets':{'openai_key':''}}])
def test_credential_change_resets_check(client,monkeypatch,change):
    monkeypatch.setattr('studio.llm.generate_json',lambda *a:({'ok':True},{}))
    client.post('/api/settings/test/llm')
    client.put('/api/settings',json=change)
    assert row(client)['test_result']=='untested'


def test_failure_and_provider_independence(client,monkeypatch):
    def fail(*a):raise ValueError('test failure')
    monkeypatch.setattr('studio.llm.generate_json',fail)
    assert client.post('/api/settings/test/llm').status_code==400
    assert row(client)['test_result']=='failed'
    assert row(client,'anthropic')['test_result']=='untested'
    saved=client.get('/api/settings').json()
    client.put('/api/settings',json={**saved,'llm_provider':'anthropic'})
    assert row(client)['test_result']=='failed' and not row(client)['selected']
    assert row(client,'anthropic')['selected']


def test_stale_result_not_applied_and_local_block(client,monkeypatch):
    snapshot=client.app.state.store.settings()
    client.put('/api/settings',json={'model':'changed-model','privacy_mode':'local_only'})
    assert not record_check(client.app.state.store,'openai',snapshot,'success')
    assert row(client)['test_result']=='untested' and row(client)['blocked']
    assert not row(client,'ollama')['blocked']
    assert client.post('/api/settings/test/llm').status_code==403


def test_endpoint_change_invalidates_only_that_provider(client):
    client.put('/api/settings',json={'compatible_model':'test','compatible_url':'https://first.example/v1'})
    store=client.app.state.store;record_check(store,'compatible',store.settings(),'success');record_check(store,'openai',store.settings(),'success')
    saved=client.get('/api/settings').json()
    client.put('/api/settings',json={**saved,'compatible_url':'https://second.example/v1'})
    assert row(client,'compatible')['test_result']=='untested'
    assert row(client)['test_result']=='success'

@pytest.mark.parametrize('provider,settings,flags,expected',[
    ('openai',{}, {}, ['API 키']),
    ('openai',{}, {'openai_key':True}, []),
    ('compatible',{}, {}, ['모델 이름','API 기본 주소','API 키']),
    ('ollama',{'ollama_model':'','ollama_url':''}, {}, ['모델 이름','로컬 API 주소']),
])
def test_required_fields_for_each_provider(provider,settings,flags,expected):
    from studio.model_status import statuses
    value=next(r for r in statuses(settings,flags) if r['provider']==provider)
    assert value['missing_fields']==expected
