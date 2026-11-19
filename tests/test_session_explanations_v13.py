"""v0.13: transparência do refresh, do progresso e da ordenação."""


def test_refresh_closes_session_and_new_session_is_independent(client):
    sid_subject = client.post('/api/subjects', json={'name':'Informática'}).json()['id']
    topic = client.post('/api/topics', json={'subject_id':sid_subject, 'title':'Redes'}).json()['id']
    question = client.post('/api/questions', json={'subject_id':sid_subject, 'url':'https://example.org/q1'}).json()['id']
    session = client.post('/api/sessions').json()['id']
    assert client.post(f'/api/sessions/{session}/topic-reviews', json={
        'topic_id':topic, 'recall_level':3, 'accuracy_level':3,
        'assistance_level':0, 'gap_level':0,
    }).status_code == 201
    assert client.post(f'/api/sessions/{session}/question-attempts', json={
        'question_id':question, 'is_correct':False, 'confidence':1
    }).status_code == 201
    queue = client.get(f'/api/sessions/{session}/queue?subject_id={sid_subject}').json()
    assert not queue['topics'] and not queue['questions']
    original = client.get(f'/api/sessions/{session}/progress').json()
    assert original == {'topics':[topic],'questions':[question]}

    finish = client.post(f'/api/sessions/{session}/refresh').json()
    assert finish['status'] == 'closed'
    dashboard = client.get('/api/dashboard').json()
    assert dashboard['recent_sessions'][0]['id'] == session
    assert dashboard['recent_sessions'][0]['refreshed_at']
    new_session = client.post('/api/sessions').json()
    assert new_session['id'] != session and new_session['status'] == 'open'
    assert client.get(f'/api/sessions/{new_session["id"]}/progress').json() == {
        'topics':[], 'questions':[]
    }
    new_queue = client.get(f'/api/sessions/{new_session["id"]}/queue?subject_id={sid_subject}').json()
    assert new_queue['topics'][0]['attempts'] == 1
    assert new_queue['questions'][0]['attempts'] == 1
    assert original == {'topics':[topic],'questions':[question]}


def test_priority_explanation_facts_available_for_topics_and_questions(client):
    subject = client.post('/api/subjects', json={'name':'Bancários'}).json()['id']
    client.post('/api/topics',json={'subject_id':subject,'title':'Mercado aberto'})
    client.post('/api/questions', json={'subject_id':subject,'statement':'Uma questão...?'})
    queue = client.get(f'/api/queue?subject_id={subject}').json()
    for collection in ('topics','questions'):
        item = queue[collection][0]
        assert item['base_interval_days'] >= 1
        assert item['interval_days'] == item['base_interval_days'] + item['interval_adjustment_days']
        assert 'recent_review_count_3_sessions' in item
        assert 'recent_review_count_12_sessions' in item
        assert 'visits_without_review' in item
        assert 'long_term_fairness_bonus' in item
        assert 'starvation_protected' in item
        assert 'due_order_bonus' in item
        assert 'diversification_penalty' in item
        assert 'early_review_penalty' in item
        assert 'queue_order_score' in item
        expected = round(item['ranking_score'] + item['due_order_bonus'] + item['long_term_fairness_bonus']
                         - item['diversification_penalty'] - item['early_review_penalty'], 2)
        assert item['queue_order_score'] == expected


def test_frontend_explains_refresh_and_comparison_with_actual_progress(client):
    html=client.get('/').text
    js=client.get('/static/app.js').text
    assert 'Concluir sessão e atualizar fila' in html
    assert 'v0.15' in html
    assert 'state.session = await api(\'/sessions\',\'POST\')' in js
    assert 'api(`/sessions/${state.session.id}/refresh`,\'POST\')' in js
    assert 'recent_sessions?.[0]?.refreshed_at' in js
    assert 'localStorage' not in js
    assert 'últimas 3 sessões' in js or 'últimas 3' in js
    assert 'últimas 12' in js
    assert 'visits_without_review' in js
    assert 'interval_adjustment_days' in js
    assert 'Os pesos a seguir são fixos' in js
    assert 'Entenda a prioridade e o histórico desta questão' in js
    assert 'Ordem Alta' not in js and 'Ordem Média' not in js
    assert 'Não é sua porcentagem de acertos' not in js  # utiliza explicação contextualizada


def test_empty_session_is_not_confused_with_empty_catalog(client):
    script=client.get('/static/app.js').text
    assert 'hasCatalogedTopics' in script
    assert 'hasCatalogedQuestions' in script
    assert 'Questões desta sessão concluídas' in script
    assert 'Você percorreu esta pilha' in script
    assert 'not in memory' not in script


def test_same_subject_cannot_be_recorded_twice_across_review_and_initial_study(client):
    subject=client.post('/api/subjects',json={'name':'Português'}).json()['id']
    review_first=client.post('/api/topics',json={'subject_id':subject,'title':'Sintaxe'}).json()['id']
    study_first=client.post('/api/topics',json={'subject_id':subject,'title':'Crase'}).json()['id']
    sid=client.post('/api/sessions').json()['id']
    assert client.post(f'/api/sessions/{sid}/topic-reviews',json={
        'topic_id':review_first,'grade':3
    }).status_code==201
    assert client.post(f'/api/sessions/{sid}/new-content',json={
        'topic_id':review_first, 'recall_level':3, 'accuracy_level':3, 'gap_level':0
    }).status_code==409
    assert client.post(f'/api/sessions/{sid}/new-content',json={
        'topic_id':study_first, 'recall_level':2, 'accuracy_level':3, 'gap_level':1
    }).status_code==201
    assert client.post(f'/api/sessions/{sid}/topic-reviews',json={
        'topic_id':study_first,'grade':3
    }).status_code==409
    actual=client.get(f'/api/sessions/{sid}/queue?subject_id={subject}').json()
    assert actual['topics']==[]
