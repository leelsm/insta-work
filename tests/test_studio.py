import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from studio.api import create_app
from studio.jobs import digest
from studio.renderer import render
from studio.storage import Store


class MemoryVault:
    def __init__(self):
        self.data = {}
    def get(self, name):
        return self.data.get(name, '')
    def set(self, name, value):
        self.data[name] = value
    def flags(self):
        return {k: bool(v) for k, v in self.data.items() if not k.startswith('account:')}


@pytest.fixture
def client(tmp_path):
    app = create_app(Store(tmp_path), MemoryVault(), session_token='test-token')
    with TestClient(app) as c:
        assert c.post('/api/session', json={'token': 'test-token'}).status_code == 200
        c.headers['x-studio-token'] = 'test-token'
        c.app = app
        yield c


def payload():
    return {'title':'한국어 편집 테스트','sources':[{'title':'직접 작성 자료','text':'아침에 할 일을 한 줄로 기록하세요.'}],
            'scenes':[{'title':'작은 습관, 새로운 하루','body':'아침에 할 일을 한 줄로 적어 보세요.','narration':'작은 습관으로 하루를 시작하세요.','duration':2,'source_ids':[0]}],
            'caption':'직접 작성한 테스트 콘텐츠입니다.'}


def project(client):
    response = client.post('/api/projects', json=payload())
    assert response.status_code == 200, response.text
    return response.json()


def test_session_and_csrf(client):
    assert client.get('/api/projects', headers={'origin':'https://attacker.example'}).status_code == 403
    assert client.post('/api/projects', json=payload(), headers={'x-studio-token':''}).status_code == 403
    client.cookies.clear()
    assert client.get('/api/projects').status_code == 401
    assert client.post('/api/session', json={'token':'invalid'}).status_code == 401


def test_secret_never_in_db_or_response(client):
    r = client.put('/api/settings',json={'secrets':{'openai_key':'secret-not-for-db'}})
    assert r.status_code == 200
    assert 'secret-not-for-db' not in r.text
    assert 'secret-not-for-db' not in client.app.state.store.db.read_bytes().decode(errors='ignore')
    assert client.app.state.vault.get('openai_key') == 'secret-not-for-db'
    assert client.put('/api/settings',json={'secrets':{'unknown':'x'}}).status_code == 400


def test_provider_test_checks_saved_model_without_changing_selection(client, monkeypatch):
    settings=client.get('/api/settings').json()
    client.put('/api/settings',json={**settings,'anthropic_model':'claude-test-model','secrets':{'anthropic_key':'test-key'}})
    seen={}
    def fake_generate(vault,snapshot,*args):
        seen['provider']=snapshot['llm_provider']
        assert vault.get('anthropic_key')=='test-key'
        return {'ok':True},{}
    monkeypatch.setattr('studio.llm.generate_json',fake_generate)
    response=client.post('/api/settings/test/llm/anthropic')
    assert response.status_code==200,response.text
    assert seen['provider']=='anthropic'
    updated=client.get('/api/settings').json()
    assert updated['llm_provider']=='openai'
    row=next(item for item in updated['model_status'] if item['provider']=='anthropic')
    assert row['test_result']=='success'


def test_provider_test_requires_complete_settings(client, monkeypatch):
    monkeypatch.setattr('studio.llm.generate_json',lambda *args:pytest.fail('missing setup must not call provider'))
    response=client.post('/api/settings/test/llm/compatible')
    assert response.status_code==400
    assert 'API 키' in response.json()['detail']


def test_local_only_allows_testing_ollama_provider(client, monkeypatch):
    settings=client.get('/api/settings').json()
    client.put('/api/settings',json={**settings,'privacy_mode':'local_only','ollama_model':'qwen3-vl:8b'})
    seen={}
    def fake_generate(vault,snapshot,*args):
        seen['provider']=snapshot['llm_provider']
        return {'ok':True},{}
    monkeypatch.setattr('studio.llm.generate_json',fake_generate)
    response=client.post('/api/settings/test/llm/ollama')
    assert response.status_code==200,response.text
    assert seen['provider']=='ollama'


def test_approval_invalidation_and_optimistic_lock(client):
    p = project(client)
    assert client.post(f'/api/projects/{p["id"]}/approve',json={'revision':1}).status_code == 400
    p['render'] = {'folder':'test','revision':1,'duration':2}
    client.app.state.store.put('projects',p)
    approved = client.post(f'/api/projects/{p["id"]}/approve',json={'revision':1}).json()
    assert approved['approved_hash'] == digest(approved)
    approved['caption'] = '변경한 게시글'
    updated = client.put(f'/api/projects/{p["id"]}',json=approved).json()
    assert updated['revision'] == 2
    assert updated['render'] is None
    assert not updated['approved_hash']
    assert client.put(f'/api/projects/{p["id"]}',json=approved).status_code == 409
    assert client.post(f'/api/projects/{p["id"]}/publish',json={'revision':2}).status_code == 400


def test_sources_and_path_traversal(client):
    bad=payload();bad['scenes'][0]['source_ids']=[30]
    assert client.post('/api/projects',json=bad).status_code == 422
    assert client.get('/media/a/b/ffmpeg.log').status_code == 404
    assert client.get('/manuals/not-found').status_code == 404


def test_delete_project_removes_project_and_rendered_media(client):
    p = project(client)
    media_dir = client.app.state.store.media / p['id']
    media_dir.mkdir()
    (media_dir / 'video.mp4').write_bytes(b'test')
    response = client.delete(f'/api/projects/{p["id"]}')
    assert response.status_code == 200
    assert response.json()['deleted'] is True
    assert all(item['id'] != p['id'] for item in client.get('/api/projects').json())
    assert not media_dir.exists()
    assert client.delete(f'/api/projects/{p["id"]}').status_code == 404


def test_selected_news_article_summary_endpoint(client, monkeypatch):
    monkeypatch.setattr('studio.article_summary.article_summary', lambda url, title: {
        'text': '원문에서 추린 편집 가능한 요약입니다.', 'url': url, 'method': 'local_extractive'
    })
    response = client.post('/api/news/article-summary', json={
        'url': 'https://news.example/article/1', 'title': '뉴스 제목'
    })
    assert response.status_code == 200
    assert response.json()['text'] == '원문에서 추린 편집 가능한 요약입니다.'


def test_recovery_never_republishes(client):
    p = project(client)
    store = client.app.state.store
    job={'id':'job','project_id':p['id'],'kind':'publish','status':'RUNNING','message':'게시 요청 중'}
    pub={'id':'pub','project_id':p['id'],'revision':1,'account_id':'a','status':'PUBLISHING'}
    store.put('jobs',job);store.put('publications',pub)
    store.recover()
    assert store.get('jobs','job')['status']=='INTERRUPTED'
    assert store.get('publications','pub')['status']=='NEEDS_RECONCILIATION'


def test_real_korean_mp4_export(client):
    p = project(client)
    r = client.post(f'/api/projects/{p["id"]}/render',json={'revision':1})
    assert r.status_code == 200,r.text
    assert client.put(f'/api/projects/{p["id"]}',json=p).status_code == 409
    deadline=time.monotonic()+35
    while time.monotonic()<deadline:
        jobs=client.get('/api/jobs').json()
        if jobs[0]['status']!='RUNNING':break
        time.sleep(.1)
    assert jobs[0]['status']=='DONE',jobs[0]
    p=client.get(f'/api/projects/{p["id"]}').json()
    assert p['state']=='REVIEW_READY'
    assert p['render']['music_id']=='slow-morning'
    root=f'/media/{p["id"]}/{p["render"]["folder"]}/'
    for filename in ('video.mp4','subtitles.srt','cards.zip','project.json'):
        r=client.get(root+filename)
        assert r.status_code==200 and len(r.content)>50
    assert '작은 습관' in client.get(root+'subtitles.srt').text
    import subprocess
    from studio.renderer import imageio_ffmpeg
    video=client.app.state.store.media/p['id']/p['render']['folder']/'video.mp4'
    decoded=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(video),'-t','1','-map','0:a:0','-f','s16le','-ac','1','-ar','8000','pipe:1'],capture_output=True,check=True)
    assert decoded.stdout and any(decoded.stdout), 'news MP4 audio should contain the default music track'


def test_cancel_render_before_start(tmp_path):
    p={**payload(),'template':'ink','accent':'#b8f569','brand':'TEST','voice':False,'revision':1}
    event=threading.Event();event.set()
    with pytest.raises(InterruptedError):
        render(p,tmp_path,MemoryVault(),{},event,lambda *_:None,lambda *_:None)


def test_duplicate_publication_is_blocked(client,monkeypatch):
    client.app.state.store.save_settings({'allow_video_upload':True})
    import studio.adapters
    monkeypatch.setattr(studio.adapters,'s3_client',lambda *_:object())
    p=project(client)
    account={'id':'account','name':'테스트','user_id':'123','status':'CONNECTED'}
    client.app.state.store.put('accounts',account)
    p.update(account_id='account',render={'folder':'test','revision':1},state='APPROVED')
    p['approved_hash']=digest(p)
    client.app.state.store.put('projects',p)
    client.app.state.store.put('publications',{'id':'existing','project_id':p['id'],'revision':1,'account_id':'account','status':'NEEDS_RECONCILIATION'})
    r=client.post(f'/api/projects/{p["id"]}/publish',json={'revision':1})
    assert r.status_code==400
    assert '기존 게시 요청' in r.json()['detail']


def test_validation_does_not_echo_credentials(client):
    r=client.post('/api/accounts',json={'name':'test','user_id':'bad','token':'private-token-never-echo'})
    assert r.status_code==422
    assert 'private-token-never-echo' not in r.text


@pytest.mark.parametrize('timeout_at,expected',[('', 'PUBLISHED'),('create','NEEDS_RECONCILIATION'),('publish','NEEDS_RECONCILIATION'),('upload','FAILED')])
def test_publication_state_machine(client,monkeypatch,timeout_at,expected):
    import httpx
    import studio.jobs as module
    from studio.renderer import file_hash
    p=project(client)
    store=client.app.state.store
    directory=store.media/p['id']/'render-test';directory.mkdir(parents=True)
    path=directory/'video.mp4';path.write_bytes(b'local-rendered-video')
    p.update(account_id='a',render={'folder':'render-test','revision':1,'sha256':file_hash(path)},state='APPROVED')
    p['approved_hash']=digest(p);store.put('projects',p)
    store.put('accounts',{'id':'a','user_id':'123','status':'CONNECTED','name':'test'})
    calls=[]
    class FakeMeta:
        def __init__(self,*_):pass
        def create(self,url,caption):
            calls.append('create')
            if timeout_at=='create':raise httpx.ReadTimeout('sensitive-provider-message')
            return {'id':'container'}
        def status(self,id):return {'status_code':'FINISHED'}
        def publish(self,id):
            calls.append('publish')
            if timeout_at=='publish':raise httpx.ReadTimeout('sensitive-provider-message')
            return {'id':'media'}
        def media(self,id):return {'id':'media','permalink':'https://www.instagram.com/reel/test/'}
    def fake_upload(*_):
        calls.append('upload')
        if timeout_at=='upload':raise ValueError('upload failed')
        return 'https://example.s3.amazonaws.com/file.mp4'
    class Event:
        def is_set(self):return False
        def wait(self,*_):return False
        def set(self):pass
    monkeypatch.setattr(module,'Meta',FakeMeta);monkeypatch.setattr(module,'upload_video',fake_upload)
    job={'id':'j','project_id':p['id'],'kind':'publish','status':'RUNNING','publication_id':'pub'}
    pub={'id':'pub','project_id':p['id'],'revision':1,'account_id':'a','stage':'LOCAL','status':'UPLOADING'}
    store.put('jobs',job);store.put('publications',pub)
    manager=client.app.state.jobs;manager.events['j']=Event();manager.run(job,p,{})
    assert store.get('publications','pub')['status']==expected
    assert calls.count('create')<=1 and calls.count('publish')<=1
    assert 'sensitive-provider-message' not in json.dumps(store.get('jobs','j'))


def test_logo_rejects_remote_or_invalid_image(client):
    data=payload();data['logo']='https://attacker.example/image.png'
    assert client.post('/api/projects',json=data).status_code==422


def test_backup_restore_preserves_existing_and_requires_reapproval(client):
    import io,zipfile
    p=project(client)
    client.app.state.vault.set('openai_key','hidden-vault-key')
    r=client.get('/api/backup')
    assert r.status_code==200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        data=json.loads(z.read('backup.json'))
        assert 'hidden-vault-key' not in json.dumps(data)
    restored=client.post('/api/restore',content=r.content,headers={'Content-Type':'application/zip'})
    assert restored.status_code==200,restored.text
    assert restored.json()['restored']==1
    projects=client.get('/api/projects').json()
    assert len(projects)==2
    imported=next(x for x in projects if x['id']!=p['id'])
    assert imported['approved_hash']=='' and imported['state']=='EDITABLE'


def test_restore_does_not_extract_arbitrary_paths(client,tmp_path):
    import io,zipfile
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        z.writestr('backup.json',json.dumps({'format':'instagram-content-studio','version':1,'projects':[]}))
        z.writestr('../../escape.txt','malicious')
    r=client.post('/api/restore',content=out.getvalue(),headers={'Content-Type':'application/zip'})
    assert r.status_code==200
    assert not (client.app.state.store.root.parent/'escape.txt').exists()


def test_tts_timing_uses_actual_wav_lengths(tmp_path,monkeypatch):
    import io,wave
    import studio.renderer as module
    def wav(*_):
        out=io.BytesIO()
        with wave.open(out,'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0\0'*24000)
        return out.getvalue()
    monkeypatch.setattr(module,'speech',wav)
    p={**payload(),'template':'paper','accent':'#b8f569','brand':'TEST','voice':True,'revision':1}
    p['scenes'][0]['narration']='첫 문장입니다. 두 번째 문장입니다.'
    r=render(p,tmp_path,MemoryVault(),{},threading.Event(),lambda *_:None,lambda *_:None)
    assert r['duration']==2
    assert '00:00:00,000 --> 00:00:01,000' in (tmp_path/'subtitles.srt').read_text()
    assert '00:00:01,000 --> 00:00:02,000' in (tmp_path/'subtitles.srt').read_text()


def test_launcher_single_instance_and_shutdown(tmp_path):
    import os,socket,subprocess,sys
    import httpx
    root=Path(__file__).resolve().parent.parent
    s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
    env={**os.environ,'STUDIO_DATA_DIR':str(tmp_path/'app')}
    args=[sys.executable,str(root/'run.py'),'--browser','--port',str(port),'--no-open']
    proc=subprocess.Popen(args,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        metadata=tmp_path/'app'/'instance.json'
        deadline=time.monotonic()+10
        while not metadata.exists() and time.monotonic()<deadline:
            assert proc.poll() is None
            time.sleep(.05)
        assert metadata.exists()
        meta=json.loads(metadata.read_text())
        second=subprocess.run(args,cwd=root,env=env,capture_output=True,timeout=10)
        assert second.returncode==0
        assert json.loads(metadata.read_text())['token']==meta['token']
        with httpx.Client(base_url=meta['base'],trust_env=False) as c:
            assert c.get('/api/health').status_code==200
            assert c.post('/api/session',json={'token':meta['token']}).status_code==200
            assert c.post('/api/shutdown',headers={'X-Studio-Token':meta['token']}).status_code==200
        assert proc.wait(timeout=10)==0
        assert not metadata.exists()
        s=socket.socket();assert s.connect_ex(('127.0.0.1',port))!=0;s.close()
        # A clean app restart should reuse the configured port immediately.
        proc=subprocess.Popen(args,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=time.monotonic()+10
        while not metadata.exists() and time.monotonic()<deadline:
            assert proc.poll() is None
            time.sleep(.05)
        assert metadata.exists()
        meta=json.loads(metadata.read_text())
        with httpx.Client(base_url=meta['base'],trust_env=False) as c:
            assert c.post('/api/session',json={'token':meta['token']}).status_code==200
            c.post('/api/shutdown',headers={'X-Studio-Token':meta['token']})
        assert proc.wait(timeout=10)==0
    finally:
        if proc.poll() is None:proc.terminate();proc.wait(timeout=10)


@pytest.mark.parametrize('provider,url,header', [
    ('hub', 'https://naverapihub.apigw.ntruss.com/search/v1/news', 'X-NCP-APIGW-API-KEY-ID'),
    ('legacy', 'https://openapi.naver.com/v1/search/news.json', 'X-Naver-Client-Id'),
])
def test_news_provider_routing_and_results(monkeypatch, provider, url, header):
    import httpx
    from datetime import datetime, timezone, timedelta
    from email.utils import format_datetime
    from studio import adapters
    vault = MemoryVault(); vault.data = {'naver_id':'sample-id','naver_secret':'sample-secret'}
    def handle(request):
        assert str(request.url).split('?')[0] == url
        assert request.headers[header] == 'sample-id'
        other = 'X-Naver-Client-Id' if provider == 'hub' else 'X-NCP-APIGW-API-KEY-ID'
        assert other not in request.headers
        assert request.url.params['query'] == '한국어'
        article = {'title':'<b>뉴스</b> &amp; 이야기','description':'<b>요약</b>',
                   'originallink':'https://example.org/article#section','pubDate':format_datetime(datetime.now(timezone.utc))}
        old = {**article,'originallink':'https://example.org/old', 'pubDate':format_datetime(datetime.now(timezone.utc)-timedelta(days=90))}
        return httpx.Response(200,json={'items':[article,article,old]})
    monkeypatch.setattr(adapters,'client',lambda:httpx.Client(transport=httpx.MockTransport(handle)))
    result = adapters.search_news(vault,'한국어',provider=provider)
    assert len(result) == 1
    assert result[0]['title'] == '뉴스 & 이야기'
    assert result[0]['url'] == 'https://example.org/article'
