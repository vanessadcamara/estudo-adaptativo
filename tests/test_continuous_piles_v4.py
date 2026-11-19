"""Pilhas contínuas, gerenciamento de questões e sugestões conservadoras."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from app.db import get_db
from app.engine import build_queue
from app.models import QuestionAttempt, Question


def test_full_queue_never_limits_by_day_or_session(client):
    subject = client.post('/api/subjects', json={'name': 'Economia'}).json()
    for i in range(12):
        assert client.post('/api/topics', json={'subject_id': subject['id'], 'title': f'Assunto {i}'}).status_code == 201
    for i in range(8):
        assert client.post('/api/questions', json={'subject_id': subject['id'], 'url': f'https://example.com/q{i}'}).status_code == 201
    full = client.get('/api/queue').json()
    assert len(full['topics']) == 12 and len(full['questions']) == 8
    assert full['topic_minutes'] is None and full['question_minutes'] is None
    session = client.post('/api/sessions').json()
    first = full['topics'][0]['id']
    assert client.post(f"/api/sessions/{session['id']}/topic-reviews", json={'topic_id': first, 'grade': 1}).status_code == 201
    assert len(client.get('/api/queue').json()['topics']) == 12
    assert len(client.get(f"/api/sessions/{session['id']}/queue").json()['topics']) == 11
    assert client.post(f"/api/sessions/{session['id']}/refresh").status_code == 200
    assert len(client.get('/api/queue').json()['topics']) == 12


def test_question_archive_restores_without_erasing_history(client):
    subject=client.post('/api/subjects',json={'name':'Português'}).json()
    question=client.post('/api/questions',json={'subject_id':subject['id'],'url':'https://example.org/prova/crase'}).json()
    sid=client.post('/api/sessions').json()['id']
    assert client.post(f'/api/sessions/{sid}/question-attempts', json={'question_id':question['id'],'is_correct':False,'confidence':1}).status_code==201
    assert client.patch(f"/api/questions/{question['id']}/archive",json={'archived':True}).status_code==200
    assert client.get('/api/queue').json()['questions']==[]
    assert client.get('/api/queue').json()['archived_questions']==1
    assert client.get('/api/questions').json()==[]
    archived=client.get('/api/questions?include_archived=true').json()
    assert len(archived)==1 and archived[0]['archived_at'] is not None
    assert client.patch(f"/api/questions/{question['id']}/archive",json={'archived':False}).status_code==200
    restored=client.get('/api/queue').json()['questions'][0]
    assert restored['errors']==1 and restored['attempts']==1
    assert client.patch('/api/questions/99999/archive',json={'archived':True}).status_code==404
    assert client.patch(f"/api/questions/{question['id']}/archive",json={'archived':'invalid'}).status_code==422


def test_archive_suggestion_only_after_confident_spaced_correct_answers(client):
    subject=client.post('/api/subjects',json={'name':'Matemática Financeira'}).json()
    question=client.post('/api/questions',json={'subject_id':subject['id'],'url':'https://example.org/fin/1'}).json()
    # Uma falha inicial e cinco acertos seguros ao longo de 35 dias.
    for i in range(6):
        session=client.post('/api/sessions').json()
        response=client.post(f"/api/sessions/{session['id']}/question-attempts",json={
            'question_id':question['id'],'is_correct':i>0,'confidence':3,
        })
        assert response.status_code==201
        client.post(f"/api/sessions/{session['id']}/refresh")
    with next(client.app.dependency_overrides[get_db]()) as db:
        attempts=db.scalars(select(QuestionAttempt).where(QuestionAttempt.question_id==question['id']).order_by(QuestionAttempt.id)).all()
        now=datetime.now(timezone.utc)
        for i,attempt in enumerate(attempts):
            attempt.created_at=now-timedelta(days=35-7*i)
        db.commit()
        priority=build_queue(db,now=now)['questions'][0]
    assert priority['archive_suggested'] is True
    assert priority['archive_reason']
    assert priority['attempts']==6
    # Uma nova tentativa insegura desliga a sugestão de arquivar.
    new_session=client.post('/api/sessions').json()
    client.post(f"/api/sessions/{new_session['id']}/question-attempts",json={'question_id':question['id'],'is_correct':True,'confidence':1})
    assert client.get('/api/queue').json()['questions'][0]['archive_suggested'] is False


def test_question_priority_rises_when_overdue_without_removing_others(client):
    subject=client.post('/api/subjects',json={'name':'Informática'}).json()
    for i in range(3):
        client.post('/api/questions',json={'subject_id':subject['id'],'url':f'https://example.org/inf/{i}'})
    session=client.post('/api/sessions').json()
    question=client.get('/api/queue').json()['questions'][0]
    client.post(f"/api/sessions/{session['id']}/question-attempts",json={'question_id':question['id'],'is_correct':False,'confidence':1})
    with next(client.app.dependency_overrides[get_db]()) as db:
        attempt=db.scalars(select(QuestionAttempt).where(QuestionAttempt.question_id==question['id'])).first()
        now=attempt.created_at
        recent=build_queue(db,now=now)
        distant=build_queue(db,now=now+timedelta(days=21))
    candidate=lambda queue:next(q for q in queue['questions'] if q['id']==question['id'])
    assert candidate(distant)['priority']>candidate(recent)['priority']
    assert len(distant['questions'])==3


def test_layout_five_main_tabs_and_two_settings_tabs(client):
    html=client.get('/').text
    assert html.count('data-tab=') == 5
    nav = html.split('<nav class="tabs"', 1)[1].split('</nav>', 1)[0]
    ordered_tabs = ['performance', 'cards', 'errors', 'novel', 'settings']
    positions = [nav.index(f'data-tab="{tab}"') for tab in ordered_tabs]
    assert positions == sorted(positions)
    assert html.count('data-settings-tab=')==2
    assert 'id="subjectForm"' in html and 'id="topicForm"' in html
    assert 'id="managedQuestionsList"' in html
    assert 'id="cardsRefresh"' in html and 'id="errorsRefresh"' in html
    assert 'id="cardsSubject"' in html and 'id="errorsSubject"' in html
    assert 'id="newContentForm"' not in html
    assert 'id="cardsOverview"' not in html and 'id="errorsOverview"' not in html
    assert 'class="hero"' not in html and 'section-mini-icon' not in html
    assert 'cronômetro' not in html.lower() and 'rodada' not in html.lower()
