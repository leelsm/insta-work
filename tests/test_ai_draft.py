import pytest
from studio.adapters import RemoteError, generate

class Vault:
    def get(self, key): return 'test-key'


def project():
    return {'title':'지속가능한 에너지 정책', 'tone':'쉽고 중립적인 설명', 'sources':[
        {'title':'네이버 뉴스 검색 요약','text':'정부가 오늘 태양광 보급 계획을 발표했다. 설치 목표는 기존 계획보다 늘었다.',
         'url':'https://news.example/article/42','rights':''}]}


def cards(count=5, source_ids=None):
    return {'scenes':[{'title':f'핵심 {i+1}','body':f'제공 자료의 핵심 {i+1}입니다.',
                       'narration':f'제공 자료를 바탕으로 한 자막 {i+1}입니다.',
                       'source_ids':source_ids if source_ids is not None else [0],
                       'image_search_query':f'related news topic {i+1}'} for i in range(count)],
            'caption':'정부가 태양광 보급 계획을 발표했습니다. https://news.example/article/42'}


def test_generate_uses_provided_summary_and_returns_exact_card_count(monkeypatch):
    captured={}
    def fake(*args):
        captured['prompt']=args[2];captured['content']=args[3];captured['schema']=args[4]
        return cards(),{'input_tokens':5}
    monkeypatch.setattr('studio.llm.generate_json',fake)
    scenes,caption,usage=generate(Vault(),{},project(),5)
    assert len(scenes)==5 and scenes[0]['source_ids']==[0]
    assert scenes[0]['title']==project()['title']
    assert '기사를 읽은 척하지 마세요' in captured['prompt']
    assert '사건의 세부사항은 추정하지 마세요' in captured['prompt']
    assert '기존 계획보다 늘었다' in captured['content'][0]['text']
    assert captured['schema']['properties']['scenes']['minItems']==5
    assert captured['schema']['properties']['scenes']['maxItems']==5
    assert 'image_search_query' in captured['schema']['properties']['scenes']['items']['properties']
    assert '자막 대본' in captured['prompt']
    assert 'news.example/article/42' in caption and usage=={'input_tokens':5}


def test_generate_rejects_wrong_card_count_and_keeps_no_partial_output(monkeypatch):
    monkeypatch.setattr('studio.llm.generate_json',lambda *args:(cards(4),{}))
    with pytest.raises(RemoteError,match='기존 편집 내용은 유지'):
        generate(Vault(),{},project(),5)


def test_generate_rejects_unlinked_claims(monkeypatch):
    monkeypatch.setattr('studio.llm.generate_json',lambda *args:(cards(source_ids=[]),{}))
    with pytest.raises(RemoteError,match='출처 연결'):
        generate(Vault(),{},project(),5)


def test_generate_rejects_no_source_before_provider_request(monkeypatch):
    monkeypatch.setattr('studio.llm.generate_json',lambda *args:pytest.fail('provider must not be called'))
    with pytest.raises(ValueError,match='자료를 먼저 추가'):
        generate(Vault(),{}, {**project(),'sources':[]},5)


def test_generated_image_credits_are_added_to_caption(monkeypatch, tmp_path):
    monkeypatch.setattr('studio.llm.generate_json', lambda *args:(cards(),{}))
    def attach(scenes, root, progress=None):
        for scene in scenes:
            scene.update(image_asset_id='a'*32,image_title='News image',image_author='Photo Author',
                         image_license='CC BY 4.0',image_page_url='https://commons.wikimedia.org/wiki/File:News.jpg',
                         image_license_url='https://creativecommons.org/licenses/by/4.0/')
        return scenes
    monkeypatch.setattr('studio.images.attach_first_results',attach)
    scenes,caption,_=generate(Vault(),{},project(),5,assets=tmp_path)
    assert all(scene['image_asset_id']=='a'*32 for scene in scenes)
    assert '사진 출처 (카드별)' in caption
    assert 'creativecommons.org/licenses/by/4.0' in caption


def test_local_only_generation_never_searches_external_images(monkeypatch, tmp_path):
    monkeypatch.setattr('studio.llm.generate_json', lambda *args:(cards(),{}))
    monkeypatch.setattr('studio.images.attach_first_results',lambda *args,**kwargs:pytest.fail('external search blocked'))
    scenes,_,_=generate(Vault(),{'privacy_mode':'local_only'},project(),5,assets=tmp_path)
    assert all(not scene['image_asset_id'] for scene in scenes)
