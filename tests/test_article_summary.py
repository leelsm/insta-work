import pytest

from studio.article_summary import _summarize, article_summary
from studio.adapters import RemoteError, json_response


def test_article_summary_extracts_and_returns_editable_summary(monkeypatch):
    class Response:
        is_redirect = False
        is_success = True
        content = b'x' * 500
        text = '<html><body><nav>메뉴와 광고</nav><article><h1>제목</h1><p>' + (
            '정부가 오늘 새로운 지원 계획을 발표했다. ' * 20
        ) + '</p></article></body></html>'
        headers = {'content-type': 'text/html; charset=utf-8'}

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url): return Response()

    monkeypatch.setattr('studio.article_summary._public_article_url', lambda url: url)
    monkeypatch.setattr('studio.article_summary.httpx.Client', Client)
    result = article_summary('https://news.example/story', '정부 지원 계획')
    assert result['method'] == 'local_extractive'
    assert '정부가 오늘 새로운 지원 계획을 발표했다.' in result['text']
    assert '메뉴와 광고' not in result['text']


def test_summary_requires_sufficient_article_text():
    with pytest.raises(RemoteError, match='충분히 읽지 못했습니다'):
        _summarize('본문이 너무 짧음', '제목')


class FakeResponse:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self.is_success = 200 <= status < 300
        self._payload = payload
        self.headers = headers or {}
    def json(self): return self._payload


def test_openai_quota_429_explains_billing_action_without_echoing_body():
    with pytest.raises(RemoteError, match='Billing과 Limits'):
        json_response(FakeResponse(429, {'error': {'code': 'insufficient_quota', 'type': 'insufficient_quota', 'message': 'secret'}}), 'OpenAI')


def test_openai_empty_prepaid_balance_explains_non_retryable_429():
    with pytest.raises(RemoteError, match='선불 잔액이 소진') as err:
        json_response(FakeResponse(429, {'error': {'code': 'credit_balance_exhausted'}}), 'OpenAI')
    assert '재시도해도 생성되지 않습니다' in str(err.value)


def test_openai_rate_limit_429_includes_retry_after():
    with pytest.raises(RemoteError, match='약 12초 후'):
        json_response(FakeResponse(429, {'error': {'code': 'rate_limit_exceeded'}}, {'retry-after': '12'}), 'OpenAI')
