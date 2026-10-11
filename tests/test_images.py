import io

import pytest
from PIL import Image

from test_studio import client
from studio.adapters import RemoteError
from studio.images import search_commons, fetch_image, sync_caption_credits
from studio.renderer import card


class Response:
    is_success = True
    headers = {'content-type': 'application/json'}
    def json(self):
        return {'query': {'pages': [
            {'title': 'File:Stadium.jpg', 'imageinfo': [{'thumburl': 'https://upload.wikimedia.org/thumb/stadium.jpg', 'extmetadata': {
                'LicenseShortName': {'value': 'CC BY 4.0'}, 'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by/4.0/'},
                'Artist': {'value': '<a>Photo Author</a>'}}}]},
            {'title': 'File:Restricted.jpg', 'imageinfo': [{'thumburl': 'https://upload.wikimedia.org/thumb/restricted.jpg', 'extmetadata': {
                'LicenseShortName': {'value': 'CC BY-NC 4.0'}, 'LicenseUrl': {'value': ''}, 'Artist': {'value': 'Author'}}}]},
        ]}}


def test_commons_search_keeps_attributed_commercially_reusable_results(monkeypatch):
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, params):
            assert 'gsrsearch' in params and params['iiprop'] == 'url|extmetadata'
            return Response()
    monkeypatch.setattr('studio.images.httpx.Client', Client)
    results = search_commons('football stadium')
    assert len(results) == 1
    assert results[0]['author'] == 'Photo Author'
    assert results[0]['license'] == 'CC BY 4.0'
    assert results[0]['page_url'].startswith('https://commons.wikimedia.org/wiki/File:')


def test_image_download_rejects_non_commons_hosts():
    with pytest.raises(ValueError, match='Wikimedia Commons'):
        fetch_image('https://example.org/private.jpg')


def test_caption_contains_five_card_image_attributions_and_stays_within_limit():
    scenes = [{'image_asset_id':str(i)*32, 'image_author':f'Author {i}', 'image_license':'CC BY 4.0',
               'image_page_url':f'https://commons.wikimedia.org/wiki/File:Image_{i}.jpg'} for i in range(1,6)]
    result = sync_caption_credits('News summary and article source', scenes)
    assert all(f'Author {i}' in result for i in range(1,6))
    assert len(result) <= 2200
    assert sync_caption_credits(result, scenes) == result


def test_news_card_renders_selected_image_and_credits(tmp_path):
    asset_id = 'a' * 32
    Image.new('RGB', (400, 400), (15, 100, 220)).save(tmp_path / (asset_id + '.jpg'))
    project = {'template':'ink', 'accent':'#b8f569', 'brand':'NEWS', 'logo':'', 'voice':False,
               'scenes':[{'title':'경기 결과와 의미','body':'경기 결과와 핵심 사실을 요약한 카드 본문입니다.',
                           'narration':'이 카드의 자막 대본입니다.', 'source_ids':[0]}]}
    scene = {**project['scenes'][0], 'image_asset_id':asset_id, 'image_author':'Photo Author', 'image_license':'CC BY 4.0'}
    rendered = card(project, scene, 0, assets=tmp_path)
    sample = rendered.getpixel((150, 900))
    assert sample[0] < 30 and 90 <= sample[1] <= 110 and 205 <= sample[2] <= 230
    output = io.BytesIO(); rendered.save(output, format='PNG')
    assert output.tell() > 1000


def test_automatic_images_connect_saved_asset_and_preserve_uploaded_photo(monkeypatch, tmp_path):
    from studio.images import attach_first_results
    candidate = {'title': 'Stadium', 'image_url': 'https://upload.wikimedia.org/stadium.jpg'}
    monkeypatch.setattr('studio.images.search_commons', lambda query, limit: [candidate])
    monkeypatch.setattr('studio.images.select_and_save', lambda root, item: {
        'asset_id': 'a' * 32, 'fit': 'cover', 'image_author': 'Author', 'image_license': 'CC BY 4.0'})
    scenes = [{'title': 'Football', 'image_search_query': 'football stadium'},
              {'title': 'Uploaded', 'image_asset_id': 'b' * 32}]
    attach_first_results(scenes, tmp_path)
    assert scenes[0]['image_asset_id'] == 'a' * 32
    assert scenes[1]['image_asset_id'] == 'b' * 32
    assert 'asset_id' not in scenes[0]


def test_news_background_has_no_editorial_text_and_covers_canvas(tmp_path):
    asset_id = 'a' * 32
    color = (15, 100, 220)
    Image.new('RGB', (600, 300), color).save(tmp_path / (asset_id + '.jpg'))
    scene = {'title': 'Title must not be burned into artwork', 'body': 'Body must not duplicate captions',
             'narration': 'Caption', 'image_asset_id': asset_id, 'image_license': '직접 제공'}
    project = {'template': 'ink', 'scenes': [scene]}
    background = card(project, scene, 0, subtitle='', assets=tmp_path)
    assert background.size == (1080, 1920)
    assert len(background.getcolors(1080 * 1920)) == 1
    assert background.getpixel((0, 0)) == background.getpixel((1079, 1919))
    with_caption = card(project, scene, 0, assets=tmp_path)
    assert with_caption.getpixel((540, 1517)) != background.getpixel((540, 1517))


def test_recommendation_endpoint_attaches_images_and_rejects_stale_revision(client, monkeypatch):
    from test_studio import payload
    def attach(scenes, root, progress=None):
        for scene in scenes:
            scene.update(image_asset_id='a'*32, image_author='Author', image_license='CC BY 4.0',
                         image_page_url='https://commons.wikimedia.org/wiki/File:Stadium.jpg')
        return scenes
    monkeypatch.setattr('studio.images.attach_first_results', attach)
    project = client.post('/api/projects', json=payload()).json()
    path = '/api/projects/' + project['id'] + '/recommend-images'
    result = client.post(path, json={'revision': project['revision']})
    assert result.status_code == 200, result.text
    assert result.json()['scenes'][0]['image_asset_id'] == 'a'*32
    assert 'Author' in result.json()['caption']
    assert result.json()['revision'] == project['revision'] + 1
    assert client.post(path, json={'revision': project['revision']}).status_code == 409
