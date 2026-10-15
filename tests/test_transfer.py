import json
import pytest
from pathlib import Path

from test_daily import daily
from test_studio import client, payload


@pytest.mark.parametrize('music_id', ['little-weekend', 'dream-culture'])
def test_mac_iphone_project_transfer_roundtrip(client, music_id):
    font = (Path(__file__).resolve().parent.parent / 'resources' / 'NotoSansKR.ttf').read_bytes()
    font_id = client.post('/api/fonts?filename=caption.ttf', content=font).json()['asset_id']
    original = daily(client, 1)
    original.update(subtitle_font_id=font_id, subtitle_font_name='caption.ttf',
                    subtitle_x=.62, subtitle_y=.4, music_id=music_id, subtitle_size=76, motion='pan-left', transition='cut', music_offset=7.5, mood='여행', description='산책한 주말', tone='가볍고 유쾌하게')
    created = client.post('/api/projects', json=original)
    assert created.status_code == 200, created.text
    exported = client.get('/api/projects/' + created.json()['id'] + '/transfer')
    assert exported.status_code == 200, exported.text[:300]
    transfer = exported.json()
    assert transfer['format'] == 'content-studio-transfer'
    assert transfer['project']['subtitleX'] == .62
    assert transfer['project']['fontAssetID'].endswith('.ttf')
    restored = client.post('/api/projects/transfer', content=exported.content,
                           headers={'Content-Type': 'application/json'})
    assert restored.status_code == 200, restored.text
    copy = restored.json()
    assert copy['id'] != created.json()['id']
    assert copy['subtitle_x'] == .62
    assert copy['subtitle_font_id'] != font_id
    assert copy['photos'][0]['asset_id'] != original['photos'][0]['asset_id']
    assert copy['music_id'] == music_id
    assert copy['subtitle_size'] == 76
    assert copy['motion'] == 'pan-left' and copy['transition'] == 'cut'
    assert copy['music_offset'] == 7.5 and copy['mood'] == '여행'
    assert copy['description'] == '산책한 주말' and copy['tone'] == '가볍고 유쾌하게'


def test_news_transfer_keeps_sources(client):
    created = client.post('/api/projects', json=payload()).json()
    export = client.get('/api/projects/' + created['id'] + '/transfer')
    imported = client.post('/api/projects/transfer', content=export.content,
                           headers={'Content-Type': 'application/json'})
    assert imported.status_code == 200, imported.text
    assert imported.json()['sources'][0]['text'] == created['sources'][0]['text']
    assert imported.json()['scenes'][0]['source_ids'] == [0]


def test_transfer_rejects_missing_assets(client):
    created = client.post('/api/projects', json=daily(client, 1)).json()
    transfer = client.get('/api/projects/' + created['id'] + '/transfer').json()
    transfer['assets'] = {}
    response = client.post('/api/projects/transfer', content=json.dumps(transfer),
                           headers={'Content-Type': 'application/json'})
    assert response.status_code == 400
