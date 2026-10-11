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
from PIL import Image, ImageDraw, ImageFont

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


def wrap(text, f, width):
    lines = []
    for paragraph in text.split('\n'):
        current = ''
        for char in paragraph:
            if current and f.getlength(current + char) > width:
                lines.append(current.rstrip())
                current = char.lstrip()
            else:
                current += char
        lines.append(current.rstrip())
    return lines or ['']


def fit(draw, text, box, size, minimum, color, font_path=''):
    x, y, width, height = box
    for candidate in range(size, minimum - 1, -2):
        f = font(candidate, font_path)
        lines = wrap(text, f, width)
        step = math.ceil(candidate * 1.48)
        if step * len(lines) <= height:
            for line in lines:
                draw.text((x, y), line, font=f, fill=color)
                y += step
            return
    raise ValueError('카드 글자가 안전 영역을 넘습니다. 제목·본문을 줄이거나 카드를 나눠 주세요.')


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
            cut = cut if cut > 0 else limit
            result.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if piece:
            result.append(piece)
    return result or ['']


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
        for k, part in enumerate(parts):
            if cancel.is_set():
                raise InterruptedError('렌더링을 취소했습니다.')
            duration = scene['duration'] / len(parts)
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
    clips = []
    for i, scene in enumerate(project['scenes']):
        parts = [item for item in timeline if item[2] == i]
        scene_duration = sum(item[1] for item in parts)
        background = f'background-{i:02}.png'
        card(project, scene, i, subtitle='', assets=assets).save(directory / background)
        offset = 0
        for k, (_, duration, _, text) in enumerate(parts):
            subtitle = f'subtitle-{i:02}-{k:02}.png'
            caption_layer(project, text, assets, .79).save(directory / subtitle)
            name = f'clip-{i:02}-{k:02}.mp4'; clips.append(name)
            render_clip(project, directory, background, subtitle, name, duration,
                        round(scene_duration*30), cancel, process_register, offset,
                        first=k==0, last=k==len(parts)-1)
            offset += round(duration*30)
        progress(40+int((i+1)/len(project['scenes'])*35), '사진 움직임·장면 전환 적용 중')
    (directory / 'clips.txt').write_text(''.join(f"file '{name}'\n" for name in clips), encoding='utf-8')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    args = [ffmpeg, '-y', '-hide_banner', '-f', 'concat', '-safe', '0', '-i', 'clips.txt']
    if project['voice']:
        with wave.open(str(directory / 'voice.wav'), 'wb') as w:
            w.setnchannels(audio_params[0]); w.setsampwidth(audio_params[1]); w.setframerate(audio_params[2])
            for data in audio_chunks:
                w.writeframes(data)
        args += ['-i', 'voice.wav']
    from .daily import MUSIC
    # Older news projects predate music_id; give them a usable soundtrack on
    # their next render. An explicit empty selection still means no music.
    music_id = project.get('music_id', 'slow-morning')
    track = next((item for item in MUSIC if item['id'] == music_id), None)
    from .custom_music import asset_path as music_asset_path, duration as music_duration
    custom_path = music_asset_path(assets, project['music_asset_id']) if project.get('music_asset_id') else None
    music_path = custom_path or (RESOURCES / 'music' / (track['id'] + '.wav') if track else None)
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
    with zipfile.ZipFile(directory / 'cards.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.glob('card-*.png')):
            z.write(path, path.name)
    (directory / 'project.json').write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'duration': round(cursor, 3), 'width': 1080, 'height': 1920, 'fps': 30,
            'layout_version': 3, 'voice': project['voice'], 'music_id': track['id'] if track and not custom_path else '',
            'music_asset_id': project.get('music_asset_id', ''),
            'folder': directory.name, 'revision': project['revision'],
            'sha256': file_hash(directory / 'video.mp4')}


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
    width = max(320, min(930, int(max(face.getlength(line) for line in lines) + 100)))
    height = min(1200, max(125, math.ceil(size * 1.48) * len(lines) + 56))
    x, y = subtitle_box(project, width, height, default_y)
    if project.get('subtitle_style', 'box') == 'box':
        d.rounded_rectangle((x, y, x+width, y+height), radius=24, fill=(8, 9, 13, 190))
    else:
        fit(d, text, (x+28, y+31, width-56, height-56), size, min(size, 24), (0, 0, 0, 210), font_path)
    fit(d, text, (x+25, y+28, width-50, height-56), size, min(size, 24), '#ffffff', font_path)
    return image


def photo_caption(project, scene, assets=None):
    default_y = .76 if project.get('subtitle_position', 'bottom') == 'bottom' else .5
    return caption_layer(project, scene.get('narration', '').strip(), assets, default_y)


def motion_filter(motion, frames, offset=0):
    p = f'min((on+{offset})/{max(1,frames)},1)'
    z = {'zoom': f'1+0.045*{p}', 'zoom-out': f'1+0.045*(1-{p})',
         'pan-left': '1.045', 'pan-right': '1.045'}.get(motion)
    if not z:
        return 'scale=1080:1920'
    x = f'(iw-iw/zoom)*{p}' if motion == 'pan-left' else f'(iw-iw/zoom)*(1-{p})' if motion == 'pan-right' else 'iw/2-iw/zoom/2'
    return f"zoompan=z='{z}':x='{x}':y='ih/2-ih/zoom/2':d=1:s=1080x1920:fps=30"


def render_clip(project, directory, background, subtitle, name, duration, frames, cancel, process_register,
                offset=0, first=True, last=True):
    motion = motion_filter(project.get('motion', 'zoom'), frames, offset)
    fade = ''
    if project.get('transition', 'fade') == 'fade':
        if first:
            fade += ',fade=t=in:st=0:d=0.25'
        if last:
            fade += f',fade=t=out:st={max(0,duration-.25):.6f}:d=0.25'
    filters = f'[0:v]{motion},setsar=1[bg];[bg][1:v]overlay=0:0:shortest=1{fade},format=yuv420p[v]'
    run_ffmpeg(['-loop', '1', '-framerate', '30', '-i', background,
                '-loop', '1', '-framerate', '30', '-i', subtitle,
                '-filter_complex_threads', '1', '-filter_complex', filters, '-map', '[v]',
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
    from .daily import MUSIC, validate_photos
    validate_photos(project, assets)
    directory.mkdir(parents=True, exist_ok=True)
    cursor, srt, clips = 0., [], []
    for i, (photo, scene) in enumerate(zip(project['photos'], project['scenes'])):
        if cancel.is_set():
            raise InterruptedError('렌더링을 취소했습니다.')
        duration = scene['duration']; frames = round(duration * 30)
        background = photo_background(photo, assets)
        subtitle = photo_caption(project, scene, assets)
        background.save(directory / f'background-{i:02}.png')
        subtitle.save(directory / f'subtitle-{i:02}.png')
        preview = background.convert('RGBA'); preview.alpha_composite(subtitle)
        preview.convert('RGB').save(directory / f'card-{i+1:02}.png')
        name = f'clip-{i:02}.mp4'; clips.append(name)
        progress(5+int(i/len(project['photos'])*80), f'사진 {i+1}/{len(project["photos"])} 장면 제작 중')
        render_clip(project, directory, f'background-{i:02}.png', f'subtitle-{i:02}.png',
                    name, duration, frames, cancel, process_register)
        text=scene.get('narration', '').strip()
        if text:
            srt.append(f'{len(srt)+1}\n{timestamp(cursor)} --> {timestamp(cursor+duration)}\n{text}\n')
        cursor += duration
    (directory/'clips.txt').write_text(''.join(f"file '{name}'\n" for name in clips), encoding='utf-8')
    args = ['-f', 'concat', '-safe', '0', '-i', 'clips.txt']
    track = next((t for t in MUSIC if t['id']==project.get('music_id')), None)
    from .custom_music import asset_path as music_asset_path, duration as music_duration
    custom_path = music_asset_path(assets, project['music_asset_id']) if project.get('music_asset_id') else None
    music_path = custom_path or (RESOURCES/'music'/(track['id']+'.wav') if track else None)
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
    with zipfile.ZipFile(directory/'cards.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.glob('card-*.png')):
            z.write(path,path.name)
    (directory/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2),encoding='utf-8')
    if track and not custom_path:
        (directory/'music-license.txt').write_text(f'{track["title"]}\n{track["license"]}\n'+(RESOURCES/'music'/'LICENSE.md').read_text(),encoding='utf-8')
    for pattern in ('background-*.png','subtitle-*.png','clip-*.mp4'):
        for path in directory.glob(pattern):
            path.unlink()
    return {'duration':round(cursor,3),'width':1080,'height':1920,'fps':30,'voice':False,'layout_version':3,
            'folder':directory.name,'revision':project['revision'],'music_id':project.get('music_id','') if not custom_path else '',
            'music_asset_id': project.get('music_asset_id', ''),
            'sha256':file_hash(directory/'video.mp4')}
