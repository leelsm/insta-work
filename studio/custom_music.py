import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

from .storage import new_id

EXTENSIONS = {'.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.wav': 'audio/wav'}
MAX_BYTES = 25_000_000


def asset_path(assets, asset_id):
    if not re.fullmatch(r'[a-f0-9]{32}', asset_id or ''):
        raise ValueError('음악 파일 ID가 올바르지 않습니다.')
    for extension in EXTENSIONS:
        path = assets / (asset_id + extension)
        if path.is_file():
            return path
    raise ValueError('첨부한 음악 파일을 찾을 수 없습니다. 다시 첨부하세요.')


def duration(path):
    try:
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-i', str(path)],
                                capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('음악 파일을 읽을 수 없습니다.') from None
    match = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', result.stderr)
    if not match:
        raise ValueError('음악 재생 시간을 확인할 수 없습니다. 다른 파일을 선택하세요.')
    seconds = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    if not 0.5 <= seconds <= 3600:
        raise ValueError('음악은 1초 이상, 60분 이하 파일을 선택하세요.')
    return seconds


def save_music(assets, data, filename):
    name = Path(filename).name[:150]
    extension = Path(name).suffix.lower()
    if extension not in EXTENSIONS:
        raise ValueError('MP3, M4A, WAV 음악 파일을 선택하세요.')
    if not data:
        raise ValueError('빈 파일입니다. 다른 파일을 선택하세요.')
    if len(data) > MAX_BYTES:
        raise ValueError('음악 파일은 25MB 이하여야 합니다.')
    assets.mkdir(parents=True, exist_ok=True)
    asset_id = new_id()
    path = assets / (asset_id + extension)
    try:
        path.write_bytes(data)
        probe = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(path),
                                '-map', '0:a:0', '-t', '1', '-f', 'null', '-'],
                               capture_output=True, timeout=15, stdin=subprocess.DEVNULL)
        if probe.returncode:
            raise ValueError('재생할 수 있는 음악 파일이 아닙니다. 다른 파일을 선택하세요.')
        seconds = duration(path)
        return {'asset_id': asset_id, 'filename': name, 'duration': round(seconds, 2)}
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('음악 파일을 읽을 수 없습니다.') from None
    finally:
        if 'seconds' not in locals():
            path.unlink(missing_ok=True)


def validate_music_asset(project, assets):
    asset_id = project.get('music_asset_id', '')
    if asset_id:
        if project.get('music_id'):
            raise ValueError('앱 음악과 첨부 음악 중 하나만 선택하세요.')
        asset_path(assets, asset_id)
