import io
import hashlib
import base64
import json
import math
import re
import subprocess
import time
import wave
import zipfile
from functools import lru_cache
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageColor, ImageDraw, ImageFont

from . import emoji
from .adapters import speech

RESOURCES = Path(__file__).resolve().parent.parent / 'resources'


@lru_cache(maxsize=80)
def font(size, custom_path=''):
    candidates = ([Path(custom_path)] if custom_path else []) + [RESOURCES / 'NotoSansKR.ttf', Path('/System/Library/Fonts/AppleSDGothicNeo.ttc'),
                  Path('C:/Windows/Fonts/malgun.ttf')]
    for path in candidates:
        if path.exists():
            f = ImageFont.truetype(str(path), size)
            try:
                f.set_variation_by_axes([700 if size >= 64 else 500])
            except (OSError, AttributeError):
                pass
            return f
    raise ValueError('한글 폰트가 없습니다. resources/NotoSansKR.ttf를 설치하세요.')


# Punctuation that must not start a line; it joins the end of the previous line.
NO_LINE_START = '.,!?)]}"\'」』”’…·:;%。、，！？）'


def text_length(f, text):
    """Width of mixed text; emoji clusters use the color emoji advance."""
    if not emoji.needs_split(text):
        return f.getlength(text)
    return sum(emoji.advance(value, f.size) if is_emoji else f.getlength(value)
               for is_emoji, value in emoji.segments(text))


def draw_text(draw, xy, text, f, fill, shadow=False):
    """Draw one line; emoji clusters are pasted in color (or as a tinted shadow)."""
    if not emoji.needs_split(text):
        draw.text(xy, text, font=f, fill=fill)
        return
    target = draw._image
    x, y = xy
    baseline = y + f.getmetrics()[0]
    for is_emoji, value in emoji.segments(text):
        if not is_emoji:
            draw.text((x, y), value, font=f, fill=fill)
            x += f.getlength(value)
            continue
        rendered = emoji.glyph(value, f.size)
        if rendered is None:
            x += f.size
            continue
        image, advance, image_baseline = rendered
        if shadow:
            alpha = image.getchannel('A')
            color = ImageColor.getrgb(fill) if isinstance(fill, str) else tuple(fill)
            if len(color) == 4:
                alpha = alpha.point(lambda value, opacity=color[3]: value * opacity // 255)
            image = Image.new('RGBA', image.size, color[:3]); image.putalpha(alpha)
        position = (round(x), round(baseline - image_baseline))
        if target.mode == 'RGBA':
            target.alpha_composite(image, (max(0, position[0]), max(0, position[1])),
                                   (max(0, -position[0]), max(0, -position[1])))
        else:
            target.paste(image, position, image)
        x += advance


def _split_long(token, f, width):
    pieces, current = [], ''
    for char in emoji.units(token):
        if current and text_length(f, current + char) > width:
            pieces.append(current)
            current = char
        else:
            current += char
    return pieces + [current]


def wrap(text, f, width):
    lines = []
    for paragraph in text.split('\n'):
        current = ''
        for word in paragraph.split():
            pieces = [word] if text_length(f, word) <= width else _split_long(word, f, width)
            for k, piece in enumerate(pieces):
                candidate = (current + (' ' if current and k == 0 else '') + piece) if current else piece
                if not current or text_length(f, candidate) <= width:
                    current = candidate
                    continue
                # A whole word that starts with a quote ("좋은) is an opening mark, so it
                # stays intact; detached marks and split-word remainders move up.
                if piece[0] in NO_LINE_START and (k > 0 or not piece.strip(NO_LINE_START)):
                    # Keep leading punctuation on the previous line (kinsoku).
                    head = len(piece) - len(piece.lstrip(NO_LINE_START))
                    current += piece[:head]
                    piece = piece[head:]
                    if not piece:
                        continue
                lines.append(current)
                current = piece
        lines.append(current)
    return lines or ['']


def layout(text, box, size, minimum, font_path=''):
    """Pick the largest font that fits the box; returns (font, lines, step)."""
    _, _, width, height = box
    for candidate in range(size, minimum - 1, -2):
        f = font(candidate, font_path)
        lines = wrap(text, f, width)
        step = math.ceil(candidate * 1.48)
        if step * len(lines) <= height:
            return f, lines, step
    raise ValueError('카드 글자가 안전 영역을 넘습니다. 제목·본문을 줄이거나 카드를 나눠 주세요.')


def draw_lines(draw, lines, f, step, x, y, color, shadow=False):
    for line in lines:
        draw_text(draw, (x, y), line, f, color, shadow)
        y += step


def fit(draw, text, box, size, minimum, color, font_path=''):
    f, lines, step = layout(text, box, size, minimum, font_path)
    draw_lines(draw, lines, f, step, box[0], box[1], color)


def card(project, scene, index, subtitle=None, assets=None):
    dark = project['template'] == 'ink'
    im = Image.new('RGB', (1080, 1920), '#171d23' if dark else '#f4f0e6')
    has_image = bool(scene.get('image_asset_id') and assets)
    if has_image:
        from PIL import ImageOps
        from .daily import asset_path
        with Image.open(asset_path(assets, scene['image_asset_id'])) as source:
            im = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'), im.size, Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(im)
    # The background contains artwork only. All editorial copy lives in one subtitle layer.
    if subtitle is None:
        subtitle = scene.get('narration') or scene.get('body') or scene.get('title', '')
    if subtitle:
        im = im.convert('RGBA')
        im.alpha_composite(caption_layer(project, subtitle, assets, .79))
        im = im.convert('RGB')
        d = ImageDraw.Draw(im)
    if has_image and scene.get('image_license') != '직접 제공':
        attribution = f"{(scene.get('image_author') or '작가 미상')[:48]} · {(scene.get('image_license') or '라이선스 확인')[:30]}"
        d.rounded_rectangle((68, 1785, 1012, 1860), radius=14, fill='#080d12')
        fit(d, attribution, (85, 1800, 910, 45), 24, 16, '#ffffff')
    return im


def chunks(text, limit=64):
    # Each speech chunk is timed from its own WAV, avoiding guessed voice timing.
    pieces = re.split(r'(?<=[.!?。])\s+|\n+', text.strip())
    result = []
    for piece in pieces:
        while len(piece) > limit:
            cut = piece.rfind(' ', 15, limit)
            cut = cut if cut > 0 else emoji.safe_cut(piece, limit)
            result.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            result.append(piece)
    return result or ['']


def chunk_durations(parts, total, minimum=0.8):
    """Split a card's duration across subtitle chunks by their length (not count)."""
    if not parts:
        return []
    if total <= minimum * len(parts):
        return [total / len(parts)] * len(parts)
    weights = [max(4, len(re.sub(r'\s', '', part))) for part in parts]
    fixed = set()
    while True:
        free = total - minimum * len(fixed)
        free_weight = sum(w for i, w in enumerate(weights) if i not in fixed)
        result = [minimum if i in fixed else free * w / free_weight for i, w in enumerate(weights)]
        short = {i for i, value in enumerate(result) if i not in fixed and value < minimum}
        if not short:
            break
        fixed |= short
    # Absorb floating-point drift so the chunks add up to the card duration exactly.
    result[-1] += total - sum(result)
    return result


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    h, milliseconds = divmod(milliseconds, 3600000)
    m, milliseconds = divmod(milliseconds, 60000)
    s, ms = divmod(milliseconds, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def render(project, directory, vault, settings, cancel, progress, process_register, assets=None):
    if project.get('content_type') == 'daily':
        return render_daily(project, directory, assets, cancel, progress, process_register)
    directory.mkdir(parents=True, exist_ok=True)
    timeline, audio_chunks, srt, cursor = [], [], [], 0.0
    audio_params = None
    for i, scene in enumerate(project['scenes']):
        if cancel.is_set():
            raise InterruptedError('렌더링을 취소했습니다.')
        card(project, scene, i, assets=assets).save(directory / f'card-{i+1:02}.png')
        parts = chunks(scene['narration'] or scene['body'] or scene['title'])
        planned = chunk_durations(parts, scene['duration'])
        for k, part in enumerate(parts):
            if cancel.is_set():
                raise InterruptedError('렌더링을 취소했습니다.')
            duration = planned[k]
            if project['voice']:
                wav = speech(vault, settings, part)
                with wave.open(io.BytesIO(wav), 'rb') as w:
                    params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                    if audio_params is not None and params != audio_params:
                        raise ValueError('음성 출력 규격이 일치하지 않습니다.')
                    audio_params = params
                    duration = w.getnframes() / w.getframerate()
                    audio_chunks.append(w.readframes(w.getnframes()))
            duration = max(duration, 0.08)
            name = f'frame-{i:02}-{k:02}.png'
            card(project, scene, i, part, assets=assets).save(directory / name)
            timeline.append((name, duration, i, part))
            srt.append(f'{len(srt)+1}\n{timestamp(cursor)} --> {timestamp(cursor+duration)}\n{part}\n')
            cursor += duration
        progress(5 + int((i+1) / len(project['scenes']) * 35), '카드·자막·음성 준비 중')
    if cursor > 180:
        raise ValueError('영상이 180초를 넘습니다. 카드 또는 대본을 줄여 주세요.')
    (directory / 'subtitles.srt').write_text('\n'.join(srt), encoding='utf-8')
    shots = []
    for i, scene in enumerate(project['scenes']):
        parts = [item for item in timeline if item[2] == i]
        scene_frames = round(sum(item[1] for item in parts)*30)
        background = f'background-{i:02}.png'
        card(project, scene, i, subtitle='', assets=assets).save(directory / background)
        offset = 0
        for k, (_, duration, _, text) in enumerate(parts):
            subtitle = f'subtitle-{i:02}-{k:02}.png'
            caption_layer(project, text, assets, .79).save(directory / subtitle)
            shots.append({'name': f'clip-{i:02}-{k:02}.mp4', 'scene': i, 'background': background,
                          'subtitle': subtitle, 'duration': duration, 'frames': scene_frames, 'offset': offset})
            offset += round(duration*30)
    clips = [shot['name'] for shot in shots]
    for j, shot in enumerate(shots):
        render_shot(project, directory, shots, j, cancel, process_register)
        progress(40+int((j+1)/len(shots)*35), '사진 움직임·장면 전환 적용 중')
    (directory / 'clips.txt').write_text(''.join(f"file '{name}'\n" for name in clips), encoding='utf-8')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    args = [ffmpeg, '-y', '-hide_banner', '-f', 'concat', '-safe', '0', '-i', 'clips.txt']
    if project['voice']:
        with wave.open(str(directory / 'voice.wav'), 'wb') as w:
            w.setnchannels(audio_params[0]); w.setsampwidth(audio_params[1]); w.setframerate(audio_params[2])
            for data in audio_chunks:
                w.writeframes(data)
        args += ['-i', 'voice.wav']
    from .music import MUSIC, music_path as bundled_music_path, write_music_notices
    # Older news projects predate music_id; give them a usable soundtrack on
    # their next render. An explicit empty selection still means no music.
    music_id = project.get('music_id', 'slow-morning')
    track = next((item for item in MUSIC if item['id'] == music_id), None)
    from .custom_music import asset_path as music_asset_path, duration as music_duration
    custom_path = music_asset_path(assets, project['music_asset_id']) if project.get('music_asset_id') else None
    music_path = custom_path or bundled_music_path(track)
    has_music = music_path is not None
    if has_music:
        track_duration = music_duration(music_path)
        offset = project.get('music_offset', 0) % track_duration
        args += ['-stream_loop', '-1', '-ss', str(offset), '-i', str(music_path)]
    elif not project['voice']:
        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    music_index = 2 if project['voice'] else 1
    if project['voice'] and has_music:
        volume = project.get('music_volume', .2)
        args += ['-filter_complex', f'[1:a]volume=1[voice];[{music_index}:a]volume={volume},afade=t=in:d=0.6,afade=t=out:st={max(0,cursor-.8):.6f}:d=0.8[music];[voice][music]amix=inputs=2:duration=longest:dropout_transition=2[audio]', '-map', '[audio]']
    elif project['voice']:
        args += ['-map', '1:a:0']
    elif has_music:
        volume = project.get('music_volume', .2)
        args += ['-af', f'volume={volume},afade=t=in:d=0.6,afade=t=out:st={max(0,cursor-.8):.6f}:d=0.8', '-map', '1:a:0']
    else:
        args += ['-map', '1:a:0']
    args += ['-map', '0:v:0', '-t', str(cursor), '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart',
             '-progress', 'progress.txt', 'video.mp4']
    with (directory / 'ffmpeg.log').open('w') as log:
        p = subprocess.Popen(args, cwd=directory, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        process_register(p)
        try:
            while p.poll() is None:
                if cancel.wait(0.2):
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill(); p.wait(timeout=2)
                    raise InterruptedError('렌더링을 취소했습니다.')
                status = directory / 'progress.txt'
                if status.exists():
                    values = dict(re.findall(r'^(\w+)=(.*)$', status.read_text(errors='ignore'), re.M))
                    done = int(values.get('out_time_us', '0')) / 1_000_000
                    progress(min(98, 75 + int(done / cursor * 23)), 'MP4 렌더링 중')
            if p.returncode:
                raise ValueError('FFmpeg 영상 생성에 실패했습니다. 카드 길이·설치 상태를 확인하세요.')
        finally:
            process_register(None)
    thumbnail = write_thumbnail(project, directory, [sum(max(1, round(t[1]*30))/30 for t in timeline if t[2] == i) for i in range(len(project['scenes']))], cancel, process_register)
    with zipfile.ZipFile(directory / 'cards.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.glob('card-*.png')):
            z.write(path, path.name)
    (directory / 'project.json').write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
    write_music_notices(directory, project)
    return {'duration': round(cursor, 3), 'width': 1080, 'height': 1920, 'fps': 30,
            'layout_version': 4, 'music_notices': True, 'voice': project['voice'], 'music_id': track['id'] if track and not custom_path else '',
            'music_asset_id': project.get('music_asset_id', ''),
            'folder': directory.name, 'revision': project['revision'],
            'sha256': file_hash(directory / 'video.mp4'), **thumbnail}


def write_thumbnail(project, directory, durations, cancel, process_register):
    index = project.get('thumbnail_scene', 0)
    if not 0 <= index < len(durations):
        raise ValueError('썸네일로 사용할 장면을 선택하세요.')
    moment = sum(durations[:index]) + durations[index] / 2
    run_ffmpeg(['-ss', str(moment), '-i', 'video.mp4', '-frames:v', '1',
                '-q:v', '2', 'thumbnail.jpg'], directory, cancel, process_register)
    # Add cover art without changing the existing H.264 video/audio tracks.
    run_ffmpeg(['-i', 'video.mp4', '-i', 'thumbnail.jpg', '-map', '0:v:0',
                '-map', '0:a?', '-map', '1:v:0', '-c', 'copy',
                '-disposition:v:1', 'attached_pic', '-movflags', '+faststart',
                'covered-video.mp4'], directory, cancel, process_register)
    (directory / 'covered-video.mp4').replace(directory / 'video.mp4')
    return {'thumbnail': True, 'thumbnail_scene': index, 'thumbnail_time': round(moment, 3)}


def file_hash(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def photo_background(photo, assets):
    from PIL import ImageOps
    from .daily import asset_path
    with Image.open(asset_path(assets, photo['asset_id'])) as source:
        if photo['fit'] == 'cover':
            return ImageOps.fit(source.convert('RGB'), (1080, 1920), Image.Resampling.LANCZOS,
                                centering=(photo['position_x'], photo['position_y']))
        canvas = Image.new('RGB', (1080, 1920), '#14151b')
        image = ImageOps.contain(source.convert('RGB'), (1080, 1920), Image.Resampling.LANCZOS)
        canvas.paste(image, ((1080-image.width)//2, (1920-image.height)//2))
        return canvas


def subtitle_box(project, width, height, default_y):
    center_x = float(project.get('subtitle_x', .5)) * 1080
    saved_y = project.get('subtitle_y')
    center_y = float(saved_y if saved_y is not None else default_y) * 1920
    x = round(max(25, min(1080-width-25, center_x-width/2)))
    y = round(max(75, min(1920-height-100, center_y-height/2)))
    return x, y


def caption_layer(project, text, assets=None, default_y=.76):
    image = Image.new('RGBA', (1080, 1920))
    if not text.strip():
        return image
    d = ImageDraw.Draw(image)
    from .custom_font import asset_path as font_asset_path
    font_path = str(font_asset_path(assets, project['subtitle_font_id'])) if project.get('subtitle_font_id') else ''
    size = int(project.get('subtitle_size', 50))
    face = font(size, font_path)
    lines = wrap(text, face, 830)
    width = max(320, min(930, int(max(text_length(face, line) for line in lines) + 100)))
    height = min(1200, max(125, math.ceil(size * 1.48) * len(lines) + 56))
    x, y = subtitle_box(project, width, height, default_y)
    # One layout drives both the shadow and the text so their line breaks always match.
    f, text_lines, step = layout(text, (x+25, y+28, width-50, height-56), size, min(size, 24), font_path)
    if project.get('subtitle_style', 'box') == 'box':
        d.rounded_rectangle((x, y, x+width, y+height), radius=24, fill=(8, 9, 13, 190))
    else:
        draw_lines(d, text_lines, f, step, x+28, y+31, (0, 0, 0, 210), shadow=True)
    draw_lines(d, text_lines, f, step, x+25, y+28, '#ffffff')
    return image


def photo_caption(project, scene, assets=None):
    default_y = .76 if project.get('subtitle_position', 'bottom') == 'bottom' else .5
    return caption_layer(project, scene.get('narration', '').strip(), assets, default_y)


def motion_filter(motion, frames, offset=0):
    # Progress is clamped so a neighbouring scene shown during a crossfade holds
    # its first pose (before it starts) or its last pose (after it ends).
    p = f'clip((on+{offset})/{max(1,frames)},0,1)'
    z = {'zoom': f'1+0.045*{p}', 'zoom-out': f'1+0.045*(1-{p})',
         'pan-left': '1.045', 'pan-right': '1.045'}.get(motion)
    if not z:
        return 'scale=1080:1920'
    x = f'(iw-iw/zoom)*{p}' if motion == 'pan-left' else f'(iw-iw/zoom)*(1-{p})' if motion == 'pan-right' else 'iw/2-iw/zoom/2'
    return f"zoompan=z='{z}':x='{x}':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps=30"


# Half-length of a crossfade on each side of a scene boundary (matches iPhone).
CROSSFADE_HALF = 0.25


def crossfade_frames(previous, following):
    """Frames blended on each side of a boundary between two clips (0 for none)."""
    return max(0, round(min(CROSSFADE_HALF, previous / 2, following / 2) * 30))


def render_shot(project, directory, shots, j, cancel, process_register):
    """Render one clip, crossfading with the neighbouring scene at scene boundaries.

    The dissolve straddles each boundary: the next scene is blended in over the
    last frames of a scene (0 -> 50%) and the previous scene is blended out over
    the first frames of the next (50% -> 0). No frame is darkened, the clip keeps
    its exact duration, so the total length and subtitle timing are unchanged.
    The very first and last frames of the video are never blended or faded.
    """
    shot, blends = shots[j], []
    if project.get('transition', 'fade') == 'fade':
        before = shots[j-1] if j > 0 and shots[j-1]['scene'] != shot['scene'] else None
        after = shots[j+1] if j+1 < len(shots) and shots[j+1]['scene'] != shot['scene'] else None
        if before and (window := crossfade_frames(before['duration'], shot['duration'])):
            # The previous scene continues past its end, holding its final motion pose.
            blends.append({**before, 'offset': before['offset'] + round(before['duration']*30),
                           'start': 0, 'length': window, 'fade': 'out'})
        if after and (window := crossfade_frames(shot['duration'], after['duration'])):
            blends.append({**after, 'offset': after['offset'] - window,
                           'start': round(shot['duration']*30) - window, 'length': window, 'fade': 'in'})
    render_clip(project, directory, shot['background'], shot['subtitle'], shot['name'], shot['duration'],
                shot['frames'], cancel, process_register, shot['offset'], blends)


def render_clip(project, directory, background, subtitle, name, duration, frames, cancel, process_register,
                offset=0, blends=()):
    motion = project.get('motion', 'zoom')
    inputs = ['-loop', '1', '-framerate', '30', '-i', background,
              '-loop', '1', '-framerate', '30', '-i', subtitle]
    filters = [f'[0:v]{motion_filter(motion, frames, offset)},setsar=1[bg]',
               '[bg][1:v]overlay=0:0:shortest=1[base0]']
    for n, blend in enumerate(blends):
        inputs += ['-loop', '1', '-framerate', '30', '-i', blend['background'],
                   '-loop', '1', '-framerate', '30', '-i', blend['subtitle']]
        a, b = 2 + 2*n, 3 + 2*n
        # The neighbour's full frame is laid over this clip at up to 50% opacity,
        # reaching 50% at the scene boundary, so the photos dissolve directly into
        # each other. Frames are counted exactly; the overlay ends after `length`.
        filters.append(f'[{a}:v]{motion_filter(motion, blend["frames"], blend["offset"])},setsar=1[nbg{n}]')
        filters.append(f'[nbg{n}][{b}:v]overlay=0:0:shortest=1,trim=end_frame={blend["length"]},'
                       f'format=rgba,colorchannelmixer=aa=0.5,fade=t={blend["fade"]}:s=0:n={blend["length"]}:alpha=1,'
                       f'setpts=PTS-STARTPTS+{blend["start"]}/(30*TB)[nb{n}]')
        filters.append(f'[base{n}][nb{n}]overlay=0:0:eof_action=pass[base{n+1}]')
    filters.append(f'[base{len(blends)}]format=yuv420p[v]')
    run_ffmpeg([*inputs, '-filter_complex_threads', '1', '-filter_complex', ';'.join(filters), '-map', '[v]',
                '-t', str(duration), '-r', '30', '-an', '-c:v', 'libx264', '-threads', '2',
                '-preset', 'veryfast', '-crf', '22', name], directory, cancel, process_register)


def run_ffmpeg(args, directory, cancel, process_register, progress=None):
    with (directory / 'ffmpeg.log').open('a') as log:
        p = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-hide_banner', *args],
                             cwd=directory, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        process_register(p)
        try:
            while p.poll() is None:
                if cancel.wait(.15):
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill(); p.wait(timeout=2)
                    raise InterruptedError('렌더링을 취소했습니다.')
                if progress:
                    progress()
            if p.returncode:
                raise ValueError('사진 영상 제작에 실패했습니다. 사진·자막 길이를 확인하세요.')
        finally:
            process_register(None)


def render_daily(project, directory, assets, cancel, progress, process_register):
    from .music import MUSIC, music_path as bundled_music_path, write_music_notices
    from .daily import validate_photos
    validate_photos(project, assets)
    directory.mkdir(parents=True, exist_ok=True)
    cursor, srt, shots = 0., [], []
    count = len(project['photos'])
    for i, (photo, scene) in enumerate(zip(project['photos'], project['scenes'])):
        if cancel.is_set():
            raise InterruptedError('렌더링을 취소했습니다.')
        duration = scene['duration']
        background = photo_background(photo, assets)
        subtitle = photo_caption(project, scene, assets)
        background.save(directory / f'background-{i:02}.png')
        subtitle.save(directory / f'subtitle-{i:02}.png')
        preview = background.convert('RGBA'); preview.alpha_composite(subtitle)
        preview.convert('RGB').save(directory / f'card-{i+1:02}.png')
        # Every image is saved first so a clip can crossfade into the next scene.
        shots.append({'name': f'clip-{i:02}.mp4', 'scene': i, 'background': f'background-{i:02}.png',
                      'subtitle': f'subtitle-{i:02}.png', 'duration': duration,
                      'frames': round(duration * 30), 'offset': 0})
        text=scene.get('narration', '').strip()
        if text:
            srt.append(f'{len(srt)+1}\n{timestamp(cursor)} --> {timestamp(cursor+duration)}\n{text}\n')
        cursor += duration
        progress(5+int((i+1)/count*15), f'사진 {i+1}/{count} 준비 중')
    clips = [shot['name'] for shot in shots]
    for i in range(count):
        progress(20+int(i/count*65), f'사진 {i+1}/{count} 장면 제작 중')
        render_shot(project, directory, shots, i, cancel, process_register)
    (directory/'clips.txt').write_text(''.join(f"file '{name}'\n" for name in clips), encoding='utf-8')
    args = ['-f', 'concat', '-safe', '0', '-i', 'clips.txt']
    track = next((t for t in MUSIC if t['id']==project.get('music_id')), None)
    from .custom_music import asset_path as music_asset_path, duration as music_duration
    custom_path = music_asset_path(assets, project['music_asset_id']) if project.get('music_asset_id') else None
    music_path = custom_path or bundled_music_path(track)
    if music_path:
        track_duration = music_duration(music_path)
        offset = project.get('music_offset', 0) % track_duration
        args += ['-stream_loop', '-1', '-ss', str(offset), '-i', str(music_path)]
    else:
        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    volume=project.get('music_volume', .35) if music_path else 0
    args += ['-map', '0:v:0', '-map', '1:a:0', '-t', str(cursor), '-c:v', 'copy',
             '-af', f'volume={volume},afade=t=in:d=0.6,afade=t=out:st={max(0,cursor-.8):.6f}:d=0.8',
             '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', 'video.mp4']
    progress(90, '음악과 자막 영상 합치는 중')
    run_ffmpeg(args, directory, cancel, process_register)
    (directory/'subtitles.srt').write_text('\n'.join(srt), encoding='utf-8')
    thumbnail = write_thumbnail(project, directory, [round(s['duration']*30)/30 for s in project['scenes']], cancel, process_register)
    with zipfile.ZipFile(directory/'cards.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.glob('card-*.png')):
            z.write(path,path.name)
    (directory/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
    write_music_notices(directory, project)
    for pattern in ('background-*.png','subtitle-*.png','clip-*.mp4'):
        for path in directory.glob(pattern):
            path.unlink()
    return {'duration':round(cursor,3),'width':1080,'height':1920,'fps':30,'voice':False,'layout_version':4,'music_notices':True,
            'folder':directory.name,'revision':project['revision'],'music_id':project.get('music_id','') if not custom_path else '',
            'music_asset_id': project.get('music_asset_id', ''),
            'sha256':file_hash(directory/'video.mp4'), **thumbnail}
