from datetime import datetime
import httpx
import pytest
from test_studio import client
from studio.ranking import RankingNews, parse_ranking, KST
from studio.adapters import RemoteError

MARKUP='''<div class="rankingnews_info_layer">집계 기준 안내<button>닫기</button></div>
<div class="rankingnews_box"><strong class="rankingnews_name">테스트일보</strong>
<ul class="rankingnews_list"><li><em class="list_ranking_num">1<span>위</span></em>
<a class="list_title" href="https://n.news.naver.com/article/001/123?ntype=RANKING">테스트 &amp; 뉴스</a><span class="list_time">1시간전</span></li>
<li><em class="list_ranking_num">2위</em><a class="list_title" href="https://evil.example/article/001/456">외부 링크</a></li>
<li><em class="list_ranking_num">3위</em><a class="list_title" href="javascript:alert(1)">스크립트</a></li>
<li><em class="list_ranking_num">4위</em><a class="list_title" href="https://n.news.naver.com/article/001/123">중복</a></li>
</ul></div>'''


def test_parse_real_shape_and_safe_links():
    items, description=parse_ranking(MARKUP)
    assert items==[{'title':'테스트 & 뉴스','url':'https://n.news.naver.com/article/001/123','publisher':'테스트일보','rank':1,'time_label':'1시간전'}]
    assert description=='집계 기준 안내'
    with pytest.raises(RemoteError): parse_ranking('<html>page changed</html>')


def test_fetch_cache_and_validation(monkeypatch):
    calls=[]
    def handle(request):
        calls.append(request)
        assert request.url.host=='news.naver.com'
        assert 'X-Naver-Client-Id' not in request.headers
        return httpx.Response(200, content=MARKUP.encode('euc-kr'),headers={'content-type':'text/html; charset=euc-kr'})
    monkeypatch.setattr('studio.ranking.client',lambda:httpx.Client(transport=httpx.MockTransport(handle)))
    ranking=RankingNews();first=ranking.fetch();second=ranking.fetch(first['date'])
    assert first==second and len(calls)==1
    assert first['date']==datetime.now(KST).date().isoformat()
    assert first['items'][0]['publisher']=='테스트일보'
    for date in ['bad','2099-01-01','2000-01-01']:
        with pytest.raises(ValueError): ranking.fetch(date)
    assert len(calls)==1


def test_fetch_limits_digest_to_five_featured_publishers(monkeypatch):
    publishers=['연합뉴스','KBS','조선일보','중앙일보','한겨레','추가일보']
    boxes=[]
    for publisher_index,name in enumerate(publishers):
        rows=''.join(f'<li><em class="list_ranking_num">{rank}위</em><a class="list_title" href="https://n.news.naver.com/article/001/{publisher_index*10+rank}">{name} 기사 {rank}</a></li>' for rank in range(1,6))
        boxes.append(f'<div class="rankingnews_box"><strong class="rankingnews_name">{name}</strong><ul class="rankingnews_list">{rows}</ul></div>')
    markup=''.join(boxes)
    monkeypatch.setattr('studio.ranking.client',lambda:httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=markup))))
    result=RankingNews().fetch()
    assert result['publishers']==['연합뉴스','KBS','조선일보','중앙일보','한겨레']
    assert len(result['items'])==25
    assert {item['rank'] for item in result['items']}=={1,2,3,4,5}


def test_remote_failure_and_size_limit(monkeypatch):
    for response in [httpx.Response(403),httpx.Response(200,content=b'x'*3_000_001)]:
        monkeypatch.setattr('studio.ranking.client',lambda:httpx.Client(transport=httpx.MockTransport(lambda request:response)))
        with pytest.raises(RemoteError): RankingNews().fetch()


def test_api_privacy_and_no_key_required(client,monkeypatch):
    monkeypatch.setattr('studio.ranking.client',lambda:httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,text=MARKUP))))
    assert client.get('/api/news/popular').status_code==200
    assert client.get('/api/news/popular?date=2099-01-01').status_code==400
    settings=client.get('/api/settings').json()
    assert not settings['configured'].get('naver_id',False)
    client.put('/api/settings',json={**settings,'privacy_mode':'local_only'})
    assert client.get('/api/news/popular').status_code==403
