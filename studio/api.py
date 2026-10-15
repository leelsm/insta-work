import hashlib
import hmac
import io
import json
import secrets
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.background import BackgroundTask

from .adapters import Meta, client, json_response, require_openai, search_news, speech
from .ranking import RankingNews
from .jobs import Jobs, digest
from .models import AppearanceInput, AccountInput, ArticleSummaryInput, ImageSearchInput, ImageSelectInput, GenerateInput, ProjectInput, ProjectUpdate, RevisionInput, SettingsInput
from .renderer import card
from .storage import SECRET_NAMES, Store, Vault, new_id, now

ROOT = Path(__file__).resolve().parent.parent


def equal(left, right):
    return hmac.compare_digest(str(left).encode('utf-8'), str(right).encode('utf-8'))


def create_app(store=None, vault=None, session_token=None, stop_callback=None, activate_callback=None, review_callback=None):
    store = store or Store()
    vault = vault or Vault(store.root)
    token = session_token or secrets.token_urlsafe(32)
    jobs = Jobs(store, vault)
    ranking_news = RankingNews()

    @asynccontextmanager
    async def lifespan(app):
        store.recover()
        yield
        jobs.shutdown()

    app = FastAPI(title='Instagram Content Studio', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.vault, app.state.jobs, app.state.session_token = store, vault, jobs, token

    @app.middleware('http')
    async def local_security(request: Request, call_next):
        host = request.headers.get('host', '')
        if host.split(':')[0] not in ('127.0.0.1', 'localhost', 'testserver'):
            return JSONResponse({'detail': '허용되지 않은 호스트입니다.'}, 403)
        if store.settings().get('privacy_mode') == 'local_only':
            path = request.url.path
            allowed_local_test = path == '/api/settings/test/llm/ollama' or (path == '/api/settings/test/llm' and store.settings().get('llm_provider') == 'ollama')
            if path.startswith('/api/settings/test/') and not allowed_local_test or path in ('/api/speech-test', '/api/news', '/api/news/popular', '/api/news/article-summary', '/api/images/search', '/api/images/select', '/api/images/preview') or path.startswith('/api/accounts') and request.method != 'GET' or path.startswith('/api/publications/') and request.method != 'GET':
                return JSONResponse({'detail': '로컬 전용 모드에서 외부 API 요청을 차단했습니다.'}, 403)
        origin = request.headers.get('origin')
        if origin and origin != f'http://{host}':
            return JSONResponse({'detail': '다른 웹사이트의 요청은 허용하지 않습니다.'}, 403)
        if request.url.path.startswith(('/api/', '/media/', '/manuals/')) and request.url.path not in ('/api/health', '/api/session'):
            if not equal(request.cookies.get('studio_session', ''), token):
                return JSONResponse({'detail': '앱을 통해 다시 접속하세요.'}, 401)
            if request.method not in ('GET', 'HEAD', 'OPTIONS') and not equal(request.headers.get('x-studio-token', ''), token):
                return JSONResponse({'detail': '요청 인증이 필요합니다.'}, 403)
        try:
            limit = 250_000_000 if request.url.path in ('/api/restore', '/api/projects/transfer') else (25_000_000 if request.url.path == '/api/custom-music' else (20_000_000 if request.url.path in ('/api/photos', '/api/fonts') else 2_000_000))
            if int(request.headers.get('content-length', '0')) > limit:
                return JSONResponse({'detail': '요청이 너무 큽니다.'}, 413)
        except ValueError:
            return JSONResponse({'detail': '잘못된 요청입니다.'}, 400)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store' if request.url.path.startswith(('/api/', '/media/')) else 'no-cache'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, 400)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        # Default validation errors echo submitted input, including credentials.
        return JSONResponse({'detail': '입력값의 길이·형식 또는 출처 번호를 확인하세요.',
            'fields': [list(e['loc']) for e in exc.errors()]}, 422)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': '항목을 찾을 수 없습니다.'}, 404)

    @app.exception_handler(httpx.HTTPError)
    async def remote(request, exc):
        return JSONResponse({'detail': '외부 서비스 연결 실패. 네트워크 상태를 확인하세요.'}, 502)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'app': 'instagram-content-studio'}

    @app.post('/api/session')
    async def session(request: Request):
        data = await request.json()
        if not isinstance(data, dict) or not equal(data.get('token', ''), token):
            raise HTTPException(401, '실행 주소가 유효하지 않습니다. 앱을 다시 실행하세요.')
        response = JSONResponse({'ok': True})
        response.set_cookie('studio_session', token, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/api/settings')
    def settings():
        from .models import SettingsInput
        defaults = SettingsInput().model_dump(exclude={'secrets'})
        from .model_status import statuses
        saved = store.settings()
        flags = vault.flags()
        public = {k: v for k, v in saved.items() if not k.startswith('_llm_')}
        return {**defaults, **public, 'configured': flags, 'model_status': statuses(saved, flags)}

    @app.put('/api/appearance')
    def appearance(data: AppearanceInput):
        changes = data.model_dump(exclude_none=True)
        if not changes:
            raise ValueError('변경할 화면 설정이 없습니다.')
        with store.lock:
            current = store.settings()
            if 'nav_groups' in changes:
                changes['nav_groups'] = {**current.get('nav_groups', {}), **changes['nav_groups']}
            store.save_settings({**current, **changes})
        return changes

    @app.put('/api/settings')
    def save_settings(data: SettingsInput):
        if any(j['status'] == 'RUNNING' for j in store.list('jobs')):
            raise ValueError('진행 중인 작업이 끝난 뒤 모델·보안 설정을 변경하세요.')
        if set(data.secrets) - SECRET_NAMES:
            raise ValueError('지원하지 않는 비밀값 이름입니다.')
        from .model_status import invalidate
        with store.lock:
            old = store.settings()
            for name, value in data.secrets.items():
                vault.set(name, value)
            updated = {**old, **data.model_dump(exclude={'secrets'}), 'theme': old.get('theme', 'dark'), 'nav_collapsed': old.get('nav_collapsed', False), 'nav_groups': old.get('nav_groups', {})}
            store.save_settings(invalidate(old, updated, set(data.secrets)))
        return settings()

    @app.post('/api/settings/models/{provider}')
    def available_models(provider: str):
        from .llm import list_models, PROVIDERS
        if provider not in PROVIDERS:
            raise HTTPException(404, '지원하지 않는 AI 서비스입니다.')
        return {'models': list_models(vault, store.settings(), provider)}

    @app.post('/api/settings/test/{provider}')
    def test_settings(provider: str):
        if provider == 'llm':
            from .llm import generate_json, PROVIDERS
            from .model_status import record_check
            snapshot = store.settings()
            selected = snapshot.get('llm_provider', 'openai')
            try:
                result, _ = generate_json(vault, snapshot, 'Return JSON {"ok":true}.', [{'type':'input_text','text':'Connection test'}], {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}, 'connection_test')
                if result.get('ok') is not True:
                    raise ValueError('모델 응답을 확인하지 못했습니다.')
            except (ValueError, httpx.HTTPError):
                record_check(store, selected, snapshot, 'failed')
                raise
            recorded = record_check(store, selected, snapshot, 'success')
            return {'message': PROVIDERS[selected] + (' 텍스트 생성 연결 성공. 사진 입력 지원은 별도 확인이 필요합니다.' if recorded else ' 테스트 중 설정이 변경되어 결과를 적용하지 않았습니다.')}
        if provider == 'naver':
            search_news(vault, '기술', days=30, provider=store.settings().get('naver_provider', 'hub'))
            return {'message': '네이버 뉴스 검색 연결 성공'}
        if provider == 'openai':
            with client() as c:
                json_response(c.get('https://api.openai.com/v1/models/' + store.settings().get('model', 'gpt-4.1-mini'), headers=require_openai(vault)), 'OpenAI')
            return {'message': '모델 접근 확인 성공. 실제 생성은 콘텐츠 만들기에서 실행하세요.'}
        if provider == 's3':
            from .adapters import s3_client
            c = s3_client(vault, store.settings())
            try:
                c.head_bucket(Bucket=store.settings()['s3_bucket'])
            except Exception:
                raise ValueError('S3 접근 실패. 버킷·지역과 권한을 확인하세요.') from None
            return {'message': 'S3 버킷 접근 성공. 실제 게시 시 업로드 권한도 필요합니다.'}
        raise HTTPException(404)

    @app.post('/api/settings/test/llm/{provider}')
    def test_llm_provider(provider: str):
        from .llm import generate_json, PROVIDERS
        from .model_status import FIELDS, record_check, statuses
        if provider not in FIELDS:
            raise HTTPException(404, '지원하지 않는 AI 제공자입니다.')
        snapshot = store.settings()
        row = next(item for item in statuses(snapshot, vault.flags()) if item['provider'] == provider)
        if row['blocked']:
            raise HTTPException(403, '현재 보안 정책에서 이 제공자는 차단되어 있습니다.')
        if row['missing_fields']:
            raise HTTPException(400, '테스트 전에 필수 설정을 완료하세요: ' + ' · '.join(row['missing_fields']))
        candidate = {**snapshot, 'llm_provider': provider}
        schema = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}
        try:
            result, _ = generate_json(vault, candidate, 'Return JSON {"ok":true}.',
                [{'type':'input_text','text':'Connection test'}], schema, 'connection_test')
            if result.get('ok') is not True:
                raise ValueError('모델 응답을 확인하지 못했습니다.')
        except (ValueError, httpx.HTTPError):
            record_check(store, provider, snapshot, 'failed')
            raise
        recorded = record_check(store, provider, snapshot, 'success')
        message = PROVIDERS[provider] + (' 텍스트 연결에 성공했습니다. 사진 입력 지원은 별도 확인이 필요합니다.' if recorded else ' 테스트 중 설정이 바뀌어 결과를 저장하지 않았습니다.')
        return {'message': message, 'recorded': recorded}

    @app.post('/api/speech-test')
    def speech_test():
        return Response(speech(vault, store.settings(), '안녕하세요. 콘텐츠 스튜디오의 한국어 AI 음성입니다.'), media_type='audio/wav')

    @app.get('/api/accounts')
    def accounts():
        return store.list('accounts')

    @app.get('/api/backup')
    def export_backup():
        from .maintenance import backup
        path = backup(store)
        return FileResponse(path, filename='content-studio-backup.zip', media_type='application/zip',
                            background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post('/api/restore')
    async def import_backup(request: Request):
        from .maintenance import restore
        if any(j['status'] == 'RUNNING' for j in store.list('jobs')):
            raise ValueError('진행 중인 작업을 완료하거나 중단한 후 복원하세요.')
        with tempfile.SpooledTemporaryFile(max_size=2_000_000) as f:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 200_000_000:
                    raise HTTPException(413, '백업 파일은 200MB 이하여야 합니다.')
                f.write(chunk)
            f.seek(0)
            with store.lock:
                if any(j['status'] == 'RUNNING' for j in store.list('jobs')):
                    raise ValueError('진행 중인 작업을 먼저 완료하세요.')
                return restore(store, f)

    @app.get('/api/diagnostics')
    def diagnostics():
        import platform
        data = {'app_version': '0.1.0', 'platform': platform.system(), 'machine': platform.machine(),
                'jobs': store.list('jobs')[:100],
                'publications': [{k: p.get(k) for k in ('id', 'project_id', 'revision', 'status', 'stage', 'container_id', 'media_id', 'updated_at')} for p in store.list('publications')]}
        return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="studio-diagnostics.json"'})

    @app.post('/api/accounts')
    def add_account(data: AccountInput):
        for account in store.list('accounts'):
            if account['user_id'] == data.user_id:
                raise ValueError('이미 등록된 계정입니다. 토큰 갱신 기능을 사용하세요.')
        account = {'id': new_id(), 'name': data.name, 'user_id': data.user_id, 'status': 'UNVERIFIED', 'username': '', 'created_at': now()}
        vault.set('account:' + account['id'], data.token)
        store.put('accounts', account)
        return account

    @app.post('/api/accounts/{id}/test')
    def test_account(id: str):
        account = store.get('accounts', id)
        try:
            profile = Meta(vault, store.settings(), account).profile()
            if profile.get('account_type') not in ('BUSINESS', 'MEDIA_CREATOR'):
                raise ValueError('프로페셔널 계정인지 확인하세요.')
        except (ValueError, httpx.HTTPError):
            account['status'] = 'ERROR'
            store.put('accounts', account)
            raise
        account.update(username=profile.get('username', ''), status='CONNECTED', checked_at=now())
        store.put('accounts', account)
        return account

    @app.put('/api/accounts/{id}/token')
    def renew_token(id: str, data: AccountInput):
        account = store.get('accounts', id)
        if data.user_id != account['user_id']:
            raise ValueError('같은 계정의 토큰을 입력하세요.')
        vault.set('account:' + id, data.token)
        account.update(name=data.name, status='UNVERIFIED')
        store.put('accounts', account)
        return account

    @app.get('/api/news')
    def news(query: str = Query(min_length=1, max_length=100), sort: str = 'date', days: int = Query(default=7, ge=1, le=365), exclude: str = Query(default='', max_length=300)):
        if sort not in ('date', 'sim'):
            raise ValueError('지원하지 않는 정렬입니다.')
        results = search_news(vault, query, sort, days, provider=store.settings().get('naver_provider', 'hub'))
        words = [w.strip() for w in exclude.split(',') if w.strip()]
        return [r for r in results if not any(w in r['title']+r['text'] for w in words)]

    @app.post('/api/news/article-summary')
    def news_article_summary(data: ArticleSummaryInput):
        from .article_summary import article_summary
        return article_summary(data.url, data.title)

    @app.post('/api/images/search')
    def image_search(data: ImageSearchInput):
        from .images import search_commons
        return {'images': search_commons(data.query)}

    @app.get('/api/images/preview')
    def image_preview(url: str = Query(min_length=1, max_length=2000)):
        from .images import fetch_image
        data, mime = fetch_image(url)
        return Response(data, media_type=mime, headers={'Cache-Control': 'no-store'})

    @app.post('/api/images/select')
    def image_select(data: ImageSelectInput):
        from .images import _license, select_and_save
        name, _, allowed = _license({'LicenseShortName': {'value': data.license}})
        if not allowed or name != data.license:
            raise ValueError('상업적 사용과 편집이 가능한 공개 라이선스 이미지인지 확인할 수 없습니다.')
        return select_and_save(store.assets, data.model_dump())

    @app.get('/api/news/popular')
    def popular_news(date: str = Query(default='', max_length=10)):
        return ranking_news.fetch(date or None)

    @app.post('/api/photos')
    async def upload_photo(request: Request, filename: str = '사진'):
        from .daily import save_photo
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 20_000_000:
                raise HTTPException(413, '사진은 한 장당 20MB 이하여야 합니다.')
        return save_photo(store.assets, data, filename)

    @app.get('/api/photos/{asset_id}')
    def get_photo(asset_id: str):
        from .daily import asset_path
        return FileResponse(asset_path(store.assets, asset_id), media_type='image/jpeg')

    @app.get('/api/music')
    def music_library():
        from .daily import MUSIC
        return MUSIC

    @app.get('/api/music/{track_id}')
    def music_preview(track_id: str):
        from .music import MUSIC, music_path
        track = next((t for t in MUSIC if t['id'] == track_id), None)
        if not track:
            raise HTTPException(404)
        path = music_path(track)
        return FileResponse(path, media_type='audio/mpeg' if path.suffix == '.mp3' else 'audio/wav')

    @app.post('/api/custom-music')
    async def upload_custom_music(request: Request, filename: str = Query(min_length=1, max_length=150)):
        from .custom_music import MAX_BYTES, save_music
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise HTTPException(413, '음악 파일은 25MB 이하여야 합니다.')
        return save_music(store.assets, data, filename)

    @app.get('/api/custom-music/{asset_id}')
    def custom_music_preview(asset_id: str):
        from .custom_music import EXTENSIONS, asset_path
        path = asset_path(store.assets, asset_id)
        return FileResponse(path, media_type=EXTENSIONS[path.suffix])

    @app.post('/api/fonts')
    async def upload_font(request: Request, filename: str = Query(min_length=1, max_length=150)):
        from .custom_font import MAX_BYTES, save_font
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise HTTPException(413, '폰트 파일은 20MB 이하여야 합니다.')
        return save_font(store.assets, data, filename)

    @app.get('/api/fonts/library')
    def font_library():
        from .custom_font import bundled_library
        return {'fonts': bundled_library(store.assets)}

    @app.get('/api/fonts/{asset_id}')
    def font_preview(asset_id: str):
        from .custom_font import EXTENSIONS, asset_path
        path = asset_path(store.assets, asset_id)
        return FileResponse(path, media_type=EXTENSIONS[path.suffix])

    @app.get('/api/projects')
    def projects():
        return store.list('projects')

    @app.post('/api/projects')
    def create_project(data: ProjectInput):
        from .daily import validate_photos
        from .images import validate_scene_images
        validate_photos(data.model_dump(), store.assets)
        validate_scene_images(data.model_dump(), store.assets)
        from .custom_music import validate_music_asset
        validate_music_asset(data.model_dump(), store.assets)
        from .custom_font import validate_font_asset
        validate_font_asset(data.model_dump(), store.assets)
        p = {**data.model_dump(), 'id': new_id(), 'revision': 1, 'state': 'EDITABLE', 'approved_hash': '', 'render': None,
             'created_at': now(), 'updated_at': now()}
        store.put('projects', p)
        return p

    @app.post('/api/projects/{id}/recommend-images')
    def recommend_images(id: str, data: RevisionInput):
        if store.settings().get('privacy_mode') == 'local_only':
            raise ValueError('로컬 전용 설정에서는 인터넷 이미지 검색을 사용할 수 없습니다.')
        from .images import attach_first_results, sync_caption_credits
        with store.lock:
            p = current(id, data.revision)
        if p.get('content_type') == 'daily':
            raise ValueError('뉴스 카드에서만 자동 이미지 추천을 사용할 수 있습니다.')
        for scene in p['scenes']:
            if not scene.get('image_search_query'):
                scene['image_search_query'] = p['title']
        p['scenes'] = attach_first_results(p['scenes'], store.assets)
        p['caption'] = sync_caption_credits(p['caption'], p['scenes'])
        p.update(revision=p['revision'] + 1, state='EDITABLE', approved_hash='', render=None, updated_at=now())
        with store.lock:
            current(id, data.revision)
            store.put('projects', p)
        return p

    @app.get('/api/projects/{id}')
    def project(id: str):
        return store.get('projects', id)

    @app.get('/api/projects/{id}/transfer')
    def export_transfer(id: str):
        from .transfer import export_project
        target = store.get('projects', id)
        data = json.dumps(export_project(store, target), ensure_ascii=False).encode('utf-8')
        if len(data) > 250_000_000:
            raise ValueError('프로젝트 파일이 250MB를 넘습니다.')
        destination = store.root / 'exports'
        destination.mkdir(exist_ok=True)
        path = destination / f'{new_id()}.studio'
        path.write_bytes(data)
        return FileResponse(path, filename='content-studio-' + id[:8] + '.studio',
                            media_type='application/json', background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post('/api/projects/transfer')
    async def import_transfer(request: Request):
        from .transfer import MAX_BYTES, import_project
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise HTTPException(413, '프로젝트 파일은 250MB 이하여야 합니다.')
        return import_project(store, data)

    @app.delete('/api/projects/{id}')
    def delete_project(id: str):
        with store.lock:
            try:
                deleted = store.get('projects', id)
            except KeyError:
                raise HTTPException(404, '콘텐츠를 찾을 수 없습니다.') from None
            if store.active(id):
                raise HTTPException(409, '작업 중인 콘텐츠는 삭제할 수 없습니다.')
            store.delete_project(id)
            media_dir = (store.media / id).resolve()
            if media_dir.is_relative_to(store.media.resolve()) and media_dir.exists():
                shutil.rmtree(media_dir)
            referenced_assets = {photo.get('asset_id') for project in store.list('projects')
                                 for photo in project.get('photos', [])}
            referenced_assets.update(scene.get('image_asset_id') for project in store.list('projects')
                                     for scene in project.get('scenes', []))
            referenced_assets.update(project.get('music_asset_id') for project in store.list('projects'))
            referenced_assets.update(project.get('subtitle_font_id') for project in store.list('projects'))
            removed_assets = {photo.get('asset_id') for photo in deleted.get('photos', [])}
            removed_assets.update(scene.get('image_asset_id') for scene in deleted.get('scenes', []))
            removed_assets.add(deleted.get('music_asset_id'))
            removed_assets.add(deleted.get('subtitle_font_id'))
            for asset_id in removed_assets - referenced_assets:
                if asset_id:
                    asset = (store.assets / f'{asset_id}.jpg').resolve()
                    if asset.is_relative_to(store.assets.resolve()):
                        asset.unlink(missing_ok=True)
                    from .custom_music import EXTENSIONS
                    for extension in EXTENSIONS:
                        (store.assets / f'{asset_id}{extension}').unlink(missing_ok=True)
                    from .custom_font import EXTENSIONS as FONT_EXTENSIONS
                    for extension in FONT_EXTENSIONS:
                        (store.assets / f'{asset_id}{extension}').unlink(missing_ok=True)
            return {'deleted': True, 'id': id}

    def current(id, revision):
        p = store.get('projects', id)
        if p['revision'] != revision:
            raise HTTPException(409, '다른 화면에서 변경되었습니다. 새로고침 후 다시 시도하세요.')
        if store.active(id):
            raise HTTPException(409, '작업 중인 콘텐츠는 변경할 수 없습니다.')
        return p

    @app.put('/api/projects/{id}')
    def save_project(id: str, data: ProjectUpdate):
        with store.lock:
            p = current(id, data.revision)
            next_fields = data.model_dump(exclude={'revision'})
            from .daily import validate_photos
            from .images import validate_scene_images
            validate_photos(next_fields, store.assets)
            validate_scene_images(next_fields, store.assets)
            from .custom_music import validate_music_asset
            validate_music_asset(next_fields, store.assets)
            from .custom_font import validate_font_asset
            validate_font_asset(next_fields, store.assets)
            from .images import sync_caption_credits
            next_fields['caption'] = sync_caption_credits(next_fields['caption'], next_fields['scenes'])
            if all(p.get(k) == v for k, v in next_fields.items()):
                return p
            p.update(next_fields, revision=p['revision']+1, state='EDITABLE', approved_hash='', render=None, updated_at=now())
            store.put('projects', p)
            return p

    @app.post('/api/projects/{id}/generate')
    def generate_project(id: str, data: GenerateInput):
        with store.lock:
            p = current(id, data.revision)
            if data.scene_index is not None and (p.get('content_type') != 'daily' or data.scene_index >= len(p['scenes'])):
                raise ValueError('일상 영상에서 자막을 추천할 장면을 선택하세요.')
            from .model_status import generation_settings
            snapshot = generation_settings(store.settings(), vault.flags(), data.provider, data.model)
            return jobs.start('generate', p, {'cards': data.cards, 'settings': snapshot, 'scene_index': data.scene_index})

    @app.post('/api/projects/{id}/render')
    def render_project(id: str, data: RevisionInput):
        with store.lock:
            p = current(id, data.revision)
            if p['voice']:
                require_openai(vault)
            return jobs.start('render', p)

    @app.post('/api/projects/{id}/approve')
    def approve(id: str, data: RevisionInput):
        with store.lock:
            p = current(id, data.revision)
            if not p.get('render') or p['render']['revision'] != p['revision']:
                raise ValueError('현재 버전의 영상을 먼저 렌더링하세요.')
            p.update(approved_hash=digest(p), state='APPROVED', updated_at=now())
            store.put('projects', p)
            return p

    @app.post('/api/projects/{id}/publish')
    def publish(id: str, data: RevisionInput):
        with store.lock:
            return jobs.start('publish', current(id, data.revision))

    @app.get('/api/projects/{id}/preview/{index}')
    def preview(id: str, index: int):
        p = store.get('projects', id)
        if index < 0 or index >= len(p['scenes']):
            raise HTTPException(404)
        if p.get('content_type') == 'daily':
            from .renderer import photo_background, photo_caption
            image = photo_background(p['photos'][index], store.assets).convert('RGBA')
            image.alpha_composite(photo_caption(p, p['scenes'][index], store.assets))
        else:
            image = card(p, p['scenes'][index], index, assets=store.assets)
        buffer = io.BytesIO(); image.thumbnail((360, 640)); image.save(buffer, 'PNG')
        return Response(buffer.getvalue(), media_type='image/png')

    @app.get('/api/jobs')
    def job_list():
        return store.list('jobs')[:100]

    @app.post('/api/jobs/{id}/cancel')
    def cancel(id: str):
        store.get('jobs', id)
        jobs.cancel(id)
        return {'ok': True}

    @app.get('/api/publications')
    def publications():
        return store.list('publications')

    @app.post('/api/publications/{id}/check')
    def check_publication(id: str):
        pub = store.get('publications', id)
        if store.active(pub['project_id']):
            raise ValueError('게시 작업이 진행 중입니다. 완료 후 확인하세요.')
        meta = Meta(vault, store.settings(), store.get('accounts', pub['account_id']))
        if pub.get('media_id'):
            pub.update(meta.media(pub['media_id']), status='PUBLISHED')
            # Don't replace our database ID with the remote media ID.
            pub['id'] = id
        elif pub.get('container_id'):
            remote = meta.status(pub['container_id']).get('status_code')
            pub['remote_status'] = remote
            if remote == 'PUBLISHED':
                pub['status'] = 'PUBLISHED'
            elif remote in ('ERROR', 'EXPIRED'):
                pub['status'] = 'FAILED'
                pub['stage'] = 'PROCESSING_ERROR'
            else:
                pub['status'] = 'NEEDS_RECONCILIATION'
        else:
            raise ValueError('원격 요청 ID를 확보하지 못했습니다. Instagram 프로필에서 직접 결과를 확인하세요. 자동 재전송하지 않습니다.')
        pub['updated_at'] = now()
        store.put('publications', pub)
        if pub['status'] == 'PUBLISHED':
            p = store.get('projects', pub['project_id'])
            if p['revision'] == pub['revision']:
                p['state'] = 'PUBLISHED'; store.put('projects', p)
        return pub

    @app.get('/media/{project_id}/{folder}/{filename}')
    def media(project_id: str, folder: str, filename: str, download: bool = False):
        if filename not in ('video.mp4', 'subtitles.srt', 'cards.zip', 'project.json', 'music-license.txt', 'posting-caption.txt', 'thumbnail.jpg') and not (filename.startswith('card-') and filename.endswith('.png')):
            raise HTTPException(404)
        p = (store.media / project_id / folder / filename).resolve()
        if not p.is_relative_to(store.media.resolve()) or not p.is_file():
            raise HTTPException(404)
        types = {'thumbnail.jpg': 'image/jpeg', 'video.mp4': 'video/mp4', 'subtitles.srt': 'application/x-subrip', 'cards.zip': 'application/zip', 'project.json': 'application/json', 'music-license.txt': 'text/plain; charset=utf-8', 'posting-caption.txt': 'text/plain; charset=utf-8'}
        return FileResponse(p, media_type=types.get(filename, 'image/png'), filename=filename if download else None)

    manuals = {
        'USER_MANUAL.md': ('프로그램 사용 방법', '뉴스·사진 선택부터 영상 제작까지'),
        'API_SETUP_GUIDE.md': ('API 발급 · 계정 준비', '모델·뉴스 API 키와 계정 준비'),
        'S3_SETUP_GUIDE.md': ('기존 영상 전달 설정', 'S3 설정과 현재 업로드 차단 정책'),
        'PRD.md': ('제품 요구사항 · 개발 계획', '제품 범위와 단계별 개발 계획'),
        'IMPLEMENTATION_STATUS.md': ('구현 · 검증 현황', '지원 기능과 검증 범위'),
    }

    @app.get('/api/manuals')
    def manual_list():
        return [{'id': name, 'title': item[0], 'description': item[1]} for name, item in manuals.items()]

    @app.get('/api/manuals/{name}')
    def manual_content(name: str):
        if name not in manuals:
            raise HTTPException(404, '가이드를 찾을 수 없습니다.')
        path = ROOT / 'docs' / name
        if not path.is_file():
            raise HTTPException(404, '앱에 포함된 가이드 파일이 없습니다.')
        return {'id': name, 'title': manuals[name][0], 'markdown': path.read_text(encoding='utf-8')}

    @app.get('/manuals/{name}')
    def manual(name: str):
        if name not in manuals:
            raise HTTPException(404)
        return FileResponse(ROOT / 'docs' / name, media_type='text/plain; charset=utf-8')

    @app.post('/api/shutdown')
    def shutdown():
        if stop_callback:
            import threading
            threading.Timer(0.2, stop_callback).start()
        return {'ok': True}

    @app.post('/api/video-review')
    async def video_review(request: Request):
        data = await request.json()
        if not isinstance(data, dict) or type(data.get('reviewing')) is not bool:
            raise HTTPException(422, 'reviewing must be a boolean')
        if review_callback:
            review_callback(data['reviewing'])
        return {'ok': True}

    @app.post('/api/activate')
    def activate():
        if activate_callback:
            activate_callback()
        return {'ok': True}

    dist = ROOT / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='ui')
    return app
