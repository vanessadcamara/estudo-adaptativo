"""v0.9: entrada agregada sem assunto, dashboard honesto e prioridade local."""
from app.performance import wilson_interval


def create_subject(client, name):
    return client.post('/api/subjects', json={'name': name}).json()['id']


def test_novel_practice_is_persistent_editable_and_restorable(client):
    sid = create_subject(client, 'Português')
    payload = {'subject_id': sid, 'practice_date': '2026-11-18', 'total': 30, 'correct': 26}
    assert client.post('/api/novel-practice', json={**payload, 'correct': 31}).status_code == 422
    assert client.post('/api/novel-practice', json={**payload, 'total': 0}).status_code == 422
    entry = client.post('/api/novel-practice', json=payload)
    assert entry.status_code == 201, entry.text
    pk = entry.json()['id']
    assert 'topic_id' not in entry.json()
    assert len(client.get('/api/novel-practice').json()) == 1
    assert client.patch(f'/api/novel-practice/{pk}', json={**payload, 'correct': 27}).status_code == 200
    assert client.get('/api/performance').json()['subjects'][0]['accuracy_percent'] == 90
    assert client.delete(f'/api/novel-practice/{pk}').status_code == 200
    assert client.get('/api/novel-practice').json() == []
    assert client.get('/api/novel-practice?include_archived=true').json()[0]['archived_at'] is not None
    assert client.patch(f'/api/novel-practice/{pk}/restore').status_code == 200
    assert client.get('/api/performance').json()['subjects'][0]['total'] == 30


def test_novel_aggregation_weighted_and_isolated(client):
    a = create_subject(client, 'Português')
    b = create_subject(client, 'Matemática')
    for subject, day, total, correct in [(a, 18, 10, 10), (a, 17, 30, 20), (b, 18, 10, 9)]:
        response = client.post('/api/novel-practice', json={
            'subject_id': subject, 'practice_date': f'2026-11-{day}',
            'total': total, 'correct': correct})
        assert response.status_code == 201, response.text
    per = {s['id']: s for s in client.get('/api/performance').json()['subjects']}
    assert (per[a]['total'], per[a]['correct'], per[a]['accuracy_percent']) == (40, 30, 75.0)
    assert (per[b]['total'], per[b]['correct'], per[b]['accuracy_percent']) == (10, 9, 90.0)
    assert per[b]['interval_95']['low'] < 90 < per[b]['interval_95']['high']


def test_novel_practice_does_not_infer_topic_accuracy(client):
    subject = create_subject(client, 'Bancários')
    t = client.post('/api/topics', json={'subject_id': subject, 'title': 'SFN'}).json()['id']
    client.post('/api/novel-practice', json={'subject_id': subject, 'practice_date': '2026-11-18', 'total': 20, 'correct': 20})
    perf = client.get('/api/performance').json()
    topic = next(x for x in perf['topics'] if x['id'] == t)
    assert topic['distinct_links'] == 0 and topic['qualified_accuracy_percent'] is None
    assert topic['mastered'] is False
    assert perf['subjects'][0]['accuracy_percent'] == 100


def test_opportunity_only_depends_on_observed_topic_errors(client):
    subject = create_subject(client, 'Matemática Financeira')
    topic = client.post('/api/topics', json={'subject_id': subject, 'title': 'Juros'}).json()['id']
    q0 = client.get(f'/api/queue?subject_id={subject}').json()['topics'][0]
    qid = client.post('/api/questions', json={
        'subject_id': subject, 'topic_id': topic, 'url': 'https://example.org/juros'}).json()['id']
    q1 = client.get(f'/api/queue?subject_id={subject}').json()['topics'][0]
    assert q0['ranking_score'] == q1['ranking_score']
    session = client.post('/api/sessions').json()['id']
    client.post(f'/api/sessions/{session}/question-attempts', json={
        'question_id': qid, 'is_correct': False, 'confidence': 3, 'error_type': 'concept'})
    q2 = client.get(f'/api/queue?subject_id={subject}').json()['topics'][0]
    assert 0 < q2['opportunity_priority_bonus'] <= 6
    assert q2['priority'] == q1['priority']


def test_wilson_does_not_fabricate_without_data():
    assert wilson_interval(0, 0) is None
    assert wilson_interval(9, 10)['low'] < 90
    assert wilson_interval(90, 100)['low'] > wilson_interval(9, 10)['low']


def test_v09_frontend_has_requested_order_and_no_auto_coaching(client):
    html = client.get('/').text
    js = client.get('/static/app.js').text
    nav = html.split('<nav class="tabs"', 1)[1].split('</nav>', 1)[0]
    assert [nav.index('data-tab="' + tab + '"') for tab in ('performance', 'cards', 'errors', 'novel', 'settings')] == sorted(
        nav.index('data-tab="' + tab + '"') for tab in ('performance', 'cards', 'errors', 'novel', 'settings'))
    assert 'id="novelForm"' in html
    assert 'id="performanceSubjects"' in html
    assert "'/performance'" in js
    assert 'Orientação automática de resolução' not in js
    assert 'varied_questions_90_percent' in js


def test_novel_practice_never_changes_topic_ranking(client):
    subject = create_subject(client, 'Inglês')
    client.post('/api/topics', json={'subject_id': subject, 'title': 'Reading comprehension'})
    before = client.get(f'/api/queue?subject_id={subject}').json()['topics'][0]
    client.post('/api/novel-practice', json={'subject_id': subject,
        'practice_date': '2026-11-18', 'total': 100, 'correct': 30})
    after = client.get(f'/api/queue?subject_id={subject}').json()['topics'][0]
    assert before['priority'] == after['priority']
    assert before['ranking_score'] == after['ranking_score']


def test_risk_audit_hides_unreliable_small_samples(client):
    subject = create_subject(client, 'Atualidades')
    client.post('/api/topics', json={'subject_id': subject, 'title': 'Finanças'})
    queue = client.get(f'/api/queue?subject_id={subject}').json()
    audit = queue['topics'][0]['risk_calibration_audit']
    assert audit['samples'] == 0
    assert audit['brier'] is None and audit['sufficient'] is False


def test_no_past_semi_novel_success_masquerades_as_latest(client):
    from datetime import datetime, timedelta, timezone
    from app.engine import semi_novel_progress
    from app.models import Question, QuestionAttempt
    now = datetime(2026, 11, 18, tzinfo=timezone.utc)
    question = Question(id=5)
    def attempt(ago, correct):
        return QuestionAttempt(question_id=5, is_correct=correct, confidence=3,
                               created_at=now-timedelta(days=ago))
    attempts = {5: [attempt(30, False), attempt(20, True), attempt(19, False)]}
    result = semi_novel_progress([question], attempts, now)
    assert result['spaced_distinct'] == 0
    assert result['spaced_secure_percent'] is None
