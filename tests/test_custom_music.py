import io
import time
import wave

from studio.custom_music import asset_path
from studio.maintenance import backup, restore
from studio.storage import Store
from test_daily import daily
from test_studio import client


def sound():
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\x00\x00' * 16000)
    return output.getvalue()


def test_custom_music_upload_and_render(client, tmp_path):
    invalid = client.post('/api/custom-music?filename=bad.wav', content=b'not audio')
    assert invalid.status_code == 400
    assert list(client.app.state.store.assets.glob('*.wav')) == []
    uploaded = client.post('/api/custom-music?filename=my-song.wav', content=sound())
    assert uploaded.status_code == 200, uploaded.text
    music = uploaded.json()
    assert music['filename'] == 'my-song.wav'
    assert client.get('/api/custom-music/' + music['asset_id']).content == sound()
    payload = daily(client, 1)
    payload.update(music_id='', music_asset_id=music['asset_id'], music_filename=music['filename'])
    created = client.post('/api/projects', json=payload)
    assert created.status_code == 200, created.text
    project = created.json()
    assert client.post('/api/projects', json={**payload, 'music_id': 'slow-morning'}).status_code == 400
    started = client.post(f'/api/projects/{project["id"]}/render', json={'revision': 1})
    assert started.status_code == 200, started.text
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = client.get('/api/jobs').json()[0]
        if job['status'] != 'RUNNING':
            break
        time.sleep(.1)
    assert job['status'] == 'DONE', job
    done = client.get(f'/api/projects/{project["id"]}').json()
    assert done['render']['music_asset_id'] == music['asset_id']
    assert done['render']['music_id'] == ''
    restored_store = Store(tmp_path / 'restored')
    restore(restored_store, backup(client.app.state.store))
    restored = restored_store.list('projects')[0]
    assert restored['music_asset_id'] != music['asset_id']
    assert asset_path(restored_store.assets, restored['music_asset_id']).is_file()
