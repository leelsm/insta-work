import io
import threading
import pytest
from PIL import Image
from test_studio import client
from studio.daily import save_photo, asset_path
from studio.maintenance import backup, restore
from studio.storage import Store


def photo_bytes():
    buf=io.BytesIO(); Image.new('RGB',(480,640),'#7a91a5').save(buf,'PNG'); return buf.getvalue()


def daily(client, count=2):
    photos=[client.post('/api/photos?filename=sample.png',content=photo_bytes()).json() for _ in range(count)]
    return {'title':'일상 영상 검증','content_type':'daily','photos':photos,
            'scenes':[{'title':'사진','narration':f'오늘의 기록 {i+1}','body':'','duration':2,'source_ids':[]} for i in range(count)],
            'voice':False,'music_id':'slow-morning','motion':'zoom','transition':'fade'}


def test_bad_photo_and_missing_asset(client):
    assert client.post('/api/photos?filename=x.jpg',content=b'not an image').status_code==400
    p=daily(client); p['photos'][0]['asset_id']='a'*32
    assert client.post('/api/projects',json=p).status_code==400


def test_photo_upload_resizes_and_compresses_for_reels(tmp_path):
    import io
    from PIL import Image
    raw=io.BytesIO();Image.effect_noise((3000,1600),80).convert('RGB').save(raw,'PNG')
    saved=save_photo(tmp_path,raw.getvalue(),'portrait memory.png')
    path=asset_path(tmp_path,saved['asset_id'])
    with Image.open(path) as image:
        assert image.format=='JPEG'
        assert image.size==(1920,1024)
    assert path.stat().st_size < len(raw.getvalue())
    assert saved['fit']=='cover' and saved['position_x']==saved['position_y']==.5


@pytest.mark.parametrize('count',[0,11])
def test_daily_photo_count(client,count):
    assert client.post('/api/projects',json=daily(client,count)).status_code==422


def test_daily_scene_count(client):
    p=daily(client); p['scenes'].pop()
    assert client.post('/api/projects',json=p).status_code==422


def test_daily_backup(client,tmp_path):
    p=client.post('/api/projects',json=daily(client)).json()
    target=Store(tmp_path/'restore'); restore(target,backup(client.app.state.store))
    restored=target.list('projects')[0]
    assert restored['photos'][0]['asset_id']!=p['photos'][0]['asset_id']
    assert asset_path(target.assets,restored['photos'][0]['asset_id']).is_file()
    assert not restored['approved_hash']


def test_daily_render_music(client):
    import time
    p=client.post('/api/projects',json=daily(client)).json()
    response=client.post(f'/api/projects/{p["id"]}/render',json={'revision':p['revision']})
    assert response.status_code==200,response.text
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        job=client.get('/api/jobs').json()[0]
        if job['status']!='RUNNING': break
        time.sleep(.1)
    assert job['status']=='DONE',job
    p=client.get(f'/api/projects/{p["id"]}').json()
    root=f'/media/{p["id"]}/{p["render"]["folder"]}/'
    assert p['render']['music_id']=='slow-morning'
    assert p['render']['duration']==4
    assert len(client.get(root+'video.mp4').content)>1000
    assert '오늘의 기록 2' in client.get(root+'subtitles.srt').text
    assert 'CC0' in client.get(root+'music-license.txt').text


@pytest.mark.parametrize('format', ['JPEG', 'PNG'])
def test_48_megapixel_original_is_automatically_downsized(tmp_path, format):
    raw = io.BytesIO()
    Image.new('RGB', (8000, 6000), '#7a91a5').save(raw, format)
    saved = save_photo(tmp_path, raw.getvalue(), '48MP.' + format.lower())
    with Image.open(asset_path(tmp_path, saved['asset_id'])) as image:
        assert image.size == (1920, 1440)
        assert image.format == 'JPEG'
        assert not image.getexif()


def test_downsizing_preserves_exif_orientation(tmp_path):
    raw = io.BytesIO()
    exif = Image.Exif(); exif[274] = 6
    Image.new('RGB', (8000, 6000), '#7a91a5').save(raw, 'JPEG', exif=exif)
    saved = save_photo(tmp_path, raw.getvalue(), 'rotated.jpg')
    with Image.open(asset_path(tmp_path, saved['asset_id'])) as image:
        assert image.size == (1440, 1920)
        assert not image.getexif()
