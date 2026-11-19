"""A alternância muda a ordem, sem adulterar as evidências de aprendizagem."""
from datetime import datetime, timedelta, timezone
from app.engine import build_queue
from app.db import get_db
from app.models import TopicReview, StudySession


def test_recently_repeated_hard_topic_yields_to_other_due_topic(client):
    subject = client.post('/api/subjects', json={'name': 'Bancários'}).json()
    hard = client.post('/api/topics', json={'subject_id': subject['id'], 'title': 'Mercado aberto', 'importance': 5}).json()
    other = client.post('/api/topics', json={'subject_id': subject['id'], 'title': 'Redesconto', 'importance': 1}).json()
    now = datetime.now(timezone.utc)
    with next(client.app.dependency_overrides[get_db]()) as db:
        for i in range(4):
            db.add(StudySession(id=100+i, opened_at=now-timedelta(days=28-7*i)))
        db.add(StudySession(id=200, opened_at=now-timedelta(days=35)))
        db.flush()
        for i in range(4):
            db.add(TopicReview(topic_id=hard['id'], session_id=100+i, grade=0,
                               difficulty=3, critical_gap=True, created_at=now-timedelta(days=28-7*i)))
        db.add(TopicReview(topic_id=other['id'], session_id=200, grade=4,
                           difficulty=1, created_at=now-timedelta(days=35)))
        db.commit()
        queue = build_queue(db, now=now, subject_id=subject['id'])['topics']
    assert all(item['maintenance_required'] for item in queue)
    assert queue[0]['id'] == other['id']
    hard_row = next(item for item in queue if item['id'] == hard['id'])
    assert hard_row['diversification_penalty'] > 0
    assert hard_row['queue_order_score'] < hard_row['ranking_score']
    assert hard_row['critical_gap'] is True
    assert hard_row['priority'] == round(sum(hard_row['priority_components'][k]*w for k,w in [('D',.35),('T',.30),('E',.25),('I',.10)]),2)


def test_multiple_reviews_same_session_do_not_count_as_multiple_sessions(client):
    subject = client.post('/api/subjects', json={'name': 'Português'}).json()
    first = client.post('/api/topics', json={'subject_id': subject['id'], 'title': 'Crase', 'importance': 5}).json()
    second = client.post('/api/topics', json={'subject_id': subject['id'], 'title': 'Pontuação', 'importance': 1}).json()
    now = datetime.now(timezone.utc)
    with next(client.app.dependency_overrides[get_db]()) as db:
        for i in range(3):
            db.add(StudySession(id=301+i, opened_at=now-timedelta(days=21-7*i)))
        db.flush()
        for i in range(3):
            db.add(TopicReview(topic_id=first['id'], session_id=301+i, grade=0, difficulty=3,
                               critical_gap=True, created_at=now-timedelta(days=21-7*i)))
        db.add(TopicReview(topic_id=second['id'], session_id=301, grade=0, difficulty=3,
                           created_at=now-timedelta(days=21)))
        db.commit()
        queue = build_queue(db, now=now, subject_id=subject['id'])['topics']
    first_row = next(item for item in queue if item['id'] == first['id'])
    assert first_row['recent_review_count_3_sessions'] == 3
    assert first_row['diversification_penalty'] == 40.0
