"""Garantias obrigatórias: fórmula exata, prazo máximo e domínio rigoroso."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import get_db
from app.engine import (build_queue, is_topic_mastered, mastery_evidence, topic_state,
                        topic_interval)
from app.models import QuestionAttempt, TopicReview


def review_on(days_ago, grade=4, explained=True, novel=True, critical=False, difficulty=1):
    return TopicReview(topic_id=1, session_id=abs(days_ago) + 10, grade=grade, difficulty=difficulty,
                       explained_without_consulting=explained,
                       applied_to_new_questions=novel, critical_gap=critical,
                       created_at=datetime(2026, 11, 18, tzinfo=timezone.utc) - timedelta(days=days_ago))


def seven_question_sample(concept_pending=False):
    base = datetime(2026, 11, 18, tzinfo=timezone.utc)
    # Pelo menos 8 tentativas, 7 questões diferentes e 6/7 acertos finais (85,71%).
    attempts = [QuestionAttempt(question_id=1, is_correct=False, confidence=1,
                                error_type='concept', created_at=base - timedelta(days=24))]
    for i in range(1, 8):
        attempts.append(QuestionAttempt(question_id=i, is_correct=i != 7, confidence=3,
                                        error_type='concept' if i == 7 and concept_pending else 'attention',
                                        created_at=base - timedelta(days=3)))
    return attempts


def test_formula_35_30_25_10_is_exact_and_in_0_to_100(client):
    s=client.post('/api/subjects',json={'name':'Bancários'}).json()
    t=client.post('/api/topics',json={'subject_id':s['id'],'title':'Bancos','importance':5}).json()
    sid=client.post('/api/sessions').json()['id']
    assert client.post(f'/api/sessions/{sid}/topic-reviews',json={
        'topic_id':t['id'],'grade':2,'difficulty':3,'critical_gap':True,
        'explained_without_consulting':False,'applied_to_new_questions':False
    }).status_code==201
    item=client.get('/api/queue').json()['topics'][0]
    c=item['priority_components']
    assert sorted(c)==['D','E','I','T']
    assert all(0 <= v <= 100 for v in c.values())
    assert c['I']==100
    expected=round(.35*c['D']+.30*c['T']+.25*c['E']+.10*c['I'],2)
    assert item['priority']==expected
    assert 0<=item['priority']<=100
    assert item['learning_state']=='em_aprendizagem'


def test_overdue_easy_topic_beats_high_score_recent_hard_topic(client):
    s=client.post('/api/subjects',json={'name':'Português'}).json()
    easy=client.post('/api/topics',json={'subject_id':s['id'],'title':'Ortografia','importance':1}).json()
    hard=client.post('/api/topics',json={'subject_id':s['id'],'title':'Semântica','importance':5}).json()
    sid=client.post('/api/sessions').json()['id']
    for topic,grade,diff in ((easy,4,1),(hard,0,3)):
        assert client.post(f'/api/sessions/{sid}/topic-reviews',json={'topic_id':topic['id'],
                'grade':grade,'difficulty':diff,'explained_without_consulting':grade==4}).status_code==201
    with next(client.app.dependency_overrides[get_db]()) as db:
        r=db.scalars(select(TopicReview)).all()
        now=datetime.now(timezone.utc)
        for row in r:
            if row.topic_id==easy['id']:row.created_at=now-timedelta(days=30)
            else:row.created_at=now-timedelta(minutes=20)
        db.commit()
        queue=build_queue(db,now=now)['topics']
    assert queue[0]['id']==easy['id']
    assert queue[0]['priority'] < queue[1]['priority']
    assert queue[0]['maintenance_required'] is True
    assert queue[1]['maintenance_required'] is False
    assert queue[0]['interval_days'] <= 30


def test_no_history_no_fabricated_missed_maintenance(client):
    s=client.post('/api/subjects',json={'name':'Matemática'}).json()
    client.post('/api/topics',json={'subject_id':s['id'],'title':'Porcentagem'}).json()
    q=client.get('/api/queue').json()['topics'][0]
    assert q['maintenance_required'] is False
    assert q['learning_state']=='em_aprendizagem'
    assert q['attempts']==0


def test_mastery_requires_all_six_independent_evidences():
    r=[review_on(50), review_on(35), review_on(0)]
    attempts=seven_question_sample()
    report=mastery_evidence(r,attempts)
    assert report['mastered'] is True
    assert report['distinct_questions']==7
    assert report['question_accuracy_percent']>=85
    assert topic_state(r,report)=='dominado'
    assert topic_interval(r)==60
    assert is_topic_mastered(r,attempts)
    # Explicou com consulta? Então não é domínio comprovado.
    without_explanation=[review_on(50),review_on(35),review_on(0,explained=False)]
    assert is_topic_mastered(without_explanation,attempts) is False
    # Não declarou prática em questões inéditas? Sem inferências artificiais.
    without_novel=[review_on(50),review_on(35),review_on(0,novel=False)]
    assert is_topic_mastered(without_novel,attempts) is False
    # Apenas 7 tentativas em 7 links não bastam para o tamanho mínimo da amostra.
    assert is_topic_mastered(r,attempts[1:]) is False
    # Menos de 14 dias entre as duas últimas recuperações não comprova espaçamento.
    unspaced=[review_on(18),review_on(8),review_on(0)]
    assert is_topic_mastered(unspaced,attempts) is False


def test_conceptual_error_blocks_mastery_until_confidently_resolved():
    r=[review_on(50),review_on(35),review_on(0)]
    attempts=seven_question_sample(concept_pending=True)
    ev=mastery_evidence(r,attempts)
    assert ev['question_accuracy_percent']>=85
    assert ev['pending_concept_errors']==1
    assert ev['no_critical_gaps'] is False
    assert ev['mastered'] is False
    assert topic_state(r,ev)=='em_aprendizagem'
    attempts.append(QuestionAttempt(question_id=7,is_correct=True,confidence=2,
                                    created_at=datetime(2026,11,18,tzinfo=timezone.utc)))
    assert mastery_evidence(r,attempts)['mastered'] is False
    attempts.append(QuestionAttempt(question_id=7,is_correct=True,confidence=3,
                                    created_at=datetime(2026,11,18,tzinfo=timezone.utc)+timedelta(seconds=1)))
    assert mastery_evidence(r,attempts)['mastered'] is True


def test_critical_topic_gap_remains_pending_until_independent_explanation():
    r=[review_on(60,grade=2,critical=True,explained=False),review_on(50),review_on(35),review_on(0)]
    assert is_topic_mastered(r,seven_question_sample()) is True
    unresolved=[review_on(60,grade=2,critical=True,explained=False),
                review_on(50,explained=False),review_on(35,explained=False),review_on(0,explained=False)]
    report=mastery_evidence(unresolved,seven_question_sample())
    assert report['no_critical_gaps'] is False
    assert report['mastered'] is False


def test_api_records_explanation_novelty_and_persists_across_refresh(client):
    s=client.post('/api/subjects',json={'name':'Conhecimentos Bancários'}).json()
    t=client.post('/api/topics',json={'subject_id':s['id'],'title':'Copom'}).json()
    sid=client.post('/api/sessions').json()['id']
    payload={'topic_id':t['id'],'grade':4,'difficulty':1,'critical_gap':False,
             'explained_without_consulting':True,'applied_to_new_questions':True}
    assert client.post(f'/api/sessions/{sid}/topic-reviews',json=payload).status_code==201
    assert client.post(f'/api/sessions/{sid}/refresh').status_code==200
    q=client.get('/api/queue').json()['topics'][0]
    assert q['learning_state']=='em_consolidacao'
    assert q['mastery_evidence']['explained_without_consulting'] is True
    assert q['mastery_evidence']['applied_to_new_questions'] is True
    assert q['mastered'] is False
    with next(client.app.dependency_overrides[get_db]()) as db:
        saved=db.scalars(select(TopicReview)).first()
        assert saved.explained_without_consulting is True
        assert saved.applied_to_new_questions is True
    # Um recarregamento da pilha volta ao PostgreSQL, não à memória do frontend.
    assert client.get('/api/queue').json()['topics'][0]['attempts']==1


def test_frontend_shows_state_formula_and_evidence_fields(client):
    html=client.get('/').text
    script=client.get('/static/app.js').text
    assert 'name="explained_without_consulting"' in html
    assert 'name="applied_to_new_questions"' in html
    assert 'Entender prioridade e critérios de domínio' in script
    assert 'Prazo atingido nesta matéria' in script
    assert 'Em consolidação' in script and 'Dominado' in script
