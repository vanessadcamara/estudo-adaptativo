from datetime import datetime, timedelta, timezone

from app.engine import build_queue, is_topic_mastered, question_interval, topic_interval
from app.models import QuestionAttempt, TopicReview


def test_flow_refresh_preserves_history(client):
    subject = client.post('/api/subjects', json={'name':'Conhecimentos Bancários'}).json()
    topic = client.post('/api/topics',json={'subject_id':subject['id'],'code':'A1','title':'Sistema Financeiro Nacional'}).json()
    q = client.post('/api/questions',json={'url':'https://example.org/questao/1'}).json()
    session = client.post('/api/sessions').json()
    sid = session['id']
    assert len(client.get(f'/api/sessions/{sid}/queue').json()['topics']) == 1
    assert client.post(f'/api/sessions/{sid}/topic-reviews',json={'topic_id':topic['id'],'grade':1}).status_code == 201
    assert client.post(f'/api/sessions/{sid}/question-attempts',json={'question_id':q['id'],'is_correct':False}).status_code == 201
    assert client.get(f'/api/sessions/{sid}/queue').json()['topics'] == []
    assert client.post(f'/api/sessions/{sid}/topic-reviews',json={'topic_id':topic['id'],'grade':4}).status_code == 409
    finish = client.post(f'/api/sessions/{sid}/refresh').json()
    assert finish['status'] == 'closed'
    assert finish['refresh_summary']['topics_reviewed'] == 1
    assert finish['refresh_summary']['questions_wrong'] == 1
    assert client.post(f'/api/sessions/{sid}/refresh').status_code == 409
    assert client.post(f'/api/sessions/{sid}/question-attempts', json={'question_id':q['id'],'is_correct':True}).status_code == 409
    session2 = client.post('/api/sessions').json()
    assert session2['id'] != sid
    assert client.get('/api/dashboard').json()['total_questions'] == 1
    assert client.get('/api/dashboard').json()['total_topics'] == 1


def test_questions_need_link_or_statement(client):
    assert client.post('/api/questions',json={}).status_code == 422
    assert client.post('/api/questions',json={'url':'javascript:alert(1)'}).status_code == 422
    assert client.post('/api/questions',json={'statement':'O SFN é formado por...'}).status_code == 201
    assert client.post('/api/questions',json={'url':'https://example.org/q'}).status_code == 201
    assert client.post('/api/questions',json={'url':'https://example.org/q'}).status_code == 409


def test_new_content_is_logged_not_automatically_graded(client):
    sub=client.post('/api/subjects',json={'name':'Português'}).json()
    topic=client.post('/api/topics',json={'subject_id':sub['id'],'title':'Concordância'}).json()
    session=client.post('/api/sessions').json()
    assert client.post(f"/api/sessions/{session['id']}/new-content",json={'topic_id':topic['id'],'minutes':60}).status_code == 201
    snapshot=client.post(f"/api/sessions/{session['id']}/refresh").json()['refresh_summary']
    assert snapshot['new_content_minutes']==60
    assert snapshot['topics_reviewed']==0
    preview=client.get('/api/queue').json()
    assert preview['topics'][0]['due'] is False


def test_pacing_and_mastery_gate():
    now=datetime.now(timezone.utc)
    events=[TopicReview(session_id=i+1,topic_id=1,grade=g,created_at=now-timedelta(days=d))
            for i,(d,g) in enumerate([(30,4),(20,4),(0,4)])]
    assert topic_interval(events)==60
    assert is_topic_mastered(events,[]) is False  # Somente explicações não bastam.
    assert topic_interval([TopicReview(grade=0)])==1
    assert topic_interval([TopicReview(grade=1)])==2
    assert topic_interval([TopicReview(grade=2)])==4
    assert topic_interval([TopicReview(grade=3)])==7
    assert question_interval([QuestionAttempt(is_correct=True)])==3
    assert question_interval([QuestionAttempt(is_correct=False)])==1


def test_seven_day_gap_reorders_by_elapsed_time(client):
    from app.db import get_db
    from sqlalchemy import select
    from app.models import TopicReview

    sub=client.post('/api/subjects',json={'name':'Inglês'}).json()
    topic=client.post('/api/topics',json={'subject_id':sub['id'],'title':'Reading'}).json()
    session=client.post('/api/sessions').json()
    client.post(f"/api/sessions/{session['id']}/topic-reviews",json={'topic_id':topic['id'],'grade':2})
    client.post(f"/api/sessions/{session['id']}/refresh")
    gen=get_db.__wrapped__ if hasattr(get_db,'__wrapped__') else None
    # A API usa a data atual; o motor também permite simular um retorno após 7 dias.
    get_session=client.app.dependency_overrides[get_db]
    with next(get_session()) as db:
        last=db.scalars(select(TopicReview)).first()
        first=build_queue(db,now=last.created_at+timedelta(hours=1))
        later=build_queue(db,now=last.created_at+timedelta(days=7))
    assert first['topics'][0]['due'] is False
    assert later['topics'][0]['due'] is True
    assert later['topics'][0]['priority']>first['topics'][0]['priority']
