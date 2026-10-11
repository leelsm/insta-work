import hashlib
import json
import sqlite3
import threading
from pathlib import Path

import httpx

from .adapters import Meta, generate, upload_video
from .renderer import file_hash, render
from .storage import new_id, now


def digest(project):
    fields = {k: project[k] for k in ('title', 'sources', 'scenes', 'caption', 'account_id', 'template', 'accent', 'brand', 'voice', 'tone', 'revision')}
    fields['logo'] = project.get('logo', '')
    for key in ('content_type', 'photos', 'mood', 'description', 'music_id', 'music_volume', 'music_offset', 'motion', 'transition', 'subtitle_style', 'subtitle_position'):
        fields[key] = project.get(key)
    for key, default in (('music_asset_id', ''), ('music_filename', ''), ('subtitle_x', .5),
                         ('subtitle_y', None), ('subtitle_font_id', ''), ('subtitle_font_name', '')):
        value = project.get(key, default)
        if value != default:
            fields[key] = value
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Jobs:
    def __init__(self, store, vault):
        self.store, self.vault = store, vault
        self.events, self.threads, self.processes = {}, {}, {}
        self.lock = threading.RLock()
        self.stopping = False
        self.shutdown_started = False

    def start(self, kind, project, options=None):
        with self.lock, self.store.lock:
            if self.stopping:
                raise ValueError('앱을 종료 중입니다.')
            if self.store.active(project['id']):
                raise ValueError('이 콘텐츠에서 작업이 진행 중입니다.')
            if any(t.is_alive() for t in self.threads.values()):
                raise ValueError('다른 작업이 진행 중입니다. 완료 후 다시 실행하세요.')
            job = {'id': new_id(), 'project_id': project['id'], 'title': project['title'], 'kind': kind,
                   'status': 'RUNNING', 'progress': 0, 'message': '작업 준비 중', 'created_at': now(), 'updated_at': now()}
            if kind == 'generate' and options and 'settings' in options:
                from .model_status import FIELDS
                snapshot = options['settings']
                provider = snapshot['llm_provider']
                job.update(provider=provider, model=snapshot[FIELDS[provider][0]])
            if kind == 'publish':
                if not self.store.settings().get('allow_video_upload', False) or self.store.settings().get('privacy_mode') == 'local_only':
                    raise ValueError('영상 외부 업로드가 차단되어 있습니다. MP4를 내려받아 직접 게시하세요.')
                if project.get('approved_hash') != digest(project) or project.get('state') != 'APPROVED':
                    raise ValueError('최신 영상과 문안을 먼저 승인하세요.')
                if not project.get('render') or project['render']['revision'] != project['revision']:
                    raise ValueError('현재 버전의 영상을 다시 렌더링하세요.')
                account = self.store.get('accounts', project['account_id'])
                if account.get('status') != 'CONNECTED':
                    raise ValueError('계정 연결 테스트를 먼저 실행하세요.')
                # Validate local prerequisites before reserving a publication.
                from .adapters import s3_client
                s3_client(self.vault, self.store.settings())
                existing = next((p for p in self.store.list('publications') if p['project_id'] == project['id'] and p['revision'] == project['revision'] and p['account_id'] == project['account_id']), None)
                if existing and not (existing['status'] == 'FAILED' and existing.get('stage') in ('LOCAL', 'PROCESSING_ERROR')):
                    raise ValueError('이 버전에는 기존 게시 요청이 있습니다. 먼저 작업 이력에서 결과를 확인하세요.')
                pub = {'id': existing['id'] if existing else new_id(), 'project_id': project['id'], 'revision': project['revision'],
                       'account_id': project['account_id'], 'status': 'UPLOADING', 'container_id': '', 'media_id': '',
                       'created_at': now(), 'updated_at': now(), 'job_id': job['id'], 's3_key': '', 'stage': 'LOCAL'}
                try:
                    self.store.put('publications', pub)
                except sqlite3.IntegrityError:
                    raise ValueError('이 버전에는 기존 게시 요청이 있습니다. 먼저 작업 이력에서 결과를 확인하세요.') from None
                job['publication_id'] = pub['id']
            self.store.put('jobs', job)
            self.events[job['id']] = threading.Event()
            project['state'] = {'render': 'RENDERING', 'generate': 'GENERATING', 'publish': 'APPROVED'}[kind]
            self.store.put('projects', project)
            t = threading.Thread(target=self.run, args=(job, project, options or {}), daemon=True)
            self.threads[job['id']] = t
            t.start()
            return job

    def update(self, job, **fields):
        job.update(fields, updated_at=now())
        self.store.put('jobs', job)

    def process(self, job_id, p):
        with self.lock:
            if p is None:
                self.processes.pop(job_id, None)
            else:
                self.processes[job_id] = p

    def run(self, job, project, options):
        cancel = self.events[job['id']]
        last_progress = [-1]

        def progress(value, message):
            if value != last_progress[0]:
                last_progress[0] = value
                self.update(job, progress=value, message=message)

        try:
            settings = dict(options.get('settings') or self.store.settings())
            settings['_cancel_event'] = cancel
            settings['_process_callback'] = lambda p: self.process(job['id'], p)
            if job['kind'] == 'generate':
                progress(15, '제공 자료로 AI 카드 초안 생성 중')
                if project.get('content_type') == 'daily':
                    from .daily import generate_daily
                    progress(15, '사진에 맞는 자막 제안 중')
                    scenes, caption, usage = generate_daily(self.vault, settings, project, self.store.assets)
                else:
                    scenes, caption, usage = generate(self.vault, settings, project, options.get('cards', 5),
                        assets=self.store.assets,
                        progress=lambda i: progress(50 + i * 8, f'카드 {i+1} 관련 이미지 찾는 중'))
                if cancel.is_set():
                    raise InterruptedError('초안 생성을 중단했습니다.')
                project.update(scenes=scenes, caption=caption, revision=project['revision']+1, state='EDITABLE',
                               approved_hash='', render=None, usage=usage, updated_at=now())
                if job.get('provider'):
                    project['last_generation'] = {'provider': job['provider'], 'model': job['model']}
                self.store.put('projects', project)
            elif job['kind'] == 'render':
                directory = self.store.media / project['id'] / job['id']
                result = render(project, directory, self.vault, settings, cancel, progress, lambda p: self.process(job['id'], p), assets=self.store.assets)
                if cancel.is_set():
                    raise InterruptedError('렌더링을 중단했습니다.')
                project.update(render=result, state='REVIEW_READY', approved_hash='', updated_at=now())
                self.store.put('projects', project)
            else:
                self.publish(job, project, cancel, progress)
            self.update(job, status='DONE', progress=100, message='게시 완료' if job['kind'] == 'publish' else '작업 완료')
        except BaseException as exc:
            interrupted = isinstance(exc, InterruptedError) or cancel.is_set()
            if job['kind'] == 'publish':
                pub = self.store.get('publications', job['publication_id'])
                # No automatic retries across a potentially accepted remote POST.
                if pub['status'] != 'PUBLISHED':
                    safe_failure = pub.get('stage') in ('LOCAL', 'PROCESSING_ERROR')
                    pub.update(status='FAILED' if safe_failure else 'NEEDS_RECONCILIATION', updated_at=now())
                    self.store.put('publications', pub)
            else:
                project.update(state='EDITABLE' if job['kind'] == 'generate' else ('INTERRUPTED' if interrupted else 'FAILED'),
                               approved_hash='', updated_at=now())
                self.store.put('projects', project)
            message = str(exc) if isinstance(exc, (ValueError, InterruptedError)) else '작업 실패. 네트워크와 서비스 연결 상태를 확인하세요.'
            self.update(job, status='INTERRUPTED' if interrupted else 'FAILED', message=message[:500])

    def publish(self, job, project, cancel, progress):
        pub = self.store.get('publications', job['publication_id'])
        settings = self.store.settings()
        meta = Meta(self.vault, settings, self.store.get('accounts', project['account_id']))
        directory = self.store.media / project['id'] / project['render']['folder']
        path = directory / 'video.mp4'
        if not path.exists() or path.stat().st_size > 1_000_000_000:
            raise ValueError('영상 파일이 없거나 크기 한도를 넘습니다.')
        if not project['render'].get('sha256') or file_hash(path) != project['render']['sha256']:
            raise ValueError('렌더링 결과와 현재 영상 파일이 다릅니다. 다시 렌더링하고 승인하세요.')
        progress(10, '승인한 영상을 임시 저장소에 업로드 중')
        pub['s3_key'] = f'instagram-studio/{pub["id"]}/video.mp4'
        self.store.put('publications', pub)
        url = upload_video(self.vault, settings, path, pub['s3_key'])
        if cancel.is_set():
            raise InterruptedError('게시 전송을 중단했습니다.')
        progress(35, 'Instagram 미디어 준비 요청 중')
        pub.update(stage='CONTAINER_SENT', updated_at=now())
        self.store.put('publications', pub)
        data = meta.create(url, project['caption'])
        pub.update(container_id=data['id'], status='PROCESSING', updated_at=now())
        self.store.put('publications', pub)
        for i in range(60):
            if cancel.wait(5):
                raise InterruptedError('진행 중 게시 요청은 외부에서 완료될 수 있습니다. 결과를 확인하세요.')
            state = meta.status(pub['container_id']).get('status_code')
            if state == 'FINISHED':
                break
            if state in ('ERROR', 'EXPIRED'):
                pub.update(stage='PROCESSING_ERROR', status='FAILED', updated_at=now())
                self.store.put('publications', pub)
                raise ValueError('Instagram 영상 처리 실패. 작업 이력에서 원격 상태를 확인하세요.')
            progress(min(78, 40+i), 'Instagram에서 영상 처리 중')
        else:
            raise ValueError('Instagram 처리 대기 시간이 지났습니다. 기존 요청 결과를 확인하세요.')
        if cancel.is_set():
            raise InterruptedError('게시 전송을 중단했습니다.')
        # Record intent before calling publish; timeout may hide a successful post.
        pub.update(status='PUBLISHING', stage='PUBLISH_SENT', updated_at=now())
        self.store.put('publications', pub)
        progress(85, '게시 요청 중')
        result = meta.publish(pub['container_id'])
        pub.update(status='PUBLISHED', media_id=result['id'], updated_at=now())
        self.store.put('publications', pub)
        project.update(state='PUBLISHED', updated_at=now())
        self.store.put('projects', project)
        try:
            pub['permalink'] = meta.media(pub['media_id']).get('permalink', '')
            self.store.put('publications', pub)
        except (ValueError, httpx.HTTPError):
            pass

    def cancel(self, job_id):
        event = self.events.get(job_id)
        if event:
            event.set()

    def request_stop(self):
        with self.lock:
            self.stopping = True
            for event in self.events.values():
                event.set()
            for p in list(self.processes.values()):
                if p.poll() is None:
                    p.terminate()

    def shutdown(self):
        with self.lock:
            if self.shutdown_started:
                return
            self.shutdown_started = True
        self.request_stop()
        # HTTP calls can be in flight; checkpoint before process exit.
        import time
        deadline = time.monotonic() + 5
        for t in self.threads.values():
            t.join(max(0, deadline-time.monotonic()))
        with self.lock:
            for p in list(self.processes.values()):
                if p.poll() is None:
                    p.kill()
        self.store.recover()
