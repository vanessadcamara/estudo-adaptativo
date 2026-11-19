"""Regressões v0.7: seleção explícita, separação entre matérias e memória."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import get_db
from app.engine import (build_queue, forgetting_risk, question_forgetting_risk,
                        question_interval, topic_forgetting_risk, topic_interval)
from app.models import Question, QuestionAttempt, TopicReview


NOW = datetime(2026, 11, 18, 13, 0, tzinfo=timezone.utc)


def test_subject_scopes_both_queues_and_not_changes_foreign_priorities(client):
    pt = client.post('/api/subjects', json={'name': 'Português'}).json()['id']
    mt = client.post('/api/subjects', json={'name': 'Matemática'}).json()['id']
    pt_topic = client.post('/api/topics', json={'subject_id': pt, 'title': 'Concordância', 'importance': 1}).json()['id']
    mt_topic = client.post('/api/topics', json={'subject_id': mt, 'title': 'Frações', 'importance': 5}).json()['id']
    pt_question = client.post('/api/questions', json={'subject_id': pt, 'topic_id': pt_topic,
        'url': 'https://example.com/portugues'}).json()['id']
    mt_question = client.post('/api/questions', json={'subject_id': mt, 'topic_id': mt_topic,
        'url': 'https://example.com/matematica'}).json()['id']
    session = client.post('/api/sessions').json()['id']
    for topic_id, grade in [(pt_topic, 4), (mt_topic, 0)]:
        assert client.post(f'/api/sessions/{session}/topic-reviews', json={
            'topic_id': topic_id, 'grade': grade, 'difficulty': 1}).status_code == 201
    for question_id, correct in [(pt_question, True), (mt_question, False)]:
        assert client.post(f'/api/sessions/{session}/question-attempts', json={
            'question_id': question_id, 'is_correct': correct, 'confidence': 3}).status_code == 201
    with next(client.app.dependency_overrides[get_db]()) as db:
        pt_review = db.scalar(select(TopicReview).where(TopicReview.topic_id == pt_topic))
        mt_review = db.scalar(select(TopicReview).where(TopicReview.topic_id == mt_topic))
        pt_attempt = db.scalar(select(QuestionAttempt).where(QuestionAttempt.question_id == pt_question))
        mt_attempt = db.scalar(select(QuestionAttempt).where(QuestionAttempt.question_id == mt_question))
        pt_review.created_at = NOW - timedelta(days=40)
        pt_attempt.created_at = NOW - timedelta(days=4)
        mt_review.created_at = NOW - timedelta(hours=1)
        mt_attempt.created_at = NOW - timedelta(hours=1)
        db.commit()
        q_pt = build_queue(db, now=NOW, subject_id=pt)
        q_mt = build_queue(db, now=NOW, subject_id=mt)
        assert {x['id'] for x in q_pt['topics']} == {pt_topic}
        assert {x['id'] for x in q_pt['questions']} == {pt_question}
        assert {x['id'] for x in q_mt['topics']} == {mt_topic}
        assert {x['id'] for x in q_mt['questions']} == {mt_question}
        assert q_pt['topics'][0]['due'] and q_pt['questions'][0]['due']
        assert not q_mt['topics'][0]['due'] and not q_mt['questions'][0]['due']
        priority_snapshot = (q_pt['topics'][0]['priority'], q_pt['questions'][0]['priority'],
                             q_pt['topics'][0]['forgetting_risk_percent'], q_pt['questions'][0]['forgetting_risk_percent'])
        # Alterar todos os pesos e o histórico da segunda matéria não altera Português.
        mt_review.grade = 4
        mt_review.created_at = NOW - timedelta(days=100)
        mt_attempt.is_correct = True
        mt_attempt.confidence = 1
        mt_attempt.created_at = NOW - timedelta(days=100)
        db.commit()
        q_pt_after = build_queue(db, now=NOW, subject_id=pt)
        assert priority_snapshot == (q_pt_after['topics'][0]['priority'],
            q_pt_after['questions'][0]['priority'], q_pt_after['topics'][0]['forgetting_risk_percent'],
            q_pt_after['questions'][0]['forgetting_risk_percent'])
    # API expõe apenas matéria selecionada; o vencimento alheio não entra na resposta.
    api_pt = client.get(f'/api/queue?subject_id={pt}').json()
    assert api_pt['subject_id'] == pt
    assert [t['id'] for t in api_pt['topics']] == [pt_topic]
    assert [q['id'] for q in api_pt['questions']] == [pt_question]
    api_mt = client.get(f'/api/sessions/{session}/queue?subject_id={mt}').json()
    assert api_mt['topics'] == [] and api_mt['questions'] == []  # já feitos nesta sessão
    assert client.get('/api/queue?subject_id=999999').status_code == 404
    assert client.get('/api/queue?subject_id=-1').status_code == 422


def test_due_priority_is_only_within_selected_subject(client):
    a = client.post('/api/subjects', json={'name': 'História'}).json()['id']
    b = client.post('/api/subjects', json={'name': 'Geografia'}).json()['id']
    items = [client.post('/api/topics', json={'subject_id': a, 'title': name,
        'importance': importance}).json()['id'] for name, importance in
        [('Fácil vencido', 1), ('Difícil recente', 5)]]
    b_id = client.post('/api/topics', json={'subject_id': b, 'title': 'Outra matéria'}).json()['id']
    session = client.post('/api/sessions').json()['id']
    for topic_id, grade in [(items[0], 4), (items[1], 0), (b_id, 0)]:
        client.post(f'/api/sessions/{session}/topic-reviews',json={'topic_id': topic_id, 'grade': grade})
    with next(client.app.dependency_overrides[get_db]()) as db:
        for row in db.scalars(select(TopicReview)).all():
            row.created_at = NOW - timedelta(days=40 if row.topic_id == items[0] else 0)
        db.commit()
        local = build_queue(db, now=NOW, subject_id=a)
        assert {x['id'] for x in local['topics']} == set(items)
        rows = {x['id']: x for x in local['topics']}
        assert rows[items[0]]['maintenance_required'] is True
        assert rows[items[1]]['maintenance_required'] is False
        assert rows[items[0]]['priority'] < rows[items[1]]['priority']
        assert rows[items[0]]['due_order_bonus'] > rows[items[1]]['due_order_bonus']
        assert [x['id'] for x in build_queue(db, now=NOW, subject_id=b)['topics']] == [b_id]


def test_adaptive_intervals_respond_to_recent_mistakes_and_confidence():
    strong = [TopicReview(grade=4, difficulty=1, critical_gap=False) for _ in range(2)]
    weak = [TopicReview(grade=0, difficulty=1, critical_gap=False),
            TopicReview(grade=4, difficulty=1, critical_gap=False)]
    assert topic_interval(strong) > topic_interval(weak)
    assert topic_interval(weak) > topic_interval([TopicReview(grade=0)])
    confident = [QuestionAttempt(is_correct=True, confidence=3) for _ in range(2)]
    recovering = [QuestionAttempt(is_correct=False, confidence=3),
                  QuestionAttempt(is_correct=True, confidence=3)]
    assert question_interval(confident) > question_interval(recovering)
    assert question_interval([QuestionAttempt(is_correct=True, confidence=1)]) == 1


def test_risk_is_explanatory_uncalibrated_and_monotonic_in_time():
    assert forgetting_risk(None, 7, 0.2) is None
    assert forgetting_risk(0, 7, 0.2) < forgetting_risk(7, 7, 0.2) < forgetting_risk(30, 7, 0.2)
    strong = [TopicReview(grade=4, difficulty=1, critical_gap=False)]
    weak = [TopicReview(grade=1, difficulty=3, critical_gap=True)]
    assert topic_forgetting_risk([], 4, 7) is None
    assert topic_forgetting_risk(strong, 1, 7) < topic_forgetting_risk(weak, 1, 7)
    assert question_forgetting_risk([], 1, 3) is None
    safe = [QuestionAttempt(is_correct=True, confidence=3)]
    guess = [QuestionAttempt(is_correct=True, confidence=1)]
    wrong = [QuestionAttempt(is_correct=False, confidence=1)]
    assert question_forgetting_risk(safe, 0, 3) < question_forgetting_risk(guess, 0, 3)
    assert question_forgetting_risk(guess, 0, 3) < question_forgetting_risk(wrong, 0, 3)


def test_legacy_unassigned_questions_are_not_mixed_with_any_subject(client):
    subject = client.post('/api/subjects',json={'name':'Química'}).json()['id']
    question = client.post('/api/questions',json={'subject_id':subject,
        'url':'https://example.com/assigned'}).json()['id']
    with next(client.app.dependency_overrides[get_db]()) as db:
        orphan=Question(url='https://example.com/legacy',subject_id=None,topic_id=None)
        db.add(orphan)
        db.commit()
        orphan_id=orphan.id
    assert [q['id'] for q in client.get('/api/queue?subject_id=0').json()['questions']] == [orphan_id]
    assert [q['id'] for q in client.get(f'/api/queue?subject_id={subject}').json()['questions']] == [question]


def test_ui_requires_subject_choice_for_both_piles(client):
    html = client.get('/').text
    js = client.get('/static/app.js').text
    assert html.count('<option value="">Escolha uma matéria</option>') == 3
    assert 'id="cardsSubject"' in html
    assert 'id="errorsSubject"' in html
    assert 'id="novelSubject"' in html
    assert 'state.cardsQueue' in js and 'state.errorsQueue' in js
    assert 'loadSelectedQueue(\'cards\')' in js and 'loadSelectedQueue(\'errors\')' in js
    assert '`/sessions/${state.session.id}/queue`' in js and '`${route}?subject_id=${subjectId}`' in js
    assert 'function riskDescription(entry)' in js
    assert 'Esquecimento: risco' in js
    assert 'Esquecimento: ainda sem histórico' in js
    assert 'Nenhum vencimento força você' in js
    assert 'Revisão obrigatória' not in js
