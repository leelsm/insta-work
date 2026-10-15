import base64
import io
import time
import threading
import pytest
from PIL import Image
from test_studio import client, project
from test_daily import daily


def wait_job(client, job_id):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        job=next(j for j in client.get('/api/jobs').json() if j['id']==job_id)
        if job['status']!='RUNNING': return job
        time.sleep(.02)
    pytest.fail('job did not finish')


def configured(client):
    client.put('/api/settings',json={'secrets':{'openai_key':'offline-test-key'}})
    payload=daily(client,3);payload['caption']='사용자가 쓴 게시 문안';payload['scenes'][1]['body']='유지할 본문'
    return client.post('/api/projects',json=payload).json()


def test_only_selected_photo_and_caption_are_used(client,monkeypatch):
    p=configured(client);seen={}
    def fake(vault,settings,prompt,content,*args):
        seen['photos']=[v['image_url'] for v in content if v['type']=='input_image']
        seen['model']=settings['model']
        return {'subtitles':['  선택 사진 추천  '],'caption':'적용하면 안 되는 게시 문안'},{'input_tokens':3,'output_tokens':1}
    monkeypatch.setattr('studio.llm.generate_json',fake)
    response=client.post(f'/api/projects/{p["id"]}/generate',json={'revision':p['revision'],'scene_index':1,'provider':'openai','model':'chosen-vision-model'})
    assert response.status_code==200,response.text
    job=wait_job(client,response.json()['id']);assert job['status']=='DONE',job['message']
    assert job['scene_index']==1 and seen['model']=='chosen-vision-model'
    assert len(seen['photos'])==1
    with Image.open(client.app.state.store.assets/(p['photos'][1]['asset_id']+'.jpg')) as image:
        image.thumbnail((768,768));buf=io.BytesIO();image.save(buf,'JPEG',quality=80)
    assert base64.b64decode(seen['photos'][0].split(',')[1])==buf.getvalue()
    updated=client.get('/api/projects/'+p['id']).json()
    expected=[dict(s) for s in p['scenes']];expected[1]['narration']='선택 사진 추천'
    assert updated['scenes']==expected
    for field in ('title','caption','photos','music_id','motion','subtitle_style','description','tone','mood'):
        assert updated[field]==p[field]
    assert updated['revision']==p['revision']+1 and updated['render'] is None and not updated['approved_hash']


@pytest.mark.parametrize('text',['', '가'*161, None])
def test_invalid_suggestion_keeps_edits(client,monkeypatch,text):
    p=configured(client)
    monkeypatch.setattr('studio.llm.generate_json',lambda *args:({'subtitles':[text],'caption':''},{}))
    response=client.post(f'/api/projects/{p["id"]}/generate',json={'revision':p['revision'],'scene_index':2})
    assert wait_job(client,response.json()['id'])['status']=='FAILED'
    updated=client.get('/api/projects/'+p['id']).json()
    assert updated['scenes']==p['scenes'] and updated['caption']==p['caption'] and updated['revision']==p['revision']


def test_scene_index_checks_before_ai(client,monkeypatch):
    p=configured(client)
    monkeypatch.setattr('studio.llm.generate_json',lambda *args:pytest.fail('invalid request contacted AI'))
    for index,code in [(-1,422),(3,400),(10,422)]:
        assert client.post(f'/api/projects/{p["id"]}/generate',json={'revision':p['revision'],'scene_index':index}).status_code==code
    news=project(client)
    assert client.post(f'/api/projects/{news["id"]}/generate',json={'revision':news['revision'],'scene_index':0}).status_code==400
    assert client.post(f'/api/projects/{p["id"]}/generate',json={'revision':2,'scene_index':0}).status_code==409
    assert not client.get('/api/jobs').json()


def test_cancelled_scene_suggestion_keeps_edits(client,monkeypatch):
    p=configured(client);entered=threading.Event();release=threading.Event()
    def fake(*args):
        entered.set();assert release.wait(3)
        return {'subtitles':['취소된 추천'],'caption':'적용 안 함'},{}
    monkeypatch.setattr('studio.llm.generate_json',fake)
    response=client.post(f'/api/projects/{p["id"]}/generate',json={'revision':p['revision'],'scene_index':0})
    job=response.json();assert entered.wait(3)
    try: assert client.post('/api/jobs/'+job['id']+'/cancel').status_code==200
    finally: release.set()
    assert wait_job(client,job['id'])['status']=='INTERRUPTED'
    updated=client.get('/api/projects/'+p['id']).json()
    assert updated['scenes']==p['scenes'] and updated['caption']==p['caption'] and updated['revision']==p['revision']
