"""Read title/link metadata from Naver's public publisher rankings, never article bodies."""
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit, urlunsplit
import re

from .adapters import client, RemoteError

KST = timezone(timedelta(hours=9))
RANKING_URL = 'https://news.naver.com/main/ranking/popularDay.naver'
# Keep the daily digest focused and balanced across five widely read outlets.
FEATURED_PUBLISHERS = ('연합뉴스', 'KBS', '조선일보', '중앙일보', '한겨레')


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find(self, css):
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if css in child.attrs.get('class', '').split(): result.append(child)
                result.extend(child.find(css))
        return result

    def text(self):
        return ''.join(child.text() if isinstance(child, Node) else child for child in self.children).strip()


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node(); self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs); self.stack[-1].children.append(node)
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}: self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_ranking(markup):
    tree = Tree(); tree.feed(markup)
    articles, seen = [], set()
    for box in tree.root.find('rankingnews_box'):
        names = box.find('rankingnews_name')
        if not names: continue
        publisher = names[0].text()[:100]
        lists = box.find('rankingnews_list')
        if not publisher or not lists: continue
        for item in lists[0].children:
            if not isinstance(item, Node) or item.tag != 'li': continue
            titles, ranks = item.find('list_title'), item.find('list_ranking_num')
            if not titles or not ranks: continue
            title = titles[0].text()[:300]
            rank = re.match(r'\s*([1-5])(?:\D|$)', ranks[0].text())
            url = urlsplit(titles[0].attrs.get('href', ''))
            if not title or not rank or url.scheme != 'https' or url.netloc != 'n.news.naver.com' or not re.fullmatch(r'/article/\d{3}/\d+', url.path): continue
            safe_url = urlunsplit(('https', 'n.news.naver.com', url.path, '', ''))
            if safe_url in seen: continue
            seen.add(safe_url)
            times = item.find('list_time')
            articles.append({'title': title, 'url': safe_url, 'publisher': publisher,
                             'rank': int(rank.group(1)), 'time_label': times[0].text()[:100] if times else ''})
    if not articles:
        raise RemoteError('인기뉴스 목록을 읽을 수 없습니다. 네이버 페이지 구조 변경 또는 일시적인 접근 제한일 수 있습니다. 잠시 후 다시 시도하세요.')
    info = tree.root.find('rankingnews_info_layer')
    description = info[0].text().replace('닫기', '').strip()[:500] if info else ''
    return articles, description


class RankingNews:
    def __init__(self):
        self.lock, self.cache = Lock(), {}

    def fetch(self, date=None):
        today = datetime.now(KST).date()
        try:
            selected = datetime.strptime(date, '%Y-%m-%d').date() if date else today
        except ValueError:
            raise ValueError('날짜는 YYYY-MM-DD 형식으로 입력하세요.') from None
        if selected > today or selected < today-timedelta(days=90):
            raise ValueError('인기뉴스 날짜는 오늘부터 최근 90일 이내로 선택하세요.')
        day = selected.isoformat()
        with self.lock:
            cached = self.cache.get(day)
            if cached and monotonic()-cached[0] < 600: return cached[1]
            try:
                with client() as c:
                    with c.stream('GET', RANKING_URL, params={'date': selected.strftime('%Y%m%d')}) as response:
                        if response.status_code != 200:
                            raise RemoteError(f'인기뉴스 조회 실패 (HTTP {response.status_code}). 잠시 후 다시 시도하세요.')
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data) > 3_000_000: raise RemoteError('인기뉴스 페이지가 예상 크기를 초과했습니다.')
                        encoding = response.encoding or 'euc-kr'
                        markup = bytes(data).decode(encoding, errors='replace')
                articles, description = parse_ranking(markup)
                available = {item['publisher'] for item in articles}
                selected_publishers = [name for name in FEATURED_PUBLISHERS if name in available]
                # Naver occasionally labels an outlet differently or omits one.
                # Fill remaining slots from the ranking page while still capping
                # the digest at five publishers.
                selected_publishers.extend(name for name in dict.fromkeys(a['publisher'] for a in articles)
                                            if name not in selected_publishers and len(selected_publishers) < 5)
                articles = [item for item in articles if item['publisher'] in selected_publishers]
            except RemoteError:
                raise
            except Exception:
                raise RemoteError('인기뉴스 서버에 연결할 수 없습니다. 인터넷 연결을 확인하고 다시 시도하세요.') from None
            result = {'date': day, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                      'source_url': RANKING_URL+'?date='+selected.strftime('%Y%m%d'),
                      'description': description, 'publishers': selected_publishers,
                      'items': sorted(articles, key=lambda a:(a['rank'], selected_publishers.index(a['publisher'])))}
            if len(self.cache) >= 8: self.cache.pop(next(iter(self.cache)))
            self.cache[day] = (monotonic(), result)
            return result
