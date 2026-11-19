"""v0.11: alternância flexível e não repetição por sessão."""
from datetime import datetime, timedelta, timezone
from app.db import get_db
from app.engine import build_queue, topic_interval, question_interval
from app.models import StudySession, TopicReview, QuestionAttempt


def test_non_due_topic_can_pass_repeated_due_topic(client):
    subject = client.post('/api/subjects', json={'name': 'Bancários'}).json()['id']
    repeated = client.post('/api/topics', json={'subject_id': subject, 'title': 'Mercado aberto', 'importance': 5}).json()['id']
    alternate = client.post('/api/topics', json={'subject_id': subject, 'title': 'Redesconto', 'importance': 5}).json()['id']
    now = datetime.now(timezone.utc)
    with next(client.app.dependency_overrides[get_db]()) as db:
        for n in range(4):
            db.add(StudySession(id=600+n, opened_at=now-timedelta(days=28-7*n)))
        db.flush()
        for n in range(3):
            db.add(TopicReview(topic_id=repeated, session_id=601+n, grade=0, difficulty=3,
                               critical_gap=True, created_at=now-timedelta(days=21-7*n)))
        db.commit()
        rows = build_queue(db, now=now, subject_id=subject)['topics']
    by_id = {x['id']: x for x in rows}
    assert by_id[repeated]['maintenance_required']
    assert not by_id[alternate]['maintenance_required']
    assert by_id[repeated]['diversification_penalty'] > 0
    assert rows[0]['id'] == alternate
    assert by_id[repeated]['due_order_bonus'] > 0


def test_evaluated_cards_and_questions_not_recommended_again_in_session(client):
    subject = client.post('/api/subjects', json={'name': 'Português'}).json()['id']
    t1 = client.post('/api/topics', json={'subject_id': subject, 'title': 'Crase'}).json()['id']
    t2 = client.post('/api/topics', json={'subject_id': subject, 'title': 'Pontuação'}).json()['id']
    q1 = client.post('/api/questions', json={'subject_id': subject, 'topic_id': t1, 'url': 'https://example.org/1'}).json()['id']
    q2 = client.post('/api/questions', json={'subject_id': subject, 'topic_id': t1, 'url': 'https://example.org/2'}).json()['id']
    sid = client.post('/api/sessions').json()['id']
    assert client.post(f'/api/sessions/{sid}/topic-reviews', json={'topic_id': t1, 'grade': 2}).status_code == 201
    assert client.post(f'/api/sessions/{sid}/question-attempts', json={'question_id': q1, 'is_correct': False}).status_code == 201
    queue = client.get(f'/api/sessions/{sid}/queue?subject_id={subject}').json()
    assert [x['id'] for x in queue['topics']] == [t2]
    assert [x['id'] for x in queue['questions']] == [q2]
    assert client.post(f'/api/sessions/{sid}/topic-reviews', json={'topic_id': t1, 'grade': 2}).status_code == 409
    assert client.post(f'/api/sessions/{sid}/question-attempts', json={'question_id': q1, 'is_correct': True}).status_code == 409


def test_intervals_are_not_changed_by_rotation():
    assert topic_interval([TopicReview(grade=4, difficulty=1)]) == 14
    assert topic_interval([TopicReview(grade=0, difficulty=3)]) == 1
    assert question_interval([QuestionAttempt(is_correct=True, confidence=3)]) == 3
    assert question_interval([QuestionAttempt(is_correct=False, confidence=3)]) == 1
