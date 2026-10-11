"""Explicit provider routing. No fallback or credential sharing across providers."""
import json
from urllib.parse import urlsplit
import httpx

PROVIDERS = {'openai':'ChatGPT · OpenAI API','anthropic':'Claude','freellmapi':'FreeLLMAPI','opencode':'OpenCode','compatible':'OpenAI 호환 API','ollama':'로컬 Ollama'}


def validate_gateway(value):
    local = urlsplit(value).hostname in ('localhost', '127.0.0.1', '::1')
    return validate_endpoint(value, local=local)


def list_models(vault, settings, provider):
    from .adapters import json_response
    if settings.get('privacy_mode') == 'local_only' and provider != 'ollama':
        raise ValueError('로컬 전용 모드에서는 외부 모델 목록을 조회할 수 없습니다.')
    if provider == 'opencode':
        from .opencode import models
        return models(vault, settings)
    if provider == 'openai':
        endpoint, key = 'https://api.openai.com/v1', vault.get('openai_key')
    elif provider == 'anthropic':
        endpoint, key = 'https://api.anthropic.com/v1', vault.get('anthropic_key')
    elif provider == 'freellmapi':
        endpoint, key = validate_gateway(settings.get('freellmapi_url','http://127.0.0.1:3001/v1')), vault.get('freellmapi_key')
    elif provider == 'ollama':
        endpoint, key = validate_endpoint(settings.get('ollama_url','http://127.0.0.1:11434/v1'), True), ''
    else:
        endpoint, key = validate_endpoint(settings.get('compatible_url','')), vault.get('compatible_key')
    if provider != 'ollama' and not key:
        raise ValueError('연결 설정에서 API 키를 먼저 저장하세요.')
    headers = {'x-api-key':key,'anthropic-version':'2023-06-01'} if provider == 'anthropic' else {'Authorization':'Bearer '+key} if key else {}
    with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
        data = json_response(client.get(endpoint+'/models', headers=headers), PROVIDERS[provider])
    return sorted({row['id'] for row in data.get('data', []) if isinstance(row, dict) and isinstance(row.get('id'), str)})


def validate_endpoint(value, local=False):
    u=urlsplit(value)
    if u.username or u.password or u.query or u.fragment or not u.hostname:
        raise ValueError('API 주소에는 인증정보·쿼리·해시를 넣을 수 없습니다.')
    if local:
        if u.hostname not in ('localhost','127.0.0.1','::1') or u.scheme not in ('http','https'):
            raise ValueError('로컬 모델 주소는 localhost 또는 127.0.0.1 이어야 합니다.')
    elif u.scheme!='https' or u.hostname in ('localhost','127.0.0.1','::1'):
        raise ValueError('외부 API 주소는 HTTPS 주소를 입력하세요.')
    return value.rstrip('/')


def generate_json(vault,settings,prompt,content,schema,name):
    from .adapters import RemoteError, json_response
    provider=settings.get('llm_provider','openai')
    if settings.get('privacy_mode')=='local_only' and provider!='ollama':
        raise ValueError('로컬 전용 모드에서는 로컬 Ollama 또는 직접 편집을 사용하세요.')
    label=PROVIDERS[provider]
    if provider == 'opencode':
        from .opencode import generate
        return generate(vault, settings, prompt, content, schema)
    # trust_env=False prevents a configured system proxy from receiving local data.
    with httpx.Client(timeout=httpx.Timeout(180,connect=10),trust_env=False,follow_redirects=False) as c:
        if provider=='openai':
            key=vault.get('openai_key')
            if not key: raise ValueError('OpenAI API 키를 설정하세요.')
            data=json_response(c.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key},json={
                'model':settings.get('model','gpt-4.1-mini'),'store':False,
                'input':[{'role':'developer','content':prompt},{'role':'user','content':content}],
                'text':{'format':{'type':'json_schema','name':name,'strict':True,'schema':schema}}}),label)
            output=''.join(v['text'] for o in data.get('output',[]) for v in o.get('content',[]) if v.get('type')=='output_text')
        elif provider=='anthropic':
            key=vault.get('anthropic_key')
            if not key: raise ValueError('Claude API 키를 설정하세요.')
            blocks=[]
            for part in content:
                if part['type']=='input_text': blocks.append({'type':'text','text':part['text']})
                else:
                    header,b64=part['image_url'].split(',',1)
                    blocks.append({'type':'image','source':{'type':'base64','media_type':header[5:].split(';')[0],'data':b64}})
            data=json_response(c.post('https://api.anthropic.com/v1/messages',headers={'x-api-key':key,'anthropic-version':'2023-06-01'},json={
                'model':settings.get('anthropic_model','claude-sonnet-4-6'),'max_tokens':6000,
                'system':prompt+'\nJSON 객체만 출력하세요. 스키마: '+json.dumps(schema,ensure_ascii=False),
                'messages':[{'role':'user','content':blocks}]}),label)
            output=''.join(v['text'] for v in data.get('content',[]) if v.get('type')=='text')
        else:
            local=provider=='ollama'
            gateway=provider=='freellmapi'
            endpoint=validate_gateway(settings.get('freellmapi_url','http://127.0.0.1:3001/v1')) if gateway else validate_endpoint(settings.get('ollama_url','http://127.0.0.1:11434/v1') if local else settings.get('compatible_url',''),local)
            key='' if local else vault.get('freellmapi_key' if gateway else 'compatible_key')
            if not local and not key: raise ValueError('호환 API 키를 설정하세요.')
            blocks=[{'type':'text','text':p['text']} if p['type']=='input_text' else {'type':'image_url','image_url':{'url':p['image_url']}} for p in content]
            data=json_response(c.post(endpoint+'/chat/completions',headers={'Authorization':'Bearer '+key} if key else {},json={
                'model':settings.get('freellmapi_model','auto') if gateway else settings.get('ollama_model','qwen3-vl:8b') if local else settings.get('compatible_model',''),
                'messages':[{'role':'system','content':prompt+'\nJSON 객체만 출력하세요. 스키마: '+json.dumps(schema,ensure_ascii=False)}, {'role':'user','content':blocks}],
                'response_format':{'type':'json_object'}}),label)
            try: output=data['choices'][0]['message']['content']
            except (KeyError,IndexError,TypeError): raise RemoteError('AI 응답 형식을 확인하지 못했습니다.') from None
    try:
        output=output.strip()
        if output.startswith('```'): output=output.split('\n',1)[1].rsplit('```',1)[0]
        parsed=json.loads(output)
        if not isinstance(parsed,dict): raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise RemoteError('AI가 올바른 JSON을 반환하지 않았습니다. 기존 콘텐츠는 보존했습니다.') from None
    return parsed,data.get('usage',{})
