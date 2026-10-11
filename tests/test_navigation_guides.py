import sqlite3,json
from test_studio import client
from studio.storage import Store


def test_guides_all_readable_in_app(client):
    listing=client.get('/api/manuals');assert listing.status_code==200
    assert len(listing.json())==5
    for item in listing.json():
        response=client.get('/api/manuals/'+item['id'])
        assert response.status_code==200
        assert response.json()['title']==item['title']
        assert len(response.json()['markdown'])>100
    assert client.get('/api/manuals/not-found.md').status_code==404
    client.cookies.clear()
    assert client.get('/api/manuals/USER_MANUAL.md').status_code==401


def test_sidebar_and_categories_persist(client):
    assert client.get('/api/settings').json()['nav_collapsed'] is False
    assert client.put('/api/appearance',json={'nav_collapsed':True,'nav_groups':{'api':False}}).status_code==200
    client.put('/api/appearance',json={'nav_groups':{'content':False}})
    fresh=Store(client.app.state.store.root)
    assert fresh.settings()['nav_collapsed'] is True
    assert fresh.settings()['nav_groups']=={'api':False,'content':False}
    client.put('/api/appearance',json={'theme':'light'})
    client.put('/api/settings',json={'model':'gpt-4.1-mini'})
    settings=client.get('/api/settings').json()
    assert settings['theme']=='light' and settings['nav_collapsed'] is True
    assert settings['nav_groups']=={'api':False,'content':False}
    client.put('/api/appearance',json={'nav_collapsed':False,'nav_groups':{'api':True}})
    assert client.get('/api/settings').json()['nav_groups']=={'api':True,'content':False}


def test_appearance_validation_and_csrf(client):
    assert client.put('/api/appearance',json={}).status_code==400
    assert client.put('/api/appearance',json={'nav_groups':{'unknown':False}}).status_code==422
    assert client.put('/api/appearance',json={'nav_collapsed':True},headers={'x-studio-token':''}).status_code==403
