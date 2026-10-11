import argparse
import json
import os
import secrets
import signal
import socket
import threading
import time
import urllib.request

import uvicorn

from .api import create_app
from .storage import Store


class Instance:
    """OS advisory lock is released by the OS after a crash."""
    def __init__(self, root):
        self.file = (root / 'instance.lock').open('a+b')
        self.root = root

    def acquire(self):
        try:
            if os.name == 'nt':
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b'0'); self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def release(self):
        (self.root / 'instance.json').unlink(missing_ok=True)
        self.file.close()


BOOTSTRAP = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>콘텐츠 스튜디오</title>
<style>body{background:#f6f8f1;color:#244530;font:15px -apple-system,BlinkMacSystemFont,sans-serif;margin:0;display:grid;place-items:center;height:100vh}main{max-width:460px;padding:40px;border:1px solid #dce6d4;border-radius:15px;background:white}h1{font-size:24px}p{line-height:1.8;color:#819271;font-size:13px}input{border:1px solid #d0dec7;border-radius:7px;padding:12px;width:110px;font:inherit}button{background:#2b5b44;color:white;border:0;border-radius:7px;padding:13px 20px;margin-left:9px;cursor:pointer}label{display:block;margin:24px 0 10px;font-size:12px}#choose{display:none}small{font-size:11px;color:#94a287}</style>
<main><small>YOUR LOCAL CREATIVE SPACE</small><h1>콘텐츠 스튜디오</h1><p id="status">로컬 서비스를 시작하고 있어요.</p><div id="choose"><label for="port">사용할 포트</label><input id="port" type="number" min="1024" max="65535" value="8080"><button onclick="start(Number(document.getElementById('port').value))">스튜디오 열기</button><p>다른 앱을 종료하지 않습니다. 선택한 포트는 다음 실행에 사용합니다.</p></div></main>
<script>async function start(port){let result=await window.pywebview.api.start_server(port);if(result.url){window.location.replace(result.url);return;}if(result.error){document.getElementById('status').textContent=result.error;document.getElementById('choose').style.display='block';}}window.addEventListener('pywebviewready',()=>start(__PORT__));</script></html>'''


class PreviewCloseGuard:
    """Close the active video review before closing the desktop application."""
    def __init__(self):
        self.reviewing = False
        self.quitting = False

    def closing(self, window):
        if self.reviewing and not self.quitting:
            # The closing event runs on the GUI thread. JS evaluation must run
            # elsewhere so WebView can process it without blocking that thread.
            threading.Thread(target=lambda: window.run_js(
                "window.dispatchEvent(new Event('studio-close-video'))"
            ), daemon=True).start()
            return False
        return None


def main():
    parser = argparse.ArgumentParser(description='Instagram Content Studio')
    parser.add_argument('--browser', action='store_true', help='개발용 브라우저 모드: Ctrl+C 또는 화면의 종료 버튼으로 종료')
    parser.add_argument('--port', type=int, default=None)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    store = Store()
    lock = Instance(store.root)
    if not lock.acquire():
        metadata = store.root / 'instance.json'
        if metadata.exists():
            data = json.loads(metadata.read_text())
            try:
                req = urllib.request.Request(data['base'] + '/api/activate', data=b'{}', headers={
                    'Content-Type': 'application/json', 'X-Studio-Token': data['token'],
                    'Cookie': 'studio_session=' + data['token']}, method='POST')
                urllib.request.urlopen(req, timeout=2)
                print('기존 스튜디오 창을 활성화했습니다.')
            except Exception:
                print('기존 스튜디오가 준비 중이거나 종료 중입니다. 잠시 후 다시 실행하세요.')
        else:
            print('기존 인스턴스가 시작 중입니다.')
        return
    server, sock, thread, window = None, None, None, None
    startup_lock = threading.Lock()
    preview_close = PreviewCloseGuard()

    def stop():
        preview_close.quitting = True
        if server:
            server.config.app.state.jobs.request_stop()
            server.should_exit = True
        if window:
            window.destroy()

    def activate():
        if window:
            window.restore(); window.show()
        elif not args.no_open and (store.root / 'instance.json').exists():
            import webbrowser
            webbrowser.open(json.loads((store.root / 'instance.json').read_text())['url'])

    def serve(port):
        nonlocal server, sock, thread
        with startup_lock:
            if server:
                return None
            if not isinstance(port, int) or not 1 <= port <= 65535:
                return '포트는 1~65535 범위의 숫자여야 합니다.'
            attempt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if os.name == 'nt':
                attempt.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                attempt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                attempt.bind(('127.0.0.1', port)); attempt.listen(128)
            except OSError as exc:
                attempt.close()
                return f'포트 {port}을 사용할 수 없습니다 (오류 {exc.errno}). 다른 앱이 사용 중이거나 권한이 부족합니다. 대체 포트를 선택하세요.'
            sock = attempt
            token = secrets.token_urlsafe(32)
            app = create_app(store=store, session_token=token, stop_callback=stop, activate_callback=activate, review_callback=lambda reviewing: setattr(preview_close, 'reviewing', reviewing))
            server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning', access_log=False, timeout_graceful_shutdown=3))
            base = f'http://127.0.0.1:{port}'
            url = base + '/#session=' + token
            thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
            thread.start()
            for _ in range(100):
                if server.started:
                    break
                if not thread.is_alive():
                    sock.close();server=None
                    return '서비스 시작에 실패했습니다.'
                time.sleep(.05)
            if not server.started:
                server.should_exit=True
                return '서비스 준비 시간이 초과되었습니다.'
            saved=store.settings();saved['port']=port;store.save_settings(saved)
            metadata=store.root/'instance.json'
            metadata.write_text(json.dumps({'base':base,'url':url,'token':token}))
            if os.name!='nt':metadata.chmod(0o600)
            return url

    class Bridge:
        def set_video_review(self, reviewing):
            preview_close.reviewing = reviewing is True

        def start_server(self, port):
            result=serve(port)
            if result and result.startswith('http://'):
                return {'url':result}
            return {'error':result or '이미 실행 중입니다.'}

    try:
        initial_port=args.port if args.port is not None else store.settings().get('port',80)
        signal.signal(signal.SIGINT, lambda *_:stop())
        signal.signal(signal.SIGTERM, lambda *_:stop())
        if args.browser:
            result=serve(initial_port)
            if not result or not result.startswith('http://'):
                print(result or '서비스 시작 실패');return
            print('개발용 브라우저 모드. 탭 닫기는 서버를 종료하지 않습니다.',flush=True)
            print('실행 주소: '+result,flush=True)
            if not args.no_open:
                import webbrowser
                webbrowser.open(result)
            while thread.is_alive():thread.join(.2)
        else:
            import webview
            webview.settings['ALLOW_DOWNLOADS'] = True
            bridge = Bridge()
            window=webview.create_window('콘텐츠 스튜디오',html=BOOTSTRAP.replace('__PORT__',str(initial_port)),js_api=bridge,width=1360,height=950,min_size=(850,620))
            window.events.closing += preview_close.closing
            window.events.closed += lambda:setattr(server,'should_exit',True) if server else None
            if os.name == 'nt':
                try:
                    webview.start(gui='edgechromium', private_mode=True)
                except Exception:
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(0, 'Microsoft Edge WebView2 런타임을 확인하세요. 설치 후 스튜디오를 다시 실행하세요.', '콘텐츠 스튜디오 시작 오류', 0)
            else:
                webview.start(private_mode=True)
    finally:
        if server:
            server.config.app.state.jobs.request_stop()
            server.should_exit=True
            if thread:thread.join(8)
            # Lifespan cleanup may not finish after a pending HTTP request.
            app=server.config.app
            app.state.jobs.shutdown()
        if sock:sock.close()
        lock.release()


if __name__=='__main__':
    main()
