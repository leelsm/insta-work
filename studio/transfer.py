"""A self-contained JSON project exchange format for the Mac and iPhone apps."""
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .models import ProjectInput
from .storage import new_id, now

FORMAT = 'content-studio-transfer'
MAX_BYTES = 250_000_000


def _date(value):
    try:
        return (datetime.fromisoformat(value.replace('Z', '+00:00')) - datetime(2001, 1, 1, tzinfo=timezone.utc)).total_seconds()
    except (AttributeError, ValueError):
        return 0


CORRUPT = '지원하지 않거나 손상된 프로젝트 파일입니다.'
FIELD_NAMES = {'title': '제목', 'scenes': '장면', 'caption': '게시 문안', 'body': '본문', 'narration': '자막',
               'duration': '길이', 'sources': '출처', 'text': '내용', 'url': '주소', 'rights': '이용 조건',
               'photos': '사진', 'filename': '파일 이름', 'fit': '사진 맞춤', 'position_x': '사진 가로 위치',
               'position_y': '사진 세로 위치', 'source_ids': '출처 번호', 'template': '템플릿', 'brand': '브랜드',
               'subtitle_x': '자막 가로 위치', 'subtitle_y': '자막 세로 위치', 'subtitle_style': '자막 스타일',
               'subtitle_position': '자막 위치', 'subtitle_size': '자막 크기', 'subtitle_font_name': '글꼴 이름',
               'motion': '사진 움직임', 'transition': '장면 전환', 'music_id': '음악', 'music_filename': '음악 이름',
               'music_volume': '음악 볼륨', 'music_offset': '음악 시작 위치', 'mood': '분위기',
               'description': '설명', 'tone': '말투', 'thumbnail_scene': '썸네일 장면',
               'image_search_query': '이미지 검색어', 'image_author': '이미지 작가',
               'image_license': '이미지 라이선스', 'image_page_url': '이미지 주소',
               'image_license_url': '라이선스 주소'}


def _field_label(loc):
    parts = []
    for part in loc:
        if isinstance(part, int):
            parts.append(str(part + 1))
        else:
            parts.append(FIELD_NAMES.get(part, '항목'))
    return ' '.join(parts)


def _validation_message(error):
    first = error.errors()[0] if error.errors() else {}
    loc = first.get('loc') or ()
    if loc:
        return f'{CORRUPT} ({_field_label(loc)} 확인)'
    detail = (first.get('ctx') or {}).get('error')
    # Model-level checks (e.g. 180초 제한) already carry a Korean message.
    return f'{CORRUPT} ({detail})' if first.get('type') == 'value_error' and detail else CORRUPT


def _text(value, limit=None):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise TypeError()
    return value[:limit] if limit else value


def _number(value, default, low, high):
    if value is None or isinstance(value, bool):
        return default
    if not isinstance(value, (int, float)):
        raise TypeError()
    return min(high, max(low, float(value)))


def export_project(store, project):
    from .daily import asset_path as photo_path
    from .custom_music import asset_path as music_path
    from .custom_font import asset_path as font_path
    assets = {}

    def include(path):
        assets[path.name] = base64.b64encode(path.read_bytes()).decode('ascii')
        return path.name

    photos = project.get('photos', [])
    scenes = []
    for index, item in enumerate(project['scenes']):
        if project.get('content_type') == 'daily':
            photo = photos[index]
            image_id = photo.get('asset_id')
            fit = photo.get('fit', 'cover')
            position_x = photo.get('position_x', .5)
            position_y = photo.get('position_y', .5)
        else:
            image_id = item.get('image_asset_id')
            fit, position_x, position_y = 'cover', .5, .5
        scene = {'id': new_id(), 'title': item['title'], 'body': item.get('body', ''),
                       'narration': item.get('narration', ''), 'duration': item.get('duration', 4),
                       'photoID': include(photo_path(store.assets, image_id)) if image_id else '',
                       'sourceIDs': item.get('source_ids', []), 'photoFit': fit,
                       'positionX': position_x, 'positionY': position_y,
                       'imageSearchQuery': item.get('image_search_query', ''),
                       'imageAuthor': item.get('image_author', ''), 'imageLicense': item.get('image_license', ''),
                       'imagePageURL': item.get('image_page_url', ''), 'imageLicenseURL': item.get('image_license_url', ''),
                       'imageCredit': (f"{item.get('image_author', '')[:48]} · {item.get('image_license', '')[:30]}"
                                       if item.get('image_page_url') else '')}
        if project.get('content_type') == 'daily' and photos[index].get('filename'):
            scene['photoFilename'] = photos[index]['filename']
        scenes.append(scene)
    music_id = project.get('music_asset_id', '')
    font_id = project.get('subtitle_font_id', '')
    target = {
        'id': project['id'], 'title': project['title'],
        'kind': 'daily' if project.get('content_type') == 'daily' else 'news',
        'scenes': scenes,
        'thumbnailSceneID': scenes[project.get('thumbnail_scene', 0)]['id'],
        'sources': [{'title': s.get('title', ''), 'text': s.get('text', ''), 'url': s.get('url', ''),
                     'rights': s.get('rights', '')} for s in project.get('sources', [])],
        'caption': project.get('caption', ''), 'template': project.get('template', 'ink'),
        'brand': project.get('brand', 'STUDIO'),
        'subtitleX': project.get('subtitle_x', .5),
        'subtitleY': project.get('subtitle_y') if project.get('subtitle_y') is not None else
                     (.76 if project.get('content_type') == 'daily' and project.get('subtitle_position') != 'center'
                      else .5 if project.get('content_type') == 'daily' else .79),
        'subtitleStyle': project.get('subtitle_style', 'box'),
        'subtitlePosition': project.get('subtitle_position', 'bottom'),
        'subtitleSize': project.get('subtitle_size', 50),
        'motion': project.get('motion', 'zoom'), 'transition': project.get('transition', 'fade'),
        'fontAssetID': include(font_path(store.assets, font_id)) if font_id else '',
        'fontName': project.get('subtitle_font_name', ''),
        'musicID': project.get('music_id', ''),
        'musicAssetID': include(music_path(store.assets, music_id)) if music_id else '',
        'musicName': project.get('music_filename', ''),
        'musicVolume': project.get('music_volume', .35),
        'musicOffset': project.get('music_offset', 0),
        'mood': project.get('mood', '일상'), 'description': project.get('description', ''),
        'tone': project.get('tone', '담백하고 자연스럽게'),
        'createdAt': _date(project.get('created_at')),
        'updatedAt': _date(project.get('updated_at')),
        'lastVideo': ''}
    return {'format': FORMAT, 'version': 1, 'project': target, 'assets': assets}


def import_project(store, data):
    if len(data) > MAX_BYTES:
        raise ValueError('프로젝트 파일은 250MB 이하여야 합니다.')
    try:
        transfer = json.loads(data)
        if transfer['format'] != FORMAT or transfer['version'] != 1:
            raise ValueError()
        raw, assets = transfer['project'], transfer['assets']
        if not isinstance(assets, dict) or len(assets) > 30:
            raise ValueError()
        if not isinstance(raw, dict):
            raise ValueError()
        kind = raw['kind']
        if kind not in ('daily', 'news') or not isinstance(raw['scenes'], list) or len(raw['scenes']) > 12:
            raise ValueError()
        if not all(isinstance(scene, dict) for scene in raw['scenes']):
            raise ValueError()
        raw_sources = raw.get('sources') or []
        if not isinstance(raw_sources, list) or not all(isinstance(item, dict) for item in raw_sources):
            raise ValueError()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError('지원하지 않는 프로젝트 파일입니다.') from None
    try:
        return _import_checked(store, raw, assets, kind, raw_sources)
    except ValidationError as error:
        raise ValueError(_validation_message(error)) from None
    except (KeyError, TypeError, AttributeError):
        raise ValueError(CORRUPT) from None


def _import_checked(store, raw, assets, kind, raw_sources):
    from .daily import save_photo
    from .custom_music import save_music
    from .custom_font import save_font

    photo_cache = {}

    def bytes_for(name, allowed, limit):
        if not isinstance(name, str) or '/' in name or '\\' in name or Path(name).suffix.lower() not in allowed:
            raise ValueError('프로젝트 첨부 파일 형식이 올바르지 않습니다.')
        encoded = assets.get(name)
        if not isinstance(encoded, str) or len(encoded) > limit * 4 // 3 + 8:
            raise ValueError('프로젝트 첨부 파일이 없거나 너무 큽니다.')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error):
            raise ValueError('프로젝트 첨부 파일을 읽을 수 없습니다.') from None
        if len(content) > limit:
            raise ValueError('프로젝트 첨부 파일이 너무 큽니다.')
        return content

    def photo_id(name):
        if not name:
            return ''
        if name not in photo_cache:
            photo_cache[name] = save_photo(store.assets,
                                           bytes_for(name, ('.jpg', '.jpeg', '.png'), 20_000_000), name)['asset_id']
        return photo_cache[name]

    scenes, photos = [], []
    for index, source in enumerate(raw['scenes']):
        asset_id = photo_id(source.get('photoID', ''))
        # iPhone drafts may carry empty titles or over-long copy; normalize before validation.
        scene = {'title': _text(source.get('title'), 90).strip() or f'장면 {index + 1}',
                 'body': _text(source.get('body'), 500),
                 'narration': _text(source.get('narration'), 700),
                 'duration': _number(source.get('duration'), 4, 2, 30),
                 'source_ids': source.get('sourceIDs', []),
                 'image_asset_id': asset_id if kind == 'news' else '',
                 'image_search_query': source.get('imageSearchQuery') or '',
                 'image_author': source.get('imageAuthor') or '', 'image_license': source.get('imageLicense') or '',
                 'image_page_url': source.get('imagePageURL') or '', 'image_license_url': source.get('imageLicenseURL') or ''}
        scenes.append(scene)
        if kind == 'daily':
            if not asset_id:
                raise ValueError('사진 영상의 사진 파일이 빠졌습니다.')
            filename = _text(source.get('photoFilename')) or _text(source.get('title')) or '사진'
            photos.append({'asset_id': asset_id, 'filename': filename[:150],
                           'fit': source.get('photoFit', 'cover'),
                           'position_x': source.get('positionX', .5),
                           'position_y': source.get('positionY', .5)})
    music_asset_id = ''
    if raw.get('musicAssetID'):
        name = raw['musicAssetID']
        music_asset_id = save_music(store.assets,
            bytes_for(name, ('.mp3', '.m4a', '.wav'), 25_000_000), name)['asset_id']
    font_asset_id = ''
    if raw.get('fontAssetID'):
        name = raw['fontAssetID']
        font_asset_id = save_font(store.assets,
            bytes_for(name, ('.ttf', '.otf'), 20_000_000), name)['asset_id']
    source_rows = [{'title': s['title'], 'text': s['text'], 'url': s.get('url', ''),
                    'rights': s.get('rights', '')} for s in raw_sources]
    thumbnail_id = raw.get('thumbnailSceneID')
    thumbnail_scene = next((i for i, scene in enumerate(raw['scenes']) if scene.get('id') == thumbnail_id), None) if thumbnail_id else 0
    if thumbnail_scene is None:
        raise ValueError('썸네일 장면이 프로젝트에 없습니다.')
    title = _text(raw.get('title'), 150).strip() or ('가져온 일상 영상' if kind == 'daily' else '가져온 카드 영상')
    position = raw.get('subtitlePosition')
    if position not in ('bottom', 'center'):
        # Older files only stored subtitleY; pick whichever preset it is closer to.
        y = raw.get('subtitleY')
        position = 'center' if isinstance(y, (int, float)) and abs(y - .5) < abs(y - .76) else 'bottom'
    incoming = {'thumbnail_scene': thumbnail_scene, 'content_type': kind, 'title': title, 'scenes': scenes, 'photos': photos,
                'sources': source_rows, 'caption': _text(raw.get('caption'), 2200),
                'subtitle_position': position,
                'template': raw.get('template', 'ink'), 'brand': raw.get('brand', 'STUDIO'),
                'subtitle_x': raw.get('subtitleX', .5), 'subtitle_y': raw.get('subtitleY'),
                'subtitle_style': raw.get('subtitleStyle', 'box'),
                'subtitle_size': raw.get('subtitleSize') or 50,
                'motion': raw.get('motion') or 'zoom', 'transition': raw.get('transition') or 'fade',
                'subtitle_font_id': font_asset_id, 'subtitle_font_name': raw.get('fontName', ''),
                'music_id': raw.get('musicID', '') if not music_asset_id else '',
                'music_asset_id': music_asset_id, 'music_filename': raw.get('musicName', ''),
                'music_volume': raw.get('musicVolume', .35), 'music_offset': raw.get('musicOffset') or 0,
                'mood': raw.get('mood') or '일상', 'description': raw.get('description') or '',
                'tone': raw.get('tone') or '담백하고 자연스럽게', 'voice': False}
    fields = ProjectInput.model_validate(incoming).model_dump()
    p = {**fields, 'id': new_id(), 'revision': 1, 'state': 'EDITABLE', 'approved_hash': '',
         'render': None, 'created_at': now(), 'updated_at': now()}
    store.put('projects', p)
    return p
