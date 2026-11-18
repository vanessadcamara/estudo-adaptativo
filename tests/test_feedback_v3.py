"""Regras da interface por ciclos e feedback adaptativo sem tempo obrigatório."""
from datetime import datetime, timedelta, timezone

from app.db import get_db
from app.engine import build_queue, question_interval, topic_interval
from app.models import QuestionAttempt, TopicReview, NewContentLog
from sqlalchemy import select


def test_topic_questionnaire_changes_priority_and_remains_in_history(client):
    sub=client.post('/api/subjects',json={'name':'Matemática'}).json()
    topic=client.post('/api/topics',json={'subject_id':sub['id'],'title':'Equações'}).json()
    first=client.get('/api/queue').json()
    assert len(first['topics'])==1
    session=client.post('/api/sessions').json()
    feedback={'topic_id':topic['id'],'grade':3,'difficulty':3,'critical_gap':True,'notes':'Equação quadrática'}
    assert client.post(f"/api/sessions/{session['id']}/topic-reviews",json=feedback).status_code==201
    progress=client.get(f"/api/sessions/{session['id']}/progress").json()
    assert progress['topics']==[topic['id']]
    assert client.get(f"/api/sessions/{session['id']}/queue").json()['topics']==[]
    refreshed=client.post(f"/api/sessions/{session['id']}/refresh").json()
    assert refreshed['refresh_summary']['topics_reviewed']==1
    with next(client.app.dependency_overrides[get_db]()) as db:
        review=db.scalars(select(TopicReview)).first()
        assert review.difficulty==3 and review.critical_gap is True
        assert topic_interval([review])==1
        days_later=build_queue(db,now=review.created_at+timedelta(days=8))
        assert days_later['topics'][0]['due'] is True
    assert client.get('/api/queue').json()['topics'][0]['attempts']==1


def test_question_subject_filter_data_and_confidence(client):
    sub=client.post('/api/subjects',json={'name':'Português'}).json()
    topic=client.post('/api/topics',json={'subject_id':sub['id'],'title':'Crase'}).json()
    question=client.post('/api/questions',json={'url':'https://example.com/crase/1','subject_id':sub['id']}).json()
    assert question['subject_id']==sub['id']
    assert client.get('/api/questions').json()[0]['subject_id']==sub['id']
    session=client.post('/api/sessions').json()
    assert client.post(f"/api/sessions/{session['id']}/question-attempts",json={'question_id':question['id'],'is_correct':True,'confidence':1}).status_code==201
    assert client.get(f"/api/sessions/{session['id']}/progress").json()['questions']==[question['id']]
    assert client.get('/api/queue').json()['questions'][0]['interval_days']==1
    client.post(f"/api/sessions/{session['id']}/refresh")
    wrong_subject=client.post('/api/questions',json={'url':'https://example.com/wrong','topic_id':topic['id'],'subject_id':sub['id']+900})
    assert wrong_subject.status_code==404


def test_no_timer_and_no_penalty_for_skipped_items(client):
    sub=client.post('/api/subjects',json={'name':'Inglês'}).json()
    t1=client.post('/api/topics',json={'subject_id':sub['id'],'title':'Vocabulário'}).json()
    t2=client.post('/api/topics',json={'subject_id':sub['id'],'title':'Interpretação'}).json()
    session=client.post('/api/sessions').json()
    assert client.post(f"/api/sessions/{session['id']}/new-content",json={'topic_id':t1['id']}).status_code==201
    summary=client.post(f"/api/sessions/{session['id']}/refresh").json()['refresh_summary']
    assert summary['new_content_records']==1
    assert summary['new_content_minutes']==0
    before=client.get('/api/queue').json()
    assert before['total_topics']==2
    with next(client.app.dependency_overrides[get_db]()) as db:
        study=db.scalars(select(NewContentLog)).first()
        assert study.minutes is None
        later=build_queue(db,now=study.created_at+timedelta(days=7))
    item=next(t for t in later['topics'] if t['id']==t1['id'])
    assert item['due'] is True and item['attempts']==0
    assert all(t['attempts']==0 for t in later['topics'])


def test_question_interval_uses_confidence():
    assert question_interval([QuestionAttempt(is_correct=True,confidence=1)])==1
    assert question_interval([QuestionAttempt(is_correct=True,confidence=2)])==2
    assert question_interval([QuestionAttempt(is_correct=True,confidence=3)])==3
    assert question_interval([QuestionAttempt(is_correct=False,confidence=3)])==1


def test_feedback_validation_and_static_three_tabs(client):
    resp=client.get('/')
    assert 'Caderno de erros' in resp.text
    assert 'id="tab-settings"' in resp.text
    assert 'id="cardsRefresh"' in resp.text
    assert 'id="errorsRefresh"' in resp.text
    sub=client.post('/api/subjects',json={'name':'Bancários'}).json()
    topic=client.post('/api/topics',json={'subject_id':sub['id'],'title':'SFN'}).json()
    session=client.post('/api/sessions').json()
    bad=client.post(f"/api/sessions/{session['id']}/topic-reviews",json={'topic_id':topic['id'],'grade':5,'difficulty':4})
    assert bad.status_code==422
