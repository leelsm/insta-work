import io
import subprocess
import threading

import imageio_ffmpeg
import pytest
from PIL import Image, ImageDraw

from studio.models import ProjectInput
from studio.renderer import crossfade_frames, render
from test_studio import client  # noqa: F401 - pytest fixture

RED, BLUE = '#dc3434', '#3446dc'


def frames(video):
    """Every decoded frame, downscaled, as a list of 54x96 RGB images."""
    raw = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(video),
                          '-vf', 'scale=54:96:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    size = 54 * 96 * 3
    return [Image.frombytes('RGB', (54, 96), raw[i:i+size]) for i in range(0, len(raw), size)]


def make(client, kind, transition, durations, narrations=None, motion='zoom'):
    photos = []
    for color in [RED, BLUE, RED][:len(durations)]:
        image = Image.new('RGB', (1080, 1920), color)
        raw = io.BytesIO(); image.save(raw, 'PNG')
        photos.append(client.post('/api/photos?filename=scene.png', content=raw.getvalue()).json())
    narrations = narrations or [''] * len(durations)
    scenes = [{'title': str(i), 'narration': narrations[i], 'duration': d, 'image_asset_id': p['asset_id']}
              for i, (d, p) in enumerate(zip(durations, photos))]
    project = ProjectInput(**{'title': 'crossfade', 'content_type': kind, 'photos': photos if kind == 'daily' else [],
                              'scenes': scenes, 'motion': motion, 'transition': transition,
                              'music_id': ''}).model_dump()
    project.update(id='test', revision=1)
    return project


def red_share(image):
    r, _, b = image.getpixel((27, 30))
    return r / max(1, r + b)


@pytest.mark.parametrize('kind', ['daily', 'news'])
def test_fade_is_a_true_crossfade_without_black_frames(client, tmp_path, kind):
    project = make(client, kind, 'fade', [2, 2])
    result = render(project, tmp_path / 'r', None, {}, threading.Event(), lambda *a: None, lambda *a: None,
                    client.app.state.store.assets)
    video = frames(tmp_path / 'r' / 'video.mp4')
    # Duration is unchanged: 2 + 2 seconds at 30 fps, no overlap shortening.
    assert result['duration'] == 4 and len(video) == 120
    for image in video:
        # No frame dips toward black: the photo area always stays bright.
        assert sum(image.getpixel((27, 30))) > 200
    shares = [red_share(image) for image in video]
    # Pure red before the dissolve, pure blue after, and a mix at the boundary.
    assert shares[0] > .75 and shares[50] > .75
    assert shares[-1] < .25 and shares[69] < .25
    assert .4 < shares[59] < .65 and .35 < shares[60] < .6
    # Red decreases monotonically through the dissolve window.
    window = shares[52:69]
    assert all(a >= b - .03 for a, b in zip(window, window[1:]))
    assert window[0] - window[-1] > .5


def test_cut_has_no_blend_and_srt_timing_is_unchanged(client, tmp_path):
    project = make(client, 'daily', 'cut', [2, 3], ['첫 장면', '둘째 장면'])
    render(project, tmp_path / 'r', None, {}, threading.Event(), lambda *a: None, lambda *a: None,
           client.app.state.store.assets)
    video = frames(tmp_path / 'r' / 'video.mp4')
    assert len(video) == 150
    assert red_share(video[59]) > .75 and red_share(video[60]) < .25
    faded = make(client, 'daily', 'fade', [2, 3], ['첫 장면', '둘째 장면'])
    render(faded, tmp_path / 'f', None, {}, threading.Event(), lambda *a: None, lambda *a: None,
           client.app.state.store.assets)
    assert (tmp_path / 'f' / 'subtitles.srt').read_text() == (tmp_path / 'r' / 'subtitles.srt').read_text()
    assert '00:00:02,000 --> 00:00:05,000' in (tmp_path / 'f' / 'subtitles.srt').read_text()
    assert len(frames(tmp_path / 'f' / 'video.mp4')) == 150


def test_first_and_last_frames_are_never_faded(client, tmp_path):
    project = make(client, 'daily', 'fade', [2, 2, 2])
    render(project, tmp_path / 'r', None, {}, threading.Event(), lambda *a: None, lambda *a: None,
           client.app.state.store.assets)
    video = frames(tmp_path / 'r' / 'video.mp4')
    assert len(video) == 180
    for image in (video[0], video[-1]):
        assert red_share(image) > .75 and sum(image.getpixel((27, 30))) > 200


def test_crossfade_window_is_limited_by_short_clips():
    assert crossfade_frames(2, 2) == 8
    assert crossfade_frames(.2, 5) == 3
    assert crossfade_frames(.01, 5) == 0
