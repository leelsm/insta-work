import json
import re
import zipfile
from pathlib import Path

from .models import ProjectInput, SettingsInput
from .renderer import file_hash
from .storage import new_id, now

FILES = ('video.mp4', 'cards.zip', 'subtitles.srt', 'project.json', 'music-license.txt')


def backup(store):
    directory = store.root / 'exports'; directory.mkdir(exist_ok=True)
    path = directory / (new_id() + '.zip')
    with store.lock:
        snapshot = {'format': 'instagram-content-studio', 'version': 1, 'created_at': now(),
                    'settings': store.settings(), 'accounts': store.list('accounts'),
                    'projects': store.list('projects'), 'publications': store.list('publications')}
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('backup.json', json.dumps(snapshot, ensure_ascii=False))
        asset_ids = {photo['asset_id'] for p in snapshot['projects'] for photo in p.get('photos', [])}
        from .daily import asset_path
        for asset_id in asset_ids:
            z.write(asset_path(store.assets, asset_id), f'assets/{asset_id}.jpg')
        from .custom_music import asset_path as music_asset_path
        for asset_id in {p.get('music_asset_id') for p in snapshot['projects']} - {None, ''}:
            source = music_asset_path(store.assets, asset_id)
            z.write(source, f'assets/{source.name}')
        from .custom_font import asset_path as font_asset_path
        for asset_id in {p.get('subtitle_font_id') for p in snapshot['projects']} - {None, ''}:
            source = font_asset_path(store.assets, asset_id)
            z.write(source, f'assets/{source.name}')
        for p in snapshot['projects']:
            if p.get('render'):
                folder = store.media / p['id'] / p['render']['folder']
                for filename in FILES:
                    source = folder / filename
                    if source.is_file():
                        z.write(source, f'media/{p["id"]}/{filename}')
    return path


def restore(store, archive):
    try:
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist()) > 500_000_000 or len(z.infolist()) > 5000:
                raise ValueError('백업 압축 해제 크기 또는 파일 수 한도를 넘습니다.')
            if z.getinfo('backup.json').file_size > 10_000_000:
                raise ValueError('백업 메타데이터가 너무 큽니다.')
            data = json.loads(z.read('backup.json'))
            if data.get('format') != 'instagram-content-studio' or data.get('version') != 1:
                raise ValueError('지원하지 않는 백업 형식입니다.')
            if len(data.get('projects', [])) > 500 or len(data.get('accounts', [])) > 100:
                raise ValueError('복원 항목 수 한도를 넘습니다.')
            # Validate before changing storage. Never extract arbitrary archive paths.
            validated = [(p, ProjectInput.model_validate(p).model_dump()) for p in data.get('projects', [])]
            settings = SettingsInput.model_validate({**data.get('settings', {}), 'secrets': {}}).model_dump(exclude={'secrets'})
            for raw, _ in validated:
                if not re.fullmatch(r'[a-f0-9]{32}', raw['id']):
                    raise ValueError('백업 콘텐츠 ID 형식이 잘못되었습니다.')
            account_map = {}
            planned_accounts = []
            for a in data.get('accounts', []):
                if not re.fullmatch(r'\d{1,30}', str(a.get('user_id', ''))) or not a.get('id'):
                    raise ValueError('백업 계정 형식이 잘못되었습니다.')
                existing = next((v for v in store.list('accounts') + planned_accounts if v['user_id'] == a['user_id']), None)
                if existing:
                    account_map[a['id']] = existing['id']
                else:
                    new = {'id': new_id(), 'name': str(a.get('name', '복원 계정'))[:60], 'user_id': a['user_id'],
                           'username': '', 'status': 'UNVERIFIED', 'created_at': now()}
                    planned_accounts.append(new); account_map[a['id']] = new['id']
            published = {p['project_id'] for p in data.get('publications', []) if p.get('status') == 'PUBLISHED'}
            from .daily import save_photo
            from .custom_music import EXTENSIONS, save_music
            from .custom_font import EXTENSIONS as FONT_EXTENSIONS, save_font
            photo_map = {}
            for raw, fields in validated:
                for photo in fields.get('photos', []):
                    old_id = photo['asset_id']
                    if old_id not in photo_map:
                        name = f'assets/{old_id}.jpg'
                        if name not in z.namelist() or z.getinfo(name).file_size > 20_000_000:
                            raise ValueError('백업의 원본 사진이 없거나 크기 한도를 넘습니다.')
                        photo_map[old_id] = save_photo(store.assets, z.read(name), photo['filename'])['asset_id']
                    photo['asset_id'] = photo_map[old_id]
            music_map = {}
            for raw, fields in validated:
                old_id = fields.get('music_asset_id')
                if old_id and old_id not in music_map:
                    candidates = [f'assets/{old_id}{ext}' for ext in EXTENSIONS if f'assets/{old_id}{ext}' in z.namelist()]
                    if len(candidates) != 1 or z.getinfo(candidates[0]).file_size > 25_000_000:
                        raise ValueError('백업의 첨부 음악이 없거나 크기 한도를 넘습니다.')
                    music_map[old_id] = save_music(store.assets, z.read(candidates[0]),
                                                   fields.get('music_filename') or Path(candidates[0]).name)['asset_id']
                if old_id:
                    fields['music_asset_id'] = music_map[old_id]
            font_map = {}
            for raw, fields in validated:
                old_id = fields.get('subtitle_font_id')
                if old_id and old_id not in font_map:
                    candidates = [f'assets/{old_id}{ext}' for ext in FONT_EXTENSIONS if f'assets/{old_id}{ext}' in z.namelist()]
                    if len(candidates) != 1 or z.getinfo(candidates[0]).file_size > 20_000_000:
                        raise ValueError('백업의 첨부 폰트가 없거나 크기 한도를 넘습니다.')
                    font_map[old_id] = save_font(store.assets, z.read(candidates[0]),
                                                 fields.get('subtitle_font_name') or Path(candidates[0]).name)['asset_id']
                if old_id:
                    fields['subtitle_font_id'] = font_map[old_id]
            restored = []
            planned_projects = []
            for raw, fields in validated:
                pid, folder = new_id(), new_id()
                p = {**fields, 'id': pid, 'account_id': account_map.get(fields['account_id'], ''), 'revision': 1,
                     'approved_hash': '', 'render': None, 'state': 'EDITABLE', 'created_at': now(), 'updated_at': now(),
                     'published_before_backup': raw['id'] in published or raw.get('state') == 'PUBLISHED',
                     'restored_from': raw['id']}
                prefix = f'media/{raw["id"]}/'
                if prefix + 'video.mp4' in z.namelist() and raw.get('render'):
                    destination = store.media / pid / folder; destination.mkdir(parents=True)
                    for name in FILES:
                        if prefix + name in z.namelist():
                            with z.open(prefix + name) as src, (destination / name).open('wb') as out:
                                while chunk := src.read(1024 * 1024):
                                    out.write(chunk)
                    expected = raw['render'].get('sha256')
                    if expected and file_hash(destination / 'video.mp4') == expected:
                        p['render'] = {**raw['render'], 'folder': folder, 'revision': 1}
                        p['state'] = 'REVIEW_READY'
                planned_projects.append(p); restored.append(pid)
            with store.connect() as c:
                for a in planned_accounts:
                    c.execute('INSERT INTO accounts VALUES(?,?)', (a['id'], json.dumps(a, ensure_ascii=False)))
                for p in planned_projects:
                    c.execute('INSERT INTO projects VALUES(?,?)', (p['id'], json.dumps(p, ensure_ascii=False)))
                c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (json.dumps({**store.settings(), **settings}, ensure_ascii=False),))
            return {'restored': len(restored), 'projects': restored,
                    'message': '기존 자료를 보존하고 새 콘텐츠로 복원했습니다. 계정 키는 다시 연결하고, 과거 게시 여부를 확인하세요.'}
    except (zipfile.BadZipFile, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('백업 파일을 읽을 수 없습니다.') from None
