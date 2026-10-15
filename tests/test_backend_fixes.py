import io
import json
import re
import socket
import threading

import pytest
from PIL import Image

import studio.renderer as renderer
from studio.daily import asset_path, save_photo
from studio.launcher import DEFAULT_PORT, bind_port
from studio.renderer import caption_layer, chunk_durations, chunks, font, render, wrap
from test_daily import daily
from test_studio import MemoryVault, client, payload

LONG = '오랜만에 바닷가 마을을 천천히 걸으며 골목마다 들러 보니 다시 오고 싶다는 생각이 들었다. 내일도 "좋은 하루"!'


def test_clean_subtitle_shadow_and_text_share_one_layout(monkeypatch):
    calls = []
    original = renderer.draw_lines
    monkeypatch.setattr(renderer, 'draw_lines',
                        lambda d, lines, f, step, x, y, color, **kw: (calls.append((list(lines), f.size, x, y)),
                                                                      original(d, lines, f, step, x, y, color, **kw)))
    project = {'subtitle_style': 'clean', 'subtitle_size': 72}
    assert caption_layer(project, LONG).getbbox()
    shadow, text = calls
    assert len(shadow[0]) == len(text[0]) > 1
    assert shadow[0] == text[0] and shadow[1] == text[1]
    assert (shadow[2] - text[2], shadow[3] - text[3]) == (3, 3)


def test_clean_subtitle_preview_endpoint(client):
    data = {**daily(client, 1), 'subtitle_style': 'clean', 'subtitle_size': 72}
    data['scenes'][0]['narration'] = LONG
    created = client.post('/api/projects', json=data)
    assert created.status_code == 200, created.text
    assert client.get('/api/projects/' + created.json()['id'] + '/preview/0').status_code == 200


def test_wrap_keeps_words_and_punctuation_together():
    face = font(72)
    lines = wrap(LONG, face, 600)
    assert len(lines) > 2
    words = LONG.split()
    # Every line boundary falls between words; no word is cut in half.
    assert ' '.join(lines).split() == words
    for line in lines:
        # Straight quotes may open a word ("좋은); every other mark must not start a line.
        assert line and (line[0] not in renderer.NO_LINE_START or line[0] in '"\'' and len(line) > 1)
        assert line == line.strip()
    assert any(line.endswith('들었다.') for line in lines) or '들었다.' in ' '.join(lines)


def test_wrap_breaks_only_overlong_tokens_and_keeps_leading_punctuation():
    face = font(50)
    token = '가' * 60
    lines = wrap(token, face, 400)
    assert ''.join(lines) == token and len(lines) > 1
    assert all(face.getlength(line) <= 400 for line in lines)
    # A detached closing mark joins the end of the previous line instead of starting a new one.
    width = face.getlength('가나다라마바')
    lines = wrap('가나다라마바 .', face, width)
    assert lines == ['가나다라마바.']
    assert wrap('첫 줄\n\n셋째', face, 400) == ['첫 줄', '', '셋째']


def test_card_chunk_durations_follow_text_length():
    parts = ['가' * 56 + '.', '나' * 8 + '.', '다' * 19 + '.', '라' * 9]
    durations = chunk_durations(parts, 6)
    assert sum(durations) == pytest.approx(6)
    assert durations[0] > 2 * durations[1]
    assert min(durations) >= .8 - 1e-9
    assert chunk_durations(['짧음', '아주 긴 문장입니다'] * 3, 2) == pytest.approx([2 / 6] * 6)


def test_card_render_srt_uses_weighted_timing(tmp_path):
    narration = ('바닷가 마을의 아침은 생각보다 조용했고 골목마다 오래된 가게들이 하나둘 문을 열며 하루를 시작하고 있었다. '
                 '바람이 좋았다. 다음 주에도 다시 오고 싶다. 고마워요.')
    p = {**payload(), 'template': 'ink', 'accent': '#b8f569', 'brand': 'TEST', 'voice': False, 'revision': 1}
    p['scenes'][0].update(narration=narration, duration=6)
    parts = chunks(narration)
    assert len(parts) == 4
    result = render(p, tmp_path, MemoryVault(), {}, threading.Event(), lambda *_: None, lambda *_: None)
    assert result['duration'] == pytest.approx(6)
    srt = (tmp_path / 'subtitles.srt').read_text()
    stamps = re.findall(r'(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})', srt)
    seconds = lambda h, m, s, ms: int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    spans = [seconds(*row[4:]) - seconds(*row[:4]) for row in stamps]
    expected = chunk_durations(parts, 6)
    assert spans == pytest.approx(expected, abs=.002)
    assert spans[0] > 2 * spans[1]


def transfer_of(client, data):
    created = client.post('/api/projects', json=data)
    assert created.status_code == 200, created.text
    return client.get('/api/projects/' + created.json()['id'] + '/transfer').json()


def post_transfer(client, transfer):
    return client.post('/api/projects/transfer', content=json.dumps(transfer, ensure_ascii=False).encode(),
                       headers={'Content-Type': 'application/json'})


@pytest.mark.parametrize('mutate', [
    lambda t: t['project'].__setitem__('scenes', 'abc'),
    lambda t: t['project'].__setitem__('scenes', ['abc']),
    lambda t: t['project'].__setitem__('sources', 'abc'),
    lambda t: t.__setitem__('project', []),
    lambda t: t['project']['scenes'][0].__setitem__('duration', 'long'),
    lambda t: t['project']['scenes'][0].__setitem__('narration', 7),
    lambda t: t['project']['sources'].__setitem__(0, {'title': '제목만'}),
])
def test_broken_transfer_is_korean_400(client, mutate):
    transfer = transfer_of(client, payload())
    mutate(transfer)
    response = post_transfer(client, transfer)
    assert response.status_code == 400, response.text
    detail = response.json()['detail']
    assert '프로젝트 파일' in detail
    assert 'validation' not in detail.lower() and 'Field required' not in detail


def test_transfer_validation_error_names_field_in_korean(client):
    transfer = transfer_of(client, payload())
    transfer['project']['sources'][0]['text'] = ''
    response = post_transfer(client, transfer)
    assert response.status_code == 400
    assert response.json()['detail'] == '지원하지 않거나 손상된 프로젝트 파일입니다. (출처 1 내용 확인)'


def test_transfer_normalizes_iphone_drafts(client):
    transfer = transfer_of(client, daily(client, 1))
    project = transfer['project']
    project['title'] = ''
    project['caption'] = '가' * 2300
    scene = project['scenes'][0]
    del scene['title']
    scene['narration'] = '나' * 900
    scene['duration'] = 100
    response = post_transfer(client, transfer)
    assert response.status_code == 200, response.text
    copy = response.json()
    assert copy['title'] == '가져온 일상 영상'
    assert len(copy['caption']) == 2200
    assert copy['scenes'][0]['title'] == '장면 1'
    assert len(copy['scenes'][0]['narration']) == 700
    assert copy['scenes'][0]['duration'] == 30

    news = transfer_of(client, payload())
    news['project']['title'] = '제' * 151
    news['project']['scenes'][0]['title'] = '목' * 120
    news['project']['scenes'][0]['duration'] = 0.5
    response = post_transfer(client, news)
    assert response.status_code == 200, response.text
    assert len(response.json()['title']) == 150
    assert len(response.json()['scenes'][0]['title']) == 90
    assert response.json()['scenes'][0]['duration'] == 2
    news['project']['title'] = '   '
    assert post_transfer(client, news).json()['title'] == '가져온 카드 영상'


def test_transfer_keeps_subtitle_position_and_photo_filename(client):
    photo = client.post('/api/photos?filename=portrait.jpg', content=io_png()).json()
    data = {**daily(client, 1), 'photos': [photo], 'subtitle_position': 'center'}
    transfer = transfer_of(client, data)
    assert transfer['project']['subtitlePosition'] == 'center'
    assert transfer['project']['scenes'][0]['photoFilename'] == 'portrait.jpg'
    copy = post_transfer(client, transfer).json()
    assert copy['subtitle_position'] == 'center'
    assert copy['photos'][0]['filename'] == 'portrait.jpg'
    # Files without the new keys (older Mac/iPhone exports) still import.
    del transfer['project']['subtitlePosition']
    del transfer['project']['scenes'][0]['photoFilename']
    transfer['project']['subtitleY'] = .52
    copy = post_transfer(client, transfer).json()
    assert copy['subtitle_position'] == 'center'
    assert copy['photos'][0]['filename'] == transfer['project']['scenes'][0]['title']
    transfer['project']['subtitleY'] = .76
    assert post_transfer(client, transfer).json()['subtitle_position'] == 'bottom'


def io_png(mode='RGB', color='#7a91a5'):
    buf = io.BytesIO()
    Image.new(mode, (64, 64), color).save(buf, 'PNG')
    return buf.getvalue()


def test_model_validation_message_is_specific(client):
    data = daily(client, 10)
    for scene in data['scenes']:
        scene['duration'] = 18
    data['scenes'][-1]['duration'] = 18.01
    response = client.post('/api/projects', json=data)
    assert response.status_code == 422
    assert response.json()['detail'] == '일상 영상은 180초 이하여야 합니다.'
    data = daily(client, 2)
    data['scenes'] = data['scenes'][:1]
    response = client.post('/api/projects', json=data)
    assert response.json()['detail'] == '일상 영상은 사진 1~10장과 같은 수의 장면이 필요합니다.'
    # Field-level errors keep the generic text and never echo input.
    response = client.post('/api/projects', json={**payload(), 'title': 'x' * 151})
    assert response.status_code == 422
    assert response.json()['detail'] == '입력값의 길이·형식 또는 출처 번호를 확인하세요.'
    assert 'x' * 151 not in response.text


@pytest.mark.parametrize('mode', ['RGBA', 'LA', 'P'])
def test_transparent_png_is_flattened_on_white(tmp_path, mode):
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    image.paste((200, 0, 0, 255), (0, 0, 32, 64))
    if mode == 'LA':
        image = image.convert('LA')
    elif mode == 'P':
        image = image.convert('P')
        image.info['transparency'] = image.getpixel((63, 0))
    buf = io.BytesIO()
    image.save(buf, 'PNG', **({'transparency': image.info['transparency']} if mode == 'P' else {}))
    saved = save_photo(tmp_path, buf.getvalue(), 'clear.png')
    with Image.open(asset_path(tmp_path, saved['asset_id'])) as result:
        assert min(result.getpixel((60, 32))) > 240


def test_empty_uploads_get_empty_file_message(client):
    for path in ('/api/photos?filename=x.png', '/api/custom-music?filename=x.mp3'):
        response = client.post(path, content=b'')
        assert response.status_code == 400
        assert response.json()['detail'] == '빈 파일입니다. 다른 파일을 선택하세요.'


def test_launcher_defaults_to_8080_and_skips_busy_ports():
    assert DEFAULT_PORT == 8080
    blocker = socket.socket()
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    try:
        sock, message = bind_port(busy)
        assert sock is None and str(busy) in message
        sock, port = bind_port(busy, 20)
        assert sock is not None and busy < port <= busy + 20
        sock.close()
    finally:
        blocker.close()
    assert bind_port(0)[0] is None and bind_port(70000, 20)[0] is None


def test_launcher_browser_mode_starts_on_8080_without_saved_port(tmp_path):
    import os, subprocess, sys, time
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, 'STUDIO_DATA_DIR': str(tmp_path / 'app')}
    p = subprocess.Popen([sys.executable, str(root / 'run.py'), '--browser', '--no-open'], cwd=root, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 20
        line = ''
        while time.time() < deadline:
            line = p.stdout.readline()
            if '실행 주소' in line or not line:
                break
        found = re.search(r'http://127\.0\.0\.1:(\d+)', line)
        # 8080, or one of the next ports when another local app already uses it.
        assert found and DEFAULT_PORT <= int(found[1]) <= DEFAULT_PORT + 20, line
    finally:
        p.terminate()
        p.wait(10)
