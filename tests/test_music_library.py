import hashlib
import time
import subprocess
import imageio_ffmpeg

import pytest

from studio.music import CATALOG, MUSIC, ROOT, music_path, posting_caption
from studio.models import ProjectInput
from test_daily import daily
from test_studio import client, payload


def test_recommendations_have_playable_source_verified_files(client):
    assert client.get('/api/music').json() == MUSIC
    by_id = {t['id']: t for t in MUSIC}
    for mood, ids in CATALOG['recommendations'].items():
        assert 2 <= len(ids) <= 3 and len(set(ids)) == len(ids)
        for id in ids:
            track = by_id[id]
            assert mood in track['tags']
            assert track['reference_url'].startswith('https://www.youtube.com/watch?v=')
            assert track['source_url'].startswith('https://incompetech.com/')
            assert track['attribution'] and 'Kevin MacLeod' in track['attribution']
    for track in MUSIC:
        assert hashlib.sha256(music_path(track).read_bytes()).hexdigest() == track['sha256']
    response = client.get('/api/music/carefree')
    assert response.status_code == 200 and response.headers['content-type'] == 'audio/mpeg'
    assert response.content == (ROOT / 'carefree.mp3').read_bytes()
    assert client.get('/api/music/not-a-track').status_code == 404
    with pytest.raises(ValueError):
        ProjectInput(**{**payload(), 'music_id': '../../secret'})


def test_caption_keeps_required_credit_once_and_respects_uploaded_music():
    project = {'music_id': 'carefree', 'music_asset_id': '', 'caption': '오늘의 일상 #일상'}
    caption = posting_caption(project)
    assert caption.startswith(project['caption'] + '\n\n')
    assert 'CC BY 4.0' in caption and '반복' in caption
    assert posting_caption({**project, 'caption': caption}) == caption
    assert posting_caption({**project, 'music_asset_id': 'a' * 32}) == project['caption']
    assert posting_caption({**project, 'music_id': ''}) == project['caption']


@pytest.mark.parametrize('kind', ['daily', 'news'])
def test_licensed_mp3_is_in_render_and_exported_caption(client, kind):
    fields = daily(client, 1) if kind == 'daily' else payload()
    fields.update(music_id='dream-culture', mood='감성', caption='오늘의 기록',
                  scenes=[{**fields['scenes'][0], 'duration': 2}])
    response = client.post('/api/projects', json=fields)
    assert response.status_code == 200, response.text
    project = response.json()
    started = client.post(f'/api/projects/{project["id"]}/render', json={'revision': project['revision']})
    assert started.status_code == 200, started.text
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = client.get('/api/jobs').json()[0]
        if job['status'] != 'RUNNING':
            break
        time.sleep(.1)
    assert job['status'] == 'DONE', job
    result = client.get(f'/api/projects/{project["id"]}').json()
    assert result['render']['music_id'] == 'dream-culture'
    root = f'/media/{project["id"]}/{result["render"]["folder"]}/'
    assert client.get(root + 'posting-caption.txt').text == posting_caption(result)
    assert 'Kevin MacLeod' in client.get(root + 'music-license.txt').text
    from studio.custom_music import duration
    video = client.app.state.store.media / project['id'] / result['render']['folder'] / 'video.mp4'
    assert 1.9 <= duration(video) <= 2.2
    probe = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(video)], capture_output=True, text=True)
    assert "Audio: aac" in probe.stderr
