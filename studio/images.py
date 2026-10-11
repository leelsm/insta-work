"""Search reusable, attributed card artwork on Wikimedia Commons."""
from html import unescape
import re
from urllib.parse import quote, urlsplit

import httpx

from .adapters import RemoteError

API = 'https://commons.wikimedia.org/w/api.php'
AGENT = 'ContentStudio/1.0 (local desktop app; image search)'


def _plain(value):
    return unescape(re.sub(r'<[^>]*>', '', str(value or ''))).strip()[:300]


def _license(meta):
    name = _plain(meta.get('LicenseShortName', {}).get('value'))
    lower = name.lower()
    # Exclude non-commercial and no-derivatives restrictions for social video reuse.
    allowed = ('cc0' in lower or 'public domain' in lower or
               (('cc by' in lower or 'cc-by' in lower) and 'nc' not in lower and 'nd' not in lower))
    return name, _plain(meta.get('LicenseUrl', {}).get('value')), allowed


def search_commons(query, limit=5):
    query = re.sub(r'\s+', ' ', query).strip()[:300]
    if len(query) < 2:
        raise ValueError('카드 제목이나 이미지 검색어를 입력하세요.')
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=8), follow_redirects=False, trust_env=False,
                          headers={'User-Agent': AGENT, 'Accept': 'application/json'}) as client:
            response = client.get(API, params={
                'action': 'query', 'generator': 'search', 'gsrsearch': query,
                'gsrnamespace': 6, 'gsrlimit': 20, 'prop': 'imageinfo',
                'iiprop': 'url|extmetadata', 'iiurlwidth': 1000,
                'format': 'json', 'formatversion': 2,
            })
        if not response.is_success:
            raise RemoteError(f'Wikimedia Commons 이미지 검색 실패 (HTTP {response.status_code}).')
        pages = response.json().get('query', {}).get('pages', [])
    except RemoteError:
        raise
    except (httpx.HTTPError, ValueError, TypeError):
        raise RemoteError('Wikimedia Commons에 연결할 수 없습니다. 잠시 후 다시 검색하세요.') from None
    results, seen = [], set()
    for page in sorted(pages, key=lambda page: page.get('index', 999)):
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata') or {}
        name, license_url, allowed = _license(meta)
        thumb = info.get('thumburl', '')
        parsed = urlsplit(thumb)
        if (not allowed or parsed.scheme != 'https' or parsed.hostname != 'upload.wikimedia.org' or
                not thumb or page.get('title') in seen):
            continue
        title = str(page.get('title', '')).removeprefix('File:')[:120]
        if not title:
            continue
        page_url = 'https://commons.wikimedia.org/wiki/File:' + quote(title.replace(' ', '_'), safe='()_,-.')
        if len(page_url) > 250:
            continue
        seen.add(page.get('title'))
        results.append({
            'image_url': thumb, 'title': title,
            'author': _plain(meta.get('Artist', {}).get('value')) or _plain(meta.get('Credit', {}).get('value')) or '저자 정보 없음',
            'license': name, 'license_url': license_url,
            'page_url': page_url,
        })
        if len(results) >= limit:
            break
    return results


def fetch_image(image_url):
    parsed = urlsplit(image_url)
    if parsed.scheme != 'https' or parsed.hostname != 'upload.wikimedia.org' or parsed.port not in (None, 443):
        raise ValueError('Wikimedia Commons에서 찾은 이미지 주소만 사용할 수 있습니다.')
    try:
        with httpx.Client(timeout=httpx.Timeout(20, connect=8), follow_redirects=False, trust_env=False,
                          headers={'User-Agent': AGENT, 'Accept': 'image/*'}) as client:
            response = client.get(image_url)
        if not response.is_success:
            raise RemoteError('이미지 다운로드에 실패했습니다. 다른 이미지를 선택하세요.')
        mime = response.headers.get('content-type', '').split(';', 1)[0].lower()
        if mime not in ('image/jpeg', 'image/png', 'image/webp') or len(response.content) > 8_000_000:
            raise RemoteError('이미지 형식 또는 크기를 확인하지 못했습니다. 다른 이미지를 선택하세요.')
        return response.content, mime
    except RemoteError:
        raise
    except httpx.HTTPError:
        raise RemoteError('이미지를 다운로드할 수 없습니다. 다른 이미지를 선택하세요.') from None


def select_and_save(root, candidate):
    data, _ = fetch_image(candidate['image_url'])
    from .daily import save_photo
    asset = save_photo(root, data, candidate['title'])
    return {
        **asset,
        'image_title': candidate['title'], 'image_author': candidate['author'],
        'image_license': candidate['license'], 'image_license_url': candidate['license_url'],
        'image_page_url': candidate['page_url'],
    }


def attach_first_results(scenes, root, progress=None):
    """Attach the best open-license result per scene; text drafting still succeeds if search fails."""
    for index, scene in enumerate(scenes):
        if scene.get('image_asset_id'):
            continue
        query = (scene.get('image_search_query') or scene.get('title') or '').strip()
        scene['image_search_query'] = query[:300]
        if not query:
            continue
        if progress:
            progress(index)
        try:
            candidates = search_commons(query, limit=3)
            if candidates:
                selected = select_and_save(root, candidates[0])
                scene.update({key: value for key, value in selected.items() if key.startswith('image_')})
                scene['image_asset_id'] = selected['asset_id']
        except (RemoteError, ValueError, OSError):
            # Image lookup is optional; never discard a valid AI draft because Commons is unavailable.
            continue
    return scenes


def sync_caption_credits(caption, scenes):
    marker = '사진 출처 (카드별)'
    base = caption.split(marker, 1)[0].rstrip()
    lines = [f"{i+1}. {scene['image_author'][:60]} · {scene['image_license'][:40]} · {scene['image_page_url']}" +
             (f" · {scene['image_license_url']}" if len(scene.get('image_license_url', '')) <= 120 and scene.get('image_license_url') else '')
             for i, scene in enumerate(scenes)
             if scene.get('image_asset_id') and scene.get('image_page_url') and scene.get('image_license')]
    if not lines:
        return base[:2200]
    block = '\n\n' + marker + '\n'
    included = []
    for line in lines:
        if len(block) + len(line) + 1 > 1900:
            break
        included.append(line)
        block += line + '\n'
    if len(included) < len(lines):
        block += '추가 카드의 작가·라이선스는 각 카드 하단에 표기했습니다.\n'
    block = block.rstrip()
    return base[:max(0, 2200-len(block))].rstrip() + block


def validate_scene_images(project, root):
    from .daily import asset_path
    for scene in project.get('scenes', []):
        if scene.get('image_asset_id'):
            asset_path(root, scene['image_asset_id'])
