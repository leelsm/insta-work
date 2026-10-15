import json
import subprocess
import threading
import pytest
import imageio_ffmpeg
from PIL import Image
from test_studio import client, payload
from test_daily import daily
from studio.renderer import render, file_hash
from studio.storage import Store
from studio.maintenance import backup, restore
from studio.transfer import export_project, import_project


def test_thumbnail_index_validation_and_approval_invalidation(client):
    p=daily(client)
    p['thumbnail_scene']=2
    assert client.post('/api/projects',json=p).status_code==422
    p['thumbnail_scene']=1
    saved=client.post('/api/projects',json=p).json()
    saved['render']={'revision':1,'folder':'previous','duration':4}
    client.app.state.store.put('projects',saved)
    assert client.post(f'/api/projects/{saved["id"]}/approve',json={'revision':1}).status_code==200
    changed=client.put('/api/projects/'+saved['id'],json={**saved,'thumbnail_scene':0}).json()
    assert changed['render'] is None and not changed['approved_hash']
    assert changed['scenes']==saved['scenes'] and changed['photos']==saved['photos']


def test_thumbnail_transfer_roundtrip_and_legacy_default(client,tmp_path):
    p=client.post('/api/projects',json={**daily(client),'thumbnail_scene':1}).json()
    transfer=export_project(client.app.state.store,p)
    assert transfer['project']['thumbnailSceneID']==transfer['project']['scenes'][1]['id']
    restored=import_project(Store(tmp_path/'second'),json.dumps(transfer).encode())
    assert restored['thumbnail_scene']==1
    del transfer['project']['thumbnailSceneID']
    assert import_project(Store(tmp_path/'legacy'),json.dumps(transfer).encode())['thumbnail_scene']==0
    transfer['project']['thumbnailSceneID']='missing'
    with pytest.raises(ValueError,match='썸네일'): import_project(Store(tmp_path/'invalid'),json.dumps(transfer).encode())


@pytest.mark.parametrize('kind',['daily','news'])
def test_selected_scene_image_saved_and_embedded_without_reordering(client,tmp_path,kind):
    p=daily(client,2)
    from test_daily import photo_bytes
    import io
    # Distinct colours make a wrong scene selection detectable.
    photos=[]
    for color in ['#aa2020','#2080aa']:
        buf=io.BytesIO();Image.new('RGB',(720,1280),color).save(buf,'PNG')
        photos.append(client.post('/api/photos?filename=test.png',content=buf.getvalue()).json())
    if kind=='daily': p.update(photos=photos)
    else:
        p=payload();p['scenes']=[dict(p['scenes'][0],title='첫 장면',narration='',image_asset_id=photos[0]['asset_id']),dict(p['scenes'][0],title='둘째 장면',narration='',image_asset_id=photos[1]['asset_id'])]
    p.update(thumbnail_scene=1,music_id='',motion='still',transition='fade')
    project=client.post('/api/projects',json=p).json();out=client.app.state.store.media/project['id']/'thumbnail-test'
    result=render(project,out,client.app.state.vault,client.app.state.store.settings(),threading.Event(),lambda *args:None,lambda *args:None,assets=client.app.state.store.assets)
    assert result['thumbnail'] and result['thumbnail_scene']==1 and result['thumbnail_time']==3
    assert result['duration']==4 and result['sha256']==file_hash(out/'video.mp4')
    with Image.open(out/'thumbnail.jpg') as im:
        assert im.size==(1080,1920)
        r,g,b=im.getpixel((100,600));assert b>r+50
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    probe=subprocess.run([ffmpeg,'-hide_banner','-i',str(out/'video.mp4')],capture_output=True,text=True)
    assert 'attached pic' in probe.stderr,probe.stderr
    attached=tmp_path/(kind+'-embedded.jpg')
    subprocess.run([ffmpeg,'-y','-i',str(out/'video.mp4'),'-map','0:v:1','-c','copy',str(attached)],check=True,capture_output=True)
    assert attached.read_bytes()==(out/'thumbnail.jpg').read_bytes()
    project.update(render=result,state='REVIEW_READY');client.app.state.store.put('projects',project)
    response=client.get(f'/media/{project["id"]}/thumbnail-test/thumbnail.jpg');assert response.status_code==200 and response.headers['content-type']=='image/jpeg'
    target=Store(tmp_path/(kind+'-backup'));restore(target,backup(client.app.state.store))
    restored=next(p for p in target.list('projects') if p['title']==project['title'])
    assert restored['thumbnail_scene']==1 and (target.media/restored['id']/restored['render']['folder']/'thumbnail.jpg').is_file()
    assert client.get('/api/projects/'+project['id']).json()['scenes']==project['scenes']
