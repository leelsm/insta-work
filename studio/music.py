"""Bundled, source-verified music shared by the Mac and iPhone editors."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / 'resources' / 'music'
CATALOG = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
MUSIC = CATALOG['tracks']
MOODS = tuple(CATALOG['recommendations'])


def track_for(project):
    if project.get('music_asset_id'):
        return None
    return next((t for t in MUSIC if t['id'] == project.get('music_id', 'slow-morning')), None)


def music_path(track):
    return ROOT / track['filename'] if track else None


def posting_caption(project):
    caption = project.get('caption', '').strip()
    track = track_for(project)
    credit = track['attribution'] if track else ''
    if credit and credit not in caption:
        caption = '\n\n'.join(filter(None, (caption, credit)))
    return caption


def write_music_notices(directory, project):
    directory = Path(directory)
    track = track_for(project)
    if track:
        notice = f'{track["title"]} — {track["artist"]}\n{track["license"]}\n{track["license_url"]}\n'
        if track['attribution']:
            notice += '\n게시 문안에 아래 출처를 포함하세요.\n' + track['attribution'] + '\n'
        else:
            notice += '\n앱에서 제작한 오리지널 연주곡입니다. 개인·상업 영상에 무료로 사용·편집할 수 있으며 출처 표기는 필요하지 않습니다.\n'
        (directory / 'music-license.txt').write_text(notice, encoding='utf-8')
    (directory / 'posting-caption.txt').write_text(posting_caption(project), encoding='utf-8')
