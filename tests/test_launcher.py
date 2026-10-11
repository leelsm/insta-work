import threading

from studio.launcher import PreviewCloseGuard


def test_window_close_dismisses_review_without_closing_application():
    guard = PreviewCloseGuard()
    guard.reviewing = True
    dispatched = threading.Event()
    gui_thread = threading.get_ident()

    class Window:
        def run_js(self, script):
            # WebView's GUI thread must stay free to execute the script.
            assert threading.get_ident() != gui_thread
            assert script == "window.dispatchEvent(new Event('studio-close-video'))"
            dispatched.set()

    window = Window()
    assert guard.closing(window) is False
    assert dispatched.wait(2)
    guard.reviewing = False
    assert guard.closing(window) is None


def test_explicit_shutdown_can_close_window_during_review():
    guard = PreviewCloseGuard()
    guard.reviewing = True
    guard.quitting = True

    class Window:
        def run_js(self, script):
            raise AssertionError('Explicit shutdown must not dismiss the review')

    assert guard.closing(Window()) is None


def test_review_status_uses_authenticated_local_api(tmp_path):
    from fastapi.testclient import TestClient
    from studio.api import create_app
    from studio.storage import Store
    from test_studio import MemoryVault
    guard = PreviewCloseGuard()
    app = create_app(store=Store(tmp_path), vault=MemoryVault(), session_token='review-test',
                     review_callback=lambda value: setattr(guard, 'reviewing', value))
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/video-review', json={'reviewing': True}).status_code == 401
        assert not guard.reviewing
        client.headers['X-Studio-Token'] = 'review-test'
        assert client.post('/api/session', json={'token':'review-test'}).status_code == 200
        assert client.post('/api/video-review', json={'reviewing':True}).status_code == 200
        assert guard.reviewing
        assert client.post('/api/video-review', json={'reviewing':'false'}).status_code == 422
        assert guard.reviewing
        assert client.post('/api/video-review', json={'reviewing':False}).status_code == 200
        assert not guard.reviewing
