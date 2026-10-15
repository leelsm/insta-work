import pytest
from PIL import Image

from studio import emoji
from test_studio import client  # noqa: F401 - pytest fixture
from studio.renderer import caption_layer, card, chunks, font, text_length, wrap

needs_color_font = pytest.mark.skipif(not any(path.exists() for path in emoji.FALLBACK_FONTS),
                                      reason='no system color emoji font')

FAMILY, THUMB, FLAG, KEYCAP, HEART = '👨‍👩‍👧', '👍🏽', '🇰🇷', '#️⃣', '❤️'
SCOTLAND = '🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f'


def test_segments_keep_emoji_clusters_whole():
    text = f'가족 {FAMILY}와 {THUMB}{FLAG} {KEYCAP}{HEART}{SCOTLAND}끝'
    runs = emoji.segments(text)
    assert [value for is_emoji, value in runs if is_emoji] == [FAMILY, THUMB, FLAG, KEYCAP, HEART, SCOTLAND]
    assert ''.join(value for is_emoji, value in runs if not is_emoji) == '가족 와  끝'


def test_text_style_and_stray_selectors_stay_in_subtitle_font():
    assert emoji.segments('♥ ★ 1 # ©') == [(False, '♥ ★ 1 # ©')]
    assert emoji.segments('가️나‍다') == [(False, '가나다')]
    assert emoji.segments('☀︎') == [(False, '☀')]
    assert emoji.segments('✅ok') == [(True, '✅'), (False, 'ok')]


def test_safe_cut_and_units_never_split_a_cluster():
    assert emoji.safe_cut(f'ab{FAMILY}', 4) == 2
    assert emoji.units(f'a{THUMB}b') == ['a', THUMB, 'b']
    long = '가' * 63 + FAMILY + '나' * 10
    parts = chunks(long)
    assert ''.join(parts) == long and all(FAMILY in part or '‍' not in part for part in parts)


def colored(image):
    """Pixels that are clearly neither grey/white/black: emoji color, not tofu or text."""
    rgb = image.convert('RGB')
    return sum(1 for r, g, b in rgb.get_flattened_data() if max(r, g, b) - min(r, g, b) > 60)


@needs_color_font
@pytest.mark.parametrize('style', ['box', 'clean'])
def test_caption_draws_color_emoji(style):
    project = {'subtitle_style': style, 'subtitle_size': 60, 'subtitle_x': .5, 'subtitle_y': .5}
    plain = caption_layer(project, '오늘 바다 너무 좋았다')
    with_emoji = caption_layer(project, f'오늘 바다 🌊 너무 좋았다 {THUMB}')
    background = Image.new('RGBA', plain.size, '#808080')
    assert colored(Image.alpha_composite(background, plain)) == 0
    assert colored(Image.alpha_composite(background, with_emoji)) > 1500


@needs_color_font
def test_every_cluster_renders_one_colored_glyph():
    for cluster in (FAMILY, THUMB, FLAG, KEYCAP, HEART, '😀'):
        image, advance, baseline = emoji.glyph(cluster, 50)
        assert 35 <= advance <= 70 and 0 < baseline <= image.height
        assert colored(image) > 100
    if emoji.APPLE.exists():
        # Shaped as a single glyph, not three people side by side.
        assert emoji.glyph(FAMILY, 50)[1] == emoji.glyph('😀', 50)[1]


@needs_color_font
def test_wrapping_measures_emoji_width():
    face = font(50)
    assert text_length(face, '가😀') == pytest.approx(face.getlength('가') + emoji.advance('😀', 50))
    lines = wrap('😀' * 30, face, 400)
    assert len(lines) > 2 and ''.join(lines) == '😀' * 30
    assert all(text_length(face, line) <= 400 for line in lines)


@needs_color_font
def test_news_card_png_has_color_emoji():
    project = {'template': 'paper', 'subtitle_style': 'box', 'subtitle_size': 56}
    image = card(project, {'title': '제목', 'narration': f'오늘의 소식 {FLAG} 정리 🎉'}, 0)
    assert colored(image.crop((0, 1100, 1080, 1800))) > 1000


@needs_color_font
def test_pillow_fallback_without_appkit(monkeypatch):
    def unavailable(*args):
        raise ImportError('AppKit')
    monkeypatch.setattr(emoji, '_appkit', unavailable)
    emoji.glyph.cache_clear()
    try:
        image, advance, _ = emoji.glyph('😀', 48)
        assert advance == pytest.approx(48, abs=2) and colored(image) > 100
        # Without shaping only the base glyph of a sequence is drawn, never tofu.
        assert colored(emoji.glyph(THUMB, 48)[0]) > 100
    finally:
        emoji.glyph.cache_clear()


@needs_color_font
def test_daily_mp4_subtitle_shows_color_emoji(client, tmp_path):
    import threading
    from test_crossfade import make
    from studio.renderer import render
    project = make(client, 'daily', 'cut', [2], [f'바다 🌊 {THUMB} {FLAG}'], motion='still')
    project['subtitle_y'] = .5
    render(project, tmp_path / 'r', None, {}, threading.Event(), lambda *a: None, lambda *a: None,
           client.app.state.store.assets)
    from test_timeline_editing import decode
    frame = decode(tmp_path / 'r' / 'video.mp4', 1)
    # The photo is plain red and the text white on a dark box: blue wave pixels
    # can only come from the color emoji.
    blue = sum(1 for r, g, b in frame.get_flattened_data() if b > r + 60 and b > 120)
    assert blue > 400
