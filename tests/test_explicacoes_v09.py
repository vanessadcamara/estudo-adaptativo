"""A interface explica o progresso em linguagem comum sem alterar o algoritmo."""


def test_explicacoes_sao_legiveis_e_situacionais(client):
    script = client.get('/static/app.js').text
    assert 'Entenda sua prioridade e seu progresso' in script
    assert 'Você reuniu todas as evidências de domínio' in script
    assert 'Você já demonstrou progresso nas revisões' in script
    assert 'Ainda não há revisões deste assunto' in script
    assert 'Prioridade final:' in script
    assert 'não é sua porcentagem de acertos' in script
    assert 'O sistema marca somente o que já encontrou nos seus registros' in script
    assert 'Você escolhe a matéria e quando voltar' in script
    assert 'não cria uma obrigação diária' in script
    assert 'readableReason(topic.reason)' in script
    assert 'readableReason(q.reason)' in script
    assert 'Tente explicar sem consultar antes de avaliar' not in script
    # Na v0.13 a fórmula está disponível sob expansão, sem alterar o algoritmo.
    assert '0,35D + 0,30T' in script
    assert 'Ajuste pelas dificuldades observadas no assunto' in script


def test_explicacao_nao_muda_estados_nem_prioridades(client):
    subject = client.post('/api/subjects', json={'name': 'Português'}).json()
    client.post('/api/topics', json={'subject_id': subject['id'], 'title': 'Crase'})
    row = client.get(f'/api/queue?subject_id={subject["id"]}').json()['topics'][0]
    assert row['learning_state'] == 'em_aprendizagem'
    assert row['mastered'] is False
    assert row['priority'] >= 0
    assert row['ranking_score'] >= row['priority']
