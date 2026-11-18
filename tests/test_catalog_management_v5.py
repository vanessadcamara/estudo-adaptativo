"""Regras de persistência e gerenciamento: alterações reais, sem perda do histórico."""
from pathlib import Path


def test_catalog_edit_archive_restore_and_persistent_queue(client):
    subject = client.post('/api/subjects', json={'name': 'Conhecimentos Bancários'}).json()
    second = client.post('/api/subjects', json={'name': 'Português'}).json()
    topic = client.post('/api/topics', json={
        'subject_id': subject['id'], 'title': 'Sistema Financeiro', 'code': 'A1', 'importance': 3
    }).json()
    question = client.post('/api/questions', json={
        'subject_id': subject['id'], 'topic_id': topic['id'], 'url': 'https://example.com/questao/12'
    }).json()
    assert len(client.get('/api/queue').json()['topics']) == 1
    assert len(client.get('/api/queue').json()['questions']) == 1

    edit_subject = client.patch(f"/api/subjects/{subject['id']}", json={'name': 'Bancários'}).json()
    assert edit_subject['name'] == 'Bancários'
    edit_topic = client.patch(f"/api/topics/{topic['id']}",json={
        'subject_id': second['id'], 'title': 'Sistema Monetário', 'code': 'P1', 'importance': 5
    })
    assert edit_topic.status_code == 200
    assert edit_topic.json()['importance'] == 5
    assert client.get('/api/questions').json()[0]['subject_id'] == second['id']
    edit_question = client.patch(f"/api/questions/{question['id']}",json={
        'subject_id': second['id'], 'topic_id': topic['id'],
        'url': 'https://example.com/questao/13', 'statement': 'Uma questão de revisão.'
    })
    assert edit_question.status_code == 200
    assert edit_question.json()['url'].endswith('/13')

    session=client.post('/api/sessions').json()
    assert client.post(f"/api/sessions/{session['id']}/topic-reviews",json={
        'topic_id':topic['id'],'grade':2,'difficulty':3,'critical_gap':True
    }).status_code==201
    assert client.post(f"/api/sessions/{session['id']}/question-attempts",json={
        'question_id':question['id'],'is_correct':False,'confidence':1
    }).status_code==201
    assert client.post(f"/api/sessions/{session['id']}/refresh").status_code==200
    assert client.get('/api/queue').json()['topics'][0]['attempts']==1
    assert client.get('/api/queue').json()['questions'][0]['attempts']==1

    assert client.patch(f"/api/topics/{topic['id']}/archive",json={'archived':True}).status_code==200
    assert client.get('/api/queue').json()['total_topics']==0
    assert client.get('/api/queue').json()['total_questions']==0
    assert client.get('/api/topics?include_archived=true').json()[0]['archived_at'] is not None
    assert client.patch(f"/api/topics/{topic['id']}/archive",json={'archived':False}).status_code==200
    assert client.get('/api/queue').json()['topics'][0]['attempts']==1
    assert client.get('/api/queue').json()['questions'][0]['attempts']==1

    assert client.patch(f"/api/subjects/{second['id']}/archive",json={'archived':True}).status_code==200
    assert client.get('/api/queue').json()['total_topics']==0
    assert client.get('/api/subjects?include_archived=true').json()[1]['archived_at'] is not None
    assert client.patch(f"/api/subjects/{second['id']}/archive",json={'archived':False}).status_code==200
    assert client.get('/api/queue').json()['topics'][0]['attempts']==1
    assert client.get('/api/queue').json()['questions'][0]['attempts']==1


def test_edit_validation_and_duplicate_issues(client):
    subject=client.post('/api/subjects',json={'name':'Matemática'}).json()
    other=client.post('/api/subjects',json={'name':'Inglês'}).json()
    assert client.patch(f"/api/subjects/{other['id']}",json={'name':'Matemática'}).status_code==409
    assert client.patch('/api/subjects/9999',json={'name':'Alguém'}).status_code==404
    assert client.post('/api/subjects',json={'name':'     '}).status_code==422
    topic=client.post('/api/topics',json={'subject_id':subject['id'],'title':'Juros'}).json()
    assert client.patch(f"/api/topics/{topic['id']}",json={
        'subject_id':other['id'],'title':'  ','code':None,'importance':3
    }).status_code==422
    q=client.post('/api/questions',json={'subject_id':subject['id'],'url':'https://example.org/q1'}).json()
    assert client.patch(f"/api/questions/{q['id']}",json={'subject_id':subject['id'],'url':None,'statement':None}).status_code==422
    assert client.patch('/api/questions/99999',json={'subject_id':subject['id'],'url':'https://example.org/q1'}).status_code==404
    assert client.patch('/api/topics/99999/archive',json={'archived':True}).status_code==404


def test_frontend_has_real_dialogs_and_cache_busting(client):
    html=client.get('/').text
    assert 'id="subjectDialog"' in html and 'id="topicDialog"' in html
    assert 'id="questionEditorDialog"' in html and 'id="reviewDialog"' in html
    assert 'id="attemptDialog"' in html and 'id="newSubject"' in html
    assert '/static/app.js?v=5' in html
    assert client.get('/static/app.js').headers.get('cache-control')=='no-store'
    js=client.get('/static/app.js').text
    for route in ['/subjects/', '/topics/', '/questions/', '/topic-reviews','/question-attempts']:
        assert route in js
