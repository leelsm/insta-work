import json
import httpx
import pytest
from test_studio import client, MemoryVault, project
from studio.llm import generate_json, validate_endpoint
from studio.storage import Vault

@pytest.mark.parametrize('provider',['openai','anthropic','compatible','ollama'])
def test_routing_and_credential_isolation(monkeypatch,provider):
    vault=MemoryVault();vault.data={'openai_key':'openai-secret','anthropic_key':'claude-secret','compatible_key':'custom-secret'}
    captured=[]
    def handler(request):
        captured.append(request)
        data={'ok':True}
        if provider=='openai':body={'output':[{'content':[{'type':'output_text','text':json.dumps(data)}]}]}
        elif provider=='anthropic':body={'content':[{'type':'text','text':json.dumps(data)}]}
        else:body={'choices':[{'message':{'content':json.dumps(data)}}]}
        return httpx.Response(200,json=body)
    original=httpx.Client
    monkeypatch.setattr('studio.llm.httpx.Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    settings={'llm_provider':provider,'compatible_url':'https://llm.example/v1','compatible_model':'test'}
    content=[{'type':'input_text','text':'test'},{'type':'input_image','image_url':'data:image/jpeg;base64,YWJj'}]
    assert generate_json(vault,settings,'prompt',content,{},'test')[0]=={'ok':True}
    request=captured[0]
    expected={'openai':'Bearer openai-secret','anthropic':'claude-secret','compatible':'Bearer custom-secret','ollama':''}[provider]
    assert request.headers.get('x-api-key' if provider=='anthropic' else 'authorization','')==expected
    if provider=='anthropic':assert json.loads(request.content)['messages'][0]['content'][1]['source']['type']=='base64'
    if provider=='ollama':assert request.url.host=='127.0.0.1'

@pytest.mark.parametrize('url,local', [('http://cloud.example/v1',False),('https://user:secret@cloud.example/v1',False),('https://cloud.example/v1?key=secret',False),('http://192.168.1.2/v1',True),('https://cloud.example/v1',True)])
def test_unsafe_endpoints(url,local):
    with pytest.raises(ValueError):validate_endpoint(url,local)

def test_local_mode_blocks_before_any_request(monkeypatch):
    monkeypatch.setattr('studio.llm.httpx.Client',lambda **kw:pytest.fail('network attempted'))
    with pytest.raises(ValueError):generate_json(MemoryVault(),{'privacy_mode':'local_only','llm_provider':'anthropic'},'',[],{},'x')

def test_local_policy_routes_and_video_block(client):
    assert client.put('/api/settings',json={'privacy_mode':'local_only'}).status_code==200
    for path,method in [('/api/news','GET'),('/api/speech-test','POST'),('/api/settings/test/openai','POST'),('/api/publications/x/check','POST')]:
        assert client.request(method,path).status_code==403
    p=project(client)
    response=client.post(f'/api/projects/{p["id"]}/publish',json={'revision':1})
    assert response.status_code==400 and '차단' in response.json()['detail']

def test_vault_status_does_not_read_secrets(tmp_path,monkeypatch):
    monkeypatch.setattr('studio.storage.keyring.get_password',lambda *a:pytest.fail('secret read'))
    path=tmp_path/'credential-status.json';path.write_text('{"openai_key":true}')
    assert Vault(tmp_path).flags()['openai_key'] is True


def test_theme_persists_without_changing_security(client):
    client.put('/api/settings',json={'privacy_mode':'local_only','llm_provider':'ollama'})
    assert client.put('/api/appearance',json={'theme':'light'}).status_code==200
    result=client.get('/api/settings').json()
    assert result['theme']=='light' and result['privacy_mode']=='local_only' and result['llm_provider']=='ollama'
    assert client.put('/api/appearance',json={'theme':'bad'}).status_code==422
