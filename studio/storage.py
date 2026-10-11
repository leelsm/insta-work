import json
import os
import sqlite3
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import keyring
from platformdirs import user_data_path


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return uuid.uuid4().hex


class Store:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ.get('STUDIO_DATA_DIR') or user_data_path('InstagramContentStudio', appauthor=False))
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.media = self.root / 'media'
        self.media.mkdir(exist_ok=True)
        self.assets = self.root / 'assets'
        self.assets.mkdir(exist_ok=True)
        self.db = self.root / 'studio.sqlite3'
        self.lock = threading.RLock()
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS active_job ON jobs(project_id) WHERE status='RUNNING';
            CREATE TABLE IF NOT EXISTS publications (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision INTEGER NOT NULL, account_id TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(project_id, revision, account_id));
            ''')

    @contextmanager
    def connect(self):
        with self.lock:
            c = sqlite3.connect(self.db, timeout=15)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise
            finally:
                c.close()

    def settings(self):
        with self.connect() as c:
            row = c.execute('SELECT data FROM settings WHERE id=1').fetchone()
        return json.loads(row['data']) if row else {}

    def save_settings(self, data):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (json.dumps(data, ensure_ascii=False),))

    def list(self, table):
        assert table in ('projects', 'accounts', 'jobs', 'publications')
        with self.connect() as c:
            return [json.loads(r['data']) for r in c.execute(f'SELECT data FROM {table} ORDER BY rowid DESC').fetchall()]

    def get(self, table, id):
        assert table in ('projects', 'accounts', 'jobs', 'publications')
        with self.connect() as c:
            row = c.execute(f'SELECT data FROM {table} WHERE id=?', (id,)).fetchone()
        if row is None:
            raise KeyError('항목을 찾을 수 없습니다.')
        return json.loads(row['data'])

    def put(self, table, data):
        assert table in ('projects', 'accounts', 'jobs', 'publications')
        encoded = json.dumps(data, ensure_ascii=False)
        with self.connect() as c:
            if table == 'jobs':
                c.execute('INSERT INTO jobs VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,data=excluded.data',
                          (data['id'], data['project_id'], data['kind'], data['status'], encoded))
            elif table == 'publications':
                c.execute('INSERT INTO publications VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                          (data['id'], data['project_id'], data['revision'], data['account_id'], encoded))
            else:
                c.execute(f'INSERT OR REPLACE INTO {table} VALUES(?,?)', (data['id'], encoded))

    def delete_project(self, project_id):
        with self.connect() as c:
            result = c.execute('DELETE FROM projects WHERE id=?', (project_id,))
            if result.rowcount == 0:
                raise KeyError('항목을 찾을 수 없습니다.')

    def active(self, project_id):
        with self.connect() as c:
            return c.execute("SELECT 1 FROM jobs WHERE project_id=? AND status='RUNNING'", (project_id,)).fetchone() is not None

    def recover(self):
        for j in self.list('jobs'):
            if j['status'] == 'RUNNING':
                j.update(status='INTERRUPTED', message='앱 종료로 중단되었습니다. 게시 작업은 결과를 먼저 확인하세요.', updated_at=now())
                self.put('jobs', j)
                p = self.get('projects', j['project_id'])
                if j['kind'] != 'publish':
                    p['state'] = 'EDITABLE' if j['kind'] == 'generate' else 'INTERRUPTED'
                    self.put('projects', p)
        for pub in self.list('publications'):
            if pub['status'] not in ('PUBLISHED', 'FAILED', 'NEEDS_RECONCILIATION'):
                pub.update(status='NEEDS_RECONCILIATION', updated_at=now())
                self.put('publications', pub)


SECRET_NAMES = {'naver_id', 'naver_secret', 'openai_key', 'anthropic_key', 'compatible_key', 'freellmapi_key', 'aws_access', 'aws_secret', 'aws_session'}


class Vault:
    service = 'InstagramContentStudio'

    def __init__(self, root=None):
        self.path = Path(root or user_data_path('InstagramContentStudio', appauthor=False)) / 'credential-status.json'

    def get(self, name):
        try:
            value = keyring.get_password(self.service, name)
        except Exception:
            raise ValueError('OS 보안 저장소에 접근할 수 없습니다. Keychain 또는 Credential Manager를 확인하세요.') from None
        return value or ''

    def set(self, name, value):
        try:
            if value:
                keyring.set_password(self.service, name, value.strip())
            elif keyring.get_password(self.service, name):
                keyring.delete_password(self.service, name)
            flags = self.flags(); flags[name] = bool(value.strip())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(flags)); self.path.chmod(0o600)
        except Exception:
            raise ValueError('비밀값을 OS 보안 저장소에 저장하지 못했습니다.') from None

    def flags(self):
        # Status is metadata: opening the UI must never request secret access.
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            return {name: bool(saved.get(name, False)) for name in sorted(SECRET_NAMES)}
        result = {name: False for name in sorted(SECRET_NAMES)}
        if sys.platform == 'darwin':
            for name in result:
                try:
                    result[name] = subprocess.run(['security', 'find-generic-password', '-s', self.service, '-a', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2).returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    pass
        return result
