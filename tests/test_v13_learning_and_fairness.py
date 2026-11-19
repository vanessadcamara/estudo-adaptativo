"""v0.13: structured assessment, audit, and guaranteed queue return by subject visits."""
from datetime import datetime, timedelta, timezone

from app.assessment import inferred_grade
from app.db import get_db
from app.engine import build_queue
from app.models import NewContentLog, StudySession, TopicReview


def test_inferred_grade_is_conservative_and_transparent():
    assert inferred_grade(3, 3, 0, 0) == 4
    assert inferred_grade(3, 3, 1, 0) == 3
    assert inferred_grade(3, 3, 3, 0) == 1  # v0.14: consulta limita nota a 1
    assert inferred_grade(3, 2, 0, 1) == 3
    assert inferred_grade(3, 3, 0, 2) == 2
    assert inferred_grade(0, 3, 0, 0) == 0
    assert inferred_grade(1, 3, 0, 0) == 1


def test_new_review_questionnaire_persists_derived_grade_and_prevents_repeat(client):
    sub = client.post('/api/subjects', json={'name': 'Português'}).json()['id']
    topic = client.post('/api/topics', json={'subject_id': sub, 'title': 'Concordância'}).json()['id']
    session = client.post('/api/sessions').json()['id']
    payload = {'topic_id': topic, 'recall_level': 3, 'accuracy_level': 3,
               'assistance_level': 0, 'gap_level': 0, 'difficulty': 2,
               'applied_to_new_questions': True}
    result = client.post(f'/api/sessions/{session}/topic-reviews', json=payload)
    assert result.status_code == 201, result.text
    assert result.json()['inferred_grade'] == 4
    with next(client.app.dependency_overrides[get_db]()) as db:
        row = db.query(TopicReview).filter(TopicReview.topic_id == topic).one()
        assert (row.grade, row.recall_level, row.accuracy_level,
                row.assistance_level, row.gap_level) == (4, 3, 3, 0, 0)
        assert row.explained_without_consulting is True
        assert row.critical_gap is False
    assert topic not in [r['id'] for r in client.get(f'/api/sessions/{session}/queue?subject_id={sub}').json()['topics']]
    assert client.post(f'/api/sessions/{session}/topic-reviews', json=payload).status_code == 409
    assert client.post(f'/api/sessions/{session}/topic-reviews', json={
        'topic_id': topic, 'recall_level': 3, 'grade': 4}).status_code == 422


def test_questionnaire_marks_critical_gaps_and_legacy_grade_still_supported(client):
    sub = client.post('/api/subjects', json={'name': 'Informática'}).json()['id']
    a = client.post('/api/topics', json={'subject_id': sub, 'title': 'Redes'}).json()['id']
    b = client.post('/api/topics', json={'subject_id': sub, 'title': 'Linux'}).json()['id']
    sid = client.post('/api/sessions').json()['id']
    response = client.post(f'/api/sessions/{sid}/topic-reviews', json={
        'topic_id': a, 'recall_level': 3, 'accuracy_level': 3,
        'assistance_level': 0, 'gap_level': 3})
    assert response.json()['inferred_grade'] == 1
    legacy = client.post(f'/api/sessions/{sid}/topic-reviews', json={
        'topic_id': b, 'grade': 3, 'explained_without_consulting': True})
    assert legacy.status_code == 201 and legacy.json()['inferred_grade'] == 3
    with next(client.app.dependency_overrides[get_db]()) as db:
        assert db.query(TopicReview).filter(TopicReview.topic_id == a).one().critical_gap


def test_initial_study_is_not_fake_spaced_retention_and_does_not_repeat(client):
    sub = client.post('/api/subjects', json={'name': 'Matemática'}).json()['id']
    topic = client.post('/api/topics', json={'subject_id': sub, 'title': 'Porcentagem'}).json()['id']
    sid = client.post('/api/sessions').json()['id']
    payload = {'topic_id': topic, 'minutes': 40, 'recall_level': 3,
               'accuracy_level': 3, 'gap_level': 0}
    r = client.post(f'/api/sessions/{sid}/new-content', json=payload)
    assert r.status_code == 201, r.text
    assert client.post(f'/api/sessions/{sid}/new-content', json=payload).status_code == 409
    assert topic not in [t['id'] for t in client.get(f'/api/sessions/{sid}/queue?subject_id={sub}').json()['topics']]
    with next(client.app.dependency_overrides[get_db]()) as db:
        assert db.query(TopicReview).count() == 0
        row = db.query(NewContentLog).one()
        assert (row.recall_level, row.accuracy_level, row.gap_level) == (3, 3, 0)
    out = client.get('/api/performance').json()
    assert out['subjects'][0]['spaced_recall_7d']['samples'] == 0


def test_long_term_return_after_seven_subject_visits_and_reset_after_review(client):
    sub = client.post('/api/subjects', json={'name': 'Bancários'}).json()['id']
    neglected = client.post('/api/topics', json={'subject_id': sub, 'title': 'Redesconto'}).json()['id']
    frequent = client.post('/api/topics', json={'subject_id': sub, 'title': 'Mercado aberto'}).json()['id']
    now = datetime.now(timezone.utc) + timedelta(days=100)
    with next(client.app.dependency_overrides[get_db]()) as db:
        for i in range(8):
            stamp = now - timedelta(days=8-i)
            db.add(StudySession(id=9200+i, opened_at=stamp))
            db.add(TopicReview(topic_id=frequent, session_id=9200+i,
                               grade=0, difficulty=3, critical_gap=True, created_at=stamp))
        db.commit()
        queue = build_queue(db, now=now, subject_id=sub)['topics']
        item = next(r for r in queue if r['id'] == neglected)
        competitor = next(r for r in queue if r['id'] == frequent)
        assert item['visits_without_review'] >= 7
        assert item['recent_review_count_12_sessions'] == 0
        assert competitor['recent_review_count_3_sessions'] == 3
        assert item['starvation_protected'] is True
        assert queue[0]['id'] == neglected
        assert item['long_term_fairness_bonus'] > 0
        db.add(StudySession(id=9300, opened_at=now))
        db.add(TopicReview(topic_id=neglected, session_id=9300, grade=3,
                           difficulty=1, critical_gap=False, created_at=now))
        db.commit()
        later = build_queue(db, now=now+timedelta(days=1), subject_id=sub)['topics']
        item = next(r for r in later if r['id'] == neglected)
        assert not item['starvation_protected']
        assert item['visits_without_review'] == 0


def test_subject_boundaries_and_ineligible_non_due_are_respected(client):
    a = client.post('/api/subjects', json={'name': 'Matemática'}).json()['id']
    b = client.post('/api/subjects', json={'name': 'Português'}).json()['id']
    a_topic = client.post('/api/topics', json={'subject_id': a, 'title': 'Frações'}).json()['id']
    b_topic = client.post('/api/topics', json={'subject_id': b, 'title': 'Sintaxe'}).json()['id']
    now = datetime.now(timezone.utc)+timedelta(days=40)
    with next(client.app.dependency_overrides[get_db]()) as db:
        for i in range(8):
            stamp=now-timedelta(days=8-i)
            db.add(StudySession(id=9400+i, opened_at=stamp))
            db.add(TopicReview(topic_id=b_topic, session_id=9400+i,
                               grade=0, created_at=stamp))
        db.add(StudySession(id=9500, opened_at=now))
        db.add(TopicReview(topic_id=a_topic, session_id=9500,
                           grade=4, difficulty=1, created_at=now))
        db.commit()
        row=next(r for r in build_queue(db, now=now, subject_id=a)['topics'] if r['id']==a_topic)
        assert row['visits_without_review']==0
        assert not row['starvation_protected']
        assert row['recent_review_count_12_sessions']==1
        assert len(build_queue(db, now=now, subject_id=b)['topics'])==1


def test_exam_like_practice_is_separate_from_all_novel_results(client):
    sub = client.post('/api/subjects', json={'name': 'Atendimento'}).json()['id']
    a = {'subject_id': sub, 'practice_date': '2026-11-19', 'total': 10, 'correct': 10,
         'exam_conditions': True, 'no_consultation': True, 'distinct_questions': True}
    b = {'subject_id': sub, 'practice_date': '2026-11-18', 'total': 10, 'correct': 0}
    first = client.post('/api/novel-practice', json=a)
    assert first.status_code == 201, first.text
    assert client.post('/api/novel-practice', json=b).status_code == 201
    perf = client.get('/api/performance').json()['subjects'][0]
    assert perf['total'] == 20 and perf['accuracy_percent'] == 50
    assert perf['exam_like']['total'] == 10 and perf['exam_like']['accuracy_percent'] == 100
    assert client.patch(f"/api/novel-practice/{first.json()['id']}", json={
        **a, 'exam_conditions': False}).status_code == 200
    assert client.get('/api/performance').json()['subjects'][0]['exam_like']['total'] == 0
