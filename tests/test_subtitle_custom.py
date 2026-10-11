from pathlib import Path

from studio.custom_font import asset_path
from studio.jobs import digest
from studio.maintenance import backup, restore
from studio.renderer import card, photo_caption
from studio.storage import Store
from test_daily import daily
from test_studio import client, payload


def test_font_upload_drag_coordinates_and_backup(client, tmp_path):
    assert client.post('/api/fonts?filename=broken.ttf', content=b'not a font').status_code == 400
    source = Path(__file__).resolve().parent.parent / 'resources' / 'NotoSansKR.ttf'
    uploaded = client.post('/api/fonts?filename=my-caption.ttf', content=source.read_bytes())
    assert uploaded.status_code == 200, uploaded.text
    font = uploaded.json()
    assert client.get('/api/fonts/' + font['asset_id']).status_code == 200
    project_data = daily(client, 1)
    project_data.update(subtitle_font_id=font['asset_id'], subtitle_font_name=font['filename'],
                        subtitle_x=.65, subtitle_y=.25)
    created = client.post('/api/projects', json=project_data)
    assert created.status_code == 200, created.text
    project = created.json()
    top = photo_caption(project, project['scenes'][0], client.app.state.store.assets).getbbox()
    bottom = photo_caption({**project, 'subtitle_y': .75}, project['scenes'][0], client.app.state.store.assets).getbbox()
    assert top and bottom and top[1] < bottom[1]
    news = {**payload(), 'subtitle_font_id': font['asset_id'], 'subtitle_font_name': font['filename'],
            'subtitle_x': .4, 'subtitle_y': .3}
    response = client.post('/api/projects', json=news)
    assert response.status_code == 200, response.text
    saved = response.json()
    image = card(saved, saved['scenes'][0], 0, '드래그 자막', assets=client.app.state.store.assets)
    assert image.size == (1080, 1920)
    target = Store(tmp_path / 'restore')
    restore(target, backup(client.app.state.store))
    restored = next(p for p in target.list('projects') if p['content_type'] == 'daily')
    assert asset_path(target.assets, restored['subtitle_font_id']).is_file()


def test_default_subtitle_options_keep_existing_approval_hash(client):
    created = client.post('/api/projects', json=payload()).json()
    legacy = {k: v for k, v in created.items() if k not in
              ('subtitle_x', 'subtitle_y', 'subtitle_font_id', 'subtitle_font_name', 'music_asset_id', 'music_filename')}
    assert digest(created) == digest(legacy)
    assert digest({**created, 'subtitle_y': .3}) != digest(legacy)


def test_bundled_font_choices_render_and_transfer_offline(client):
    import json
    import hashlib
    from PIL import ImageChops
    response = client.get('/api/fonts/library')
    assert response.status_code == 200
    fonts = response.json()['fonts']
    assert len(fonts) == 9 and len({font['asset_id'] for font in fonts}) == 9
    data = payload()
    outputs = []
    for preset in fonts:
        downloaded = client.get('/api/fonts/' + preset['asset_id'])
        assert downloaded.status_code == 200
        assert hashlib.sha256(downloaded.content).hexdigest().startswith(preset['asset_id'])
        data.update(subtitle_font_id=preset['asset_id'], subtitle_font_name=preset['name'])
        created = client.post('/api/projects', json=data)
        assert created.status_code == 200, created.text
        project = created.json()
        outputs.append(card(project, project['scenes'][0], 0, '오늘의 뉴스와 일상을 영상으로', assets=client.app.state.store.assets))
        exported = client.get('/api/projects/' + project['id'] + '/transfer')
        restored = client.post('/api/projects/transfer', content=exported.content,
                               headers={'Content-Type': 'application/json'})
        assert restored.status_code == 200, restored.text
        assert restored.json()['subtitle_font_name'] == preset['name']
        path = asset_path(client.app.state.store.assets, restored.json()['subtitle_font_id'])
        assert path.read_bytes() == downloaded.content
    assert all(ImageChops.difference(outputs[0], image).getbbox() for image in outputs[1:])
    assert client.get('/api/fonts/library').json()['fonts'] == fonts
