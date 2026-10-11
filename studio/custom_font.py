import re
from pathlib import Path

from PIL import ImageFont

from .storage import new_id

EXTENSIONS = {'.ttf': 'font/ttf', '.otf': 'font/otf'}
MAX_BYTES = 20_000_000


def asset_path(assets, asset_id):
    if not re.fullmatch(r'[a-f0-9]{32}', asset_id or ''):
        raise ValueError('폰트 파일 ID가 올바르지 않습니다.')
    for extension in EXTENSIONS:
        path = assets / (asset_id + extension)
        if path.is_file():
            return path
    raise ValueError('첨부한 폰트 파일을 찾을 수 없습니다. 다시 첨부하세요.')


def save_font(assets, data, filename):
    name = Path(filename.replace('\\', '/')).name[:150]
    extension = Path(name).suffix.lower()
    if extension not in EXTENSIONS:
        raise ValueError('TTF 또는 OTF 폰트 파일을 선택하세요.')
    if not data or len(data) > MAX_BYTES:
        raise ValueError('폰트 파일은 20MB 이하여야 합니다.')
    assets.mkdir(parents=True, exist_ok=True)
    asset_id = new_id()
    path = assets / (asset_id + extension)
    try:
        path.write_bytes(data)
        face = ImageFont.truetype(str(path), 48)
        face.getbbox('한글 자막 Sample 123')
        return {'asset_id': asset_id, 'filename': name}
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        raise ValueError('읽을 수 있는 TTF·OTF 폰트가 아닙니다.') from None


def validate_font_asset(project, assets):
    if project.get('subtitle_font_id'):
        asset_path(assets, project['subtitle_font_id'])


def bundled_library(assets):
    """Install the offline presets as ordinary assets so exports/backups remain portable."""
    import json
    import shutil
    root = Path(__file__).resolve().parent.parent / 'resources' / 'fonts'
    entries = json.loads((root / 'catalog.json').read_text(encoding='utf-8'))
    assets.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        target = assets / (entry['id'] + Path(entry['filename']).suffix)
        if not target.exists():
            shutil.copyfile(root / entry['filename'], target)
    return [{**entry, 'asset_id': entry['id']} for entry in entries]
