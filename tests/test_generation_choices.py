import json
import threading
from pathlib import Path

import httpx
import pytest

from test_studio import client, project, MemoryVault
from studio.llm import generate_json
from studio.models import SettingsInput
from studio.model_status import generation_settings, record_check, statuses
from studio.opencode import environment, generate, parse_events


@pytest.mark.parametrize('provider,config', [
    ('anthropic', {'secrets': {'anthropic_key': 'claude-only'}}),
    ('ollama', {'privacy_mode': 'local_only'}),
    ('freellmapi', {'secrets': {'freellmapi_key': 'gateway-only'}}),
    ('opencode', {'secrets': {'freellmapi_key': 'gateway-only'}}),
])
def test_selected_provider_starts_without_openai_key(client, monkeypatch, provider, config):
    monkeypatch.setattr('studio.opencode.executable', lambda: '/test/opencode')
    assert client.put('/api/settings', json=config).status_code == 200
    p = project(client)
    seen = {}
    def start(kind, project, options):
        seen.update(options['settings'])
        return {'ok': True}
    monkeypatch.setattr(client.app.state.jobs, 'start', start)
    model = 'freellmapi/auto:fast' if provider == 'opencode' else 'chosen-model'
    r = client.post(f'/api/projects/{p["id"]}/generate', json={'revision':1, 'provider':provider, 'model':model})
    assert r.status_code == 200, r.text
    assert seen['llm_provider'] == provider
    from studio.model_status import FIELDS
    assert seen[FIELDS[provider][0]] == model
    assert client.get('/api/settings').json()['llm_provider'] == 'openai'
    assert 'secrets' not in seen


def test_missing_connection_and_private_mode_do_not_start_job(client):
    p = project(client)
    url = f'/api/projects/{p["id"]}/generate'
    assert client.post(url, json={'revision':1,'provider':'anthropic'}).status_code == 400
    client.put('/api/settings', json={'privacy_mode':'local_only','secrets':{'freellmapi_key':'key'}})
    assert client.post(url, json={'revision':1,'provider':'freellmapi'}).status_code == 400
    assert client.post('/api/settings/models/freellmapi', json={}).status_code == 400
    assert client.get('/api/jobs').json() == []
    assert client.get('/api/projects/'+p['id']).json()['revision'] == 1


def test_video_preview_and_download_have_distinct_dispositions(client):
    p=project(client)
    folder=client.app.state.store.media/p['id']/'render-test'
    folder.mkdir(parents=True)
    (folder/'video.mp4').write_bytes(b'video-test')
    url=f'/media/{p["id"]}/render-test/video.mp4'
    preview=client.get(url)
    download=client.get(url+'?download=1')
    assert preview.status_code==download.status_code==200
    assert 'content-disposition' not in preview.headers
    assert download.headers['content-disposition']=='attachment; filename="video.mp4"'
    assert preview.content==download.content


def test_freellmapi_uses_only_gateway_key_and_selected_model(monkeypatch):
    vault = MemoryVault()
    vault.data = {'openai_key':'unrelated', 'freellmapi_key':'gateway-key'}
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'choices':[{'message':{'content':'{"ok":true}'}}]})
    original = httpx.Client
    monkeypatch.setattr('studio.llm.httpx.Client', lambda **kwargs:original(transport=httpx.MockTransport(handler), **kwargs))
    result, _ = generate_json(vault, {'llm_provider':'freellmapi','freellmapi_model':'auto:fast'}, 'prompt', [{'type':'input_text','text':'hi'}], {}, 'test')
    assert result == {'ok':True}
    assert str(requests[0].url) == 'http://127.0.0.1:3001/v1/chat/completions'
    assert requests[0].headers['authorization'] == 'Bearer gateway-key'
    assert json.loads(requests[0].content)['model'] == 'auto:fast'


@pytest.mark.parametrize('url', ['http://remote.example/v1','http://user:secret@localhost:3001/v1','http://localhost:3001/v1?key=secret'])
def test_gateway_endpoint_rejects_unsafe_addresses(url):
    with pytest.raises(ValueError):
        SettingsInput(freellmapi_url=url)


def test_opencode_gateway_key_rotation_invalidates_test(client, monkeypatch):
    monkeypatch.setattr('studio.opencode.executable', lambda:'/test/opencode')
    saved=client.put('/api/settings',json={'secrets':{'freellmapi_key':'first'}}).json()
    store=client.app.state.store
    record_check(store, 'opencode', store.settings(), 'success')
    saved=client.put('/api/settings',json={**saved,'secrets':{'freellmapi_key':'next'}}).json()
    row=next(r for r in saved['model_status'] if r['provider']=='opencode')
    assert row['test_result']=='untested'


def test_opencode_environment_contains_only_gateway_credential():
    vault=MemoryVault();vault.data={'freellmapi_key':'gateway-secret','openai_key':'do-not-share'}
    env=environment(vault, {})
    config=json.loads(env['OPENCODE_CONFIG_CONTENT'])
    assert config['share']=='disabled'
    assert config['agent']['studio-content']['permission']=={'*':'deny'}
    assert env['STUDIO_FREELLMAPI_KEY']=='gateway-secret'
    assert 'gateway-secret' not in env['OPENCODE_CONFIG_CONTENT']
    assert 'do-not-share' not in str(config)


def test_opencode_subprocess_receives_prompt_images_and_cleans_up(monkeypatch, tmp_path):
    cli=tmp_path/'opencode'
    cli.write_text('''#!/usr/bin/env python3
import sys,json,pathlib
assert '--format' in sys.argv and 'studio-content' in sys.argv
assert 'freellmapi/auto' in sys.argv
image=pathlib.Path(sys.argv[sys.argv.index('--file')+1])
assert image.read_bytes()==b'photo'
assert 'draft prompt' in sys.stdin.read()
print(json.dumps({'type':'text','part':{'text':json.dumps({'caption':'ready','directory':str(image.parent)})}}))
''')
    cli.chmod(0o700)
    monkeypatch.setattr('studio.opencode.executable', lambda:str(cli))
    vault=MemoryVault();vault.data={'freellmapi_key':'key'}
    result,_=generate(vault, {}, 'draft prompt', [{'type':'input_image','image_url':'data:image/jpeg;base64,cGhvdG8='}], {})
    assert result['caption']=='ready'
    assert not Path(result['directory']).exists()


@pytest.mark.parametrize('output', ['{"type":"error","error":{"message":"secret"}}', '{"type":"text","part":{"text":"not json"}}', '{"type":"text","part":{"text":"[]"}}'])
def test_opencode_invalid_response_is_safe(output):
    with pytest.raises(ValueError, match='기존 콘텐츠는 보존'):
        parse_events(output)
