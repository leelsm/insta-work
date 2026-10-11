"""Fetch a selected public news article and make a short local, editable summary."""
from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

import httpx

from .adapters import RemoteError


class _ArticleText(HTMLParser):
    SKIP = {'script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'noscript', 'svg'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.article = 0
        self.stack = []
        self.chunks = []
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            name = (attrs.get('property') or attrs.get('name') or '').lower()
            if name in ('og:description', 'description') and attrs.get('content'):
                self.meta.setdefault(name, attrs['content'])
        if tag in self.SKIP:
            self.skip += 1
        if tag in ('article', 'main'):
            self.article += 1
        cls = (attrs.get('class', '') + ' ' + attrs.get('id', '')).lower()
        is_body = tag in ('div', 'section') and any(x in cls for x in (
            'article_body', 'article-body', 'newsct_article', 'article_view', 'articleview', 'article_txt', 'article-content'
        ))
        self.stack.append((tag, is_body))
        if is_body:
            self.article += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in ('article', 'main') and self.article:
            self.article -= 1
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                removed = self.stack[index:]
                self.stack = self.stack[:index]
                self.article = max(0, self.article - sum(1 for _, is_body in removed if is_body))
                break

    def handle_data(self, data):
        value = re.sub(r'\s+', ' ', data).strip()
        if value and not self.skip and (self.article or len(value) > 80):
            self.chunks.append(value)


def _public_article_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError()
        host = parsed.hostname.encode('idna').decode('ascii')
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError()
        return urlunsplit(('https', host, parsed.path or '/', parsed.query, ''))
    except (ValueError, UnicodeError, OSError, socket.gaierror):
        raise ValueError('안전하게 확인할 수 있는 HTTPS 기사 주소가 아닙니다. 검색 결과의 원문 링크를 확인하세요.') from None


def _summarize(text, title):
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) < 100:
        raise RemoteError('기사 본문을 충분히 읽지 못했습니다. 원문이 로그인·구독을 요구하거나 페이지 구조가 다를 수 있어요. 확인한 요약을 직접 입력할 수 있습니다.')
    # Sentence selection keeps source wording and numbers intact; the user can edit it.
    sentences = [s.strip() for s in re.split(r'(?<=[.!?。！？])\s+|(?<=다\.)\s+|(?<=요\.)\s+', text) if len(s.strip()) >= 18]
    if not sentences:
        sentences = [text[i:i+280] for i in range(0, min(len(text), 1400), 280)]
    terms = [w for w in re.findall(r'[가-힣A-Za-z0-9]{2,}', title) if len(w) > 1]
    scored = []
    for index, sentence in enumerate(sentences):
        score = sum(2 for word in terms if word in sentence) + (1 if index < 3 else 0)
        score += 1 if re.search(r'\d|밝혔|발표|따르|계획|결정|확인|조사|원인|결과|대비|증가|감소', sentence) else 0
        scored.append((score, index, sentence))
    picked = sorted(sorted(scored, key=lambda row: (-row[0], row[1]))[:8], key=lambda row: row[1])
    summary = '\n'.join(row[2] for row in picked)
    return summary[:4000]


def article_summary(url, title):
    safe_url = _public_article_url(url)
    try:
        with httpx.Client(timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=False,
                          headers={'User-Agent': 'Mozilla/5.0 (compatible; ContentStudio/1.0)', 'Accept': 'text/html'}) as c:
            response = c.get(safe_url)
        if response.is_redirect:
            raise RemoteError('기사 사이트가 다른 주소로 이동했습니다. 원문을 확인한 뒤 요약을 직접 입력해 주세요.')
        if not response.is_success:
            raise RemoteError(f'기사 본문을 가져오지 못했습니다 (HTTP {response.status_code}). 원문을 확인한 뒤 요약을 직접 입력해 주세요.')
        if len(response.content) > 3_000_000:
            raise RemoteError('기사 페이지가 너무 커서 본문을 읽지 않았습니다. 원문을 확인한 뒤 요약을 직접 입력해 주세요.')
        if 'html' not in response.headers.get('content-type', '').lower():
            raise RemoteError('원문이 HTML 기사 페이지가 아닙니다. 확인한 요약을 직접 입력해 주세요.')
        parser = _ArticleText()
        parser.feed(response.text)
        body = ' '.join(parser.chunks)
        if len(body) < 100:
            body = parser.meta.get('og:description') or parser.meta.get('description') or ''
        return {'text': _summarize(body, title), 'url': safe_url, 'method': 'local_extractive'}
    except httpx.HTTPError:
        raise RemoteError('기사 사이트에 연결할 수 없습니다. 원문을 확인한 뒤 요약을 직접 입력해 주세요.') from None
