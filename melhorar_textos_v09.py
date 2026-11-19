#!/usr/bin/env python3
"""Reescreve explicações da v0.9 para português claro, sem mudar o algoritmo.

Na raiz do clone estudo-adaptativo:
    python melhorar_textos_v09.py
    python -m pytest -q

Cópias de segurança ficam no computador (.antes-textos.bak), sem tocar no banco.
O script NÃO executa git push nem deploy.
"""
from pathlib import Path
from shutil import copy2
import re

ROOT = Path.cwd()
MARKER = '/* explicacoes claras v0.9.1 */'

JS_REPLACEMENT = r'''/* explicacoes claras v0.9.1 */
// Todos os números de prioridade organizam a fila: NÃO são taxas de acerto.
const displayNumber = n => n == null || !Number.isFinite(Number(n)) ? '—' :
  Number(n).toLocaleString('pt-BR', {minimumFractionDigits:1, maximumFractionDigits:1});
const dayLabel = n => `${n} ${Number(n) === 1 ? 'dia' : 'dias'}`;
const STATE_LABELS = {em_aprendizagem:'Em aprendizagem',em_consolidacao:'Em consolidação',dominado:'Dominado'};

function priority(entry) {
  const score = Number(entry.ranking_score ?? entry.priority ?? 0);
  return score >= 58 ? 'Alta' : score >= 38 ? 'Média' : 'Baixa';
}
function dateInfo(entry) {
  if (entry.days_since == null) return 'Sem revisão anterior registrada';
  if (entry.learning_state && !entry.attempts) return 'Estudo inicial registrado; ainda sem revisão';
  if (entry.days_since < 1) return 'Última avaliação: hoje';
  const days = Math.floor(entry.days_since);
  return `Última avaliação: há ${dayLabel(days)}`;
}
function riskDescription(entry) {
  if (entry.forgetting_risk_percent == null) return 'Esquecimento: ainda sem histórico para estimar';
  const names = {alto:'alto',moderado:'moderado',baixo:'baixo'};
  return `Esquecimento: risco ${names[entry.forgetting_risk_level] || 'estimado'} (estimativa)`;
}
function meta(entry) {
  const score = entry.ranking_score ?? entry.priority;
  const status = entry.maintenance_required ? 'Prazo de revisão alcançado nesta matéria' :
    entry.learning_state ? `Progresso: ${STATE_LABELS[entry.learning_state] || 'Em aprendizagem'}` :
    entry.attempts ? 'Questão em acompanhamento' : 'Questão ainda sem reavaliação';
  return `<div class="priority-line">
    <span><strong>Prioridade ${priority(entry)} · ${displayNumber(score)} de 100</strong></span>
    <span>${esc(status)}</span>
    <span>${esc(dateInfo(entry))}</span>
    <span>${esc(riskDescription(entry))}</span>
  </div>`;
}
function stateDescription(entry, evidence) {
  if (entry.learning_state === 'dominado') {
    return 'Você reuniu todas as evidências de domínio que o sistema acompanha. O assunto permanece na fila para revisões de manutenção, mesmo depois de dominado.';
  }
  if (entry.learning_state === 'em_consolidacao') {
    return 'Você já demonstrou progresso nas revisões. Ainda faltam algumas evidências para confirmar que consegue manter esse conhecimento ao longo do tempo.';
  }
  if (!entry.attempts) {
    return 'Ainda não há revisões deste assunto registradas no sistema. Por enquanto, não existem dados suficientes para avaliar quanto você já domina.';
  }
  if (!evidence.no_critical_gaps) {
    return 'Seus registros ainda mostram alguma dificuldade conceitual importante ou um erro de conceito pendente. Por isso, o assunto permanece em aprendizagem.';
  }
  return 'Na última revisão, você ainda teve dificuldade para lembrar partes importantes do conteúdo. Esse estado descreve o histórico registrado, não sua capacidade ou sua nota na prova.';
}
function reviewDescription(entry) {
  const interval = Number(entry.interval_days) || 1;
  if (entry.days_since == null) {
    return `O sistema usa inicialmente ${dayLabel(interval)} como intervalo de referência, contado a partir do primeiro registro de estudo ou revisão.`;
  }
  if (entry.learning_state && !entry.attempts) {
    return `O intervalo inicial de ${dayLabel(interval)} é contado desde o estudo registrado. Você decide quando realizar a primeira revisão.`;
  }
  if (entry.maintenance_required) {
    return `O intervalo de referência de ${dayLabel(interval)} já foi alcançado. O assunto sobe na fila desta matéria, mas você não precisa estudá-lo hoje.`;
  }
  return `O intervalo atual de referência é de ${dayLabel(interval)} desde a última revisão. O assunto continua na fila, sem exigir um retorno diário.`;
}

// Apenas uma tradução dos motivos existentes: não sugere como responder à questão.
const REASON_TEXT = {
  'Assunto novo — primeira avaliação disponível': 'Você ainda não registrou revisões deste assunto.',
  'Primeira revisão após estudo inicial': 'Este assunto já foi estudado, mas ainda não tem uma revisão registrada.',
  'Primeira revisão programada': 'Este assunto está disponível para sua primeira revisão.',
  'Prazo de revisão atingido — prioridade nesta matéria': 'O intervalo de revisão chegou. Por isso, este item aparece antes dos que ainda estão dentro do prazo nesta matéria.',
  'Erro conceitual pendente — reforçar antes de avançar': 'Há uma dificuldade conceitual importante ou um erro de conceito ainda registrado como pendente.',
  'Domínio comprovado — manutenção espaçada': 'Os critérios de domínio foram atendidos. O assunto continua na fila para manutenção.',
  'Consolidação e revisões espaçadas': 'Você já registrou progresso, mas ainda faltam evidências para confirmar domínio.',
  'Questão dominada — considere arquivá-la': 'O histórico desta questão mostra acertos seguros e espaçados. O arquivamento está disponível se você desejar.',
  'Erros recorrentes — revisar o conceito': 'Esta questão foi errada em mais de uma das últimas tentativas.',
  'Acerto com chute — não consolidado': 'Você acertou na última tentativa, mas registrou pouca segurança na resposta.',
  'Questão ainda não reavaliada': 'Esta questão foi cadastrada, mas ainda não foi reavaliada aqui.',
  'Manutenção espaçada': 'Este item continua na fila para acompanhar como você retém o conhecimento com o tempo.'
};
function readableReason(reason) { return REASON_TEXT[reason] || reason || 'Item disponível para revisão.'; }

function masteryDetails(entry) {
  const e = entry.mastery_evidence, c = entry.priority_components;
  if (!e || !c) return '';
  const count = Number(e.distinct_questions) || 0;
  const attempts = Number(e.total_question_attempts) || 0;
  const accuracy = e.question_accuracy_percent == null ? 'ainda não calculado' : `${displayNumber(e.question_accuracy_percent)}%`;
  const checks = [
    ['three_grade_fours', 'Lembrar todo o conteúdo em três revisões seguidas (nota 4, sem lacunas importantes).'],
    ['spaced_recoveries', 'Fazer essas revisões em dias diferentes, aumentando os intervalos, com pelo menos 14 dias entre as duas últimas.'],
    ['varied_questions_90_percent', `Ter pelo menos 90% de acertos sem chutes nas questões diferentes do Caderno de erros vinculadas a este assunto. Registros atuais: ${count} ${count === 1 ? 'questão distinta' : 'questões distintas'}, ${attempts} ${attempts === 1 ? 'avaliação' : 'avaliações'} e ${accuracy} de acertos. O sistema exige ao menos 5 questões distintas e 8 avaliações.`],
    ['no_critical_gaps', 'Não ter lacunas importantes ou erros de conceito ainda registrados como pendentes.'],
    ['explained_without_consulting', 'Registrar uma revisão completa em que conseguiu explicar o assunto sem consultar o material.'],
    ['applied_to_new_questions', 'Confirmar, na revisão mais recente, que conseguiu aplicar o assunto em questões variadas, sem consulta.']
  ];
  const achieved = checks.filter(([key]) => Boolean(e[key])).length;
  const score = entry.ranking_score ?? entry.priority;
  const base = entry.priority;
  const riskBonus = Number(entry.risk_priority_bonus) || 0;
  const opportunityBonus = Number(entry.opportunity_priority_bonus) || 0;
  const values = [
    ['Dificuldade para lembrar', c.D, '35%'],
    ['Tempo desde a revisão', c.T, '30%'],
    ['Falhas registradas nas revisões', c.E, '25%'],
    ['Importância que você cadastrou', c.I, '10%']
  ];
  return `<details class="mastery-details">
    <summary>Entenda sua prioridade e seu progresso</summary>
    <div class="mastery-content">
      <section class="mastery-section mastery-state">
        <h4>Seu estado: ${esc(STATE_LABELS[entry.learning_state] || 'Em aprendizagem')}</h4>
        <p>${esc(stateDescription(entry, e))}</p>
      </section>
      <section class="mastery-section">
        <h4>Por que este assunto aparece nesta posição?</h4>
        <p><strong>Prioridade ${priority(entry).toLowerCase()}: ${displayNumber(score)} de 100.</strong> Essa nota serve apenas para organizar os assuntos <strong>dentro da matéria que você escolheu</strong>. Ela não é sua porcentagem de acertos nem uma previsão da nota na prova.</p>
        <p>O sistema observa a dificuldade das revisões, o tempo decorrido, os esquecimentos registrados e a importância cadastrada. Também faz pequenos ajustes com base no histórico disponível.</p>
      </section>
      <section class="mastery-section">
        <h4>Quando este assunto volta a ganhar prioridade?</h4>
        <p>${esc(reviewDescription(entry))}</p>
        <p>Você escolhe a matéria e quando voltar a estudá-la. Um prazo alcançado muda a ordem da fila, não cria uma obrigação diária.</p>
      </section>
      <section class="mastery-section">
        <h4>${entry.learning_state === 'dominado' ? 'Como o domínio foi confirmado?' : 'O que falta para ser considerado dominado?'}</h4>
        <p><strong>${achieved} de ${checks.length} critérios atendidos.</strong> O sistema marca somente o que já encontrou nos seus registros.</p>
        <ul class="mastery-checklist">${checks.map(([key, label]) => `<li class="${e[key] ? 'criterion-done' : 'criterion-pending'}"><span class="criterion-symbol" aria-hidden="true">${e[key] ? '✓' : '○'}</span><span><strong>${e[key] ? 'Atendido' : 'Ainda não comprovado'}:</strong> ${esc(label)}</span></li>`).join('')}</ul>
        <p class="mastery-note">As questões do Caderno de erros já foram erradas anteriormente. O percentual acima se refere somente a esses registros, não às questões inéditas nem ao seu desempenho geral na prova.</p>
      </section>
      <details class="calculation-details">
        <summary>Ver os números usados no cálculo</summary>
        <p>A nota inicial reúne quatro informações. Os percentuais abaixo indicam a participação de cada informação no cálculo, <strong>não o peso da matéria na prova</strong>.</p>
        <dl class="calculation-list">${values.map(([label, value, weight]) => `<div><dt>${esc(label)} <small>(peso de ${weight})</small></dt><dd>${displayNumber(value)} de 100</dd></div>`).join('')}</dl>
        <p><strong>Nota inicial:</strong> ${displayNumber(base)} de 100.</p>
        <p><strong>Ajuste por risco de esquecimento:</strong> +${displayNumber(riskBonus)} ponto(s) (máximo de 8).</p>
        <p><strong>Ajuste pelas dificuldades observadas no assunto:</strong> +${displayNumber(opportunityBonus)} ponto(s) (máximo de 6).</p>
        <p><strong>Prioridade final:</strong> ${displayNumber(score)} de 100. O resultado nunca ultrapassa 100.</p>
        <p>O indicador de esquecimento é uma estimativa aproximada baseada no histórico, não uma probabilidade comprovada de esquecer.</p>
      </details>
    </div>
  </details>`;
}
'''

CSS_APPEND = '''
/* Texto explicativo acessível dos Cards — mantém o algoritmo intacto. */
.mastery-details{color:#283650;background:#fff;border-color:#dce4ef}
.mastery-details summary{list-style-position:inside;line-height:1.45;color:#334e93}
.mastery-content{display:grid;gap:16px;padding:12px 1px 3px}
.mastery-section{padding:0 0 15px;border-bottom:1px solid #e5eaf3}
.mastery-section:last-of-type{border-bottom:0;padding-bottom:0}
.mastery-section h4{font-size:14px;line-height:1.4;color:#273650;margin:0 0 7px;font-weight:750}
.mastery-section p,.calculation-details p{font-size:13px;line-height:1.65;color:#54637b;margin:7px 0}
.mastery-state{border-left:3px solid #8ca0dc;padding-left:12px}
.mastery-checklist{list-style:none;display:grid;gap:10px;margin:12px 0 10px;padding:0}
.mastery-checklist li{display:flex;gap:9px;align-items:flex-start;font-size:12.5px;line-height:1.55;color:#41516a}
.criterion-symbol{min-width:18px;text-align:center;font-size:17px;line-height:1.25}
.criterion-done .criterion-symbol{color:#25724b}
.criterion-pending .criterion-symbol{color:#8792a5}
.mastery-note{font-size:12px!important;color:#65768c!important}
.calculation-details{background:#f6f8fd;border:1px solid #e1e7f3;padding:12px 13px;border-radius:10px}
.calculation-details summary{color:#415580;font-size:12.5px;font-weight:700}
.calculation-list{margin:13px 0;display:grid;gap:7px}
.calculation-list>div{display:flex;align-items:baseline;justify-content:space-between;gap:14px;padding-bottom:6px;border-bottom:1px solid #e6ebf4}
.calculation-list dt,.calculation-list dd{font-size:12px;color:#475873;margin:0}
.calculation-list dd{font-weight:750;text-align:right;white-space:nowrap}
.calculation-list small{font-size:11px;color:#7d8aa0}
@media(max-width:540px){.calculation-list>div{flex-wrap:wrap;gap:2px}}
'''

def replace_once(src: str, old: str, new: str, name: str) -> str:
    n = src.count(old)
    if n != 1:
        raise RuntimeError(f'{name}: esperado 1 trecho, encontrados {n}: {old[:130]!r}')
    return src.replace(old, new, 1)


def transform_js(s: str) -> str:
    if MARKER in s:
        return s
    start = 'function priority(entry) {'
    end = 'function empty(title,description,command,label) {'
    assert s.count(start) == 1, 'Não foi possível localizar o início das explicações'
    assert s.count(end) == 1, 'Não foi possível localizar o fim das explicações'
    left, tail = s.split(start, 1)
    _removed, right = tail.split(end, 1)
    s = left + JS_REPLACEMENT + end + right
    s = replace_once(s,
        'esc(topic.reason)}. Tente explicar sem consultar antes de avaliar.',
        'esc(readableReason(topic.reason))}.', 'app.js — Card')
    s = replace_once(s,
        'esc(q.reason)}.',
        'esc(readableReason(q.reason))}.', 'app.js — questão')
    return s


def transform_css(s: str) -> str:
    if '.mastery-content{display:grid;' in s:
        return s
    return s + CSS_APPEND


def transform_html(s: str) -> str:
    # Este commit usa cache buster ?v=10. Mantemos versões independentes da API.
    s, ns = re.subn(r'(style\.css\?v=)(\d+)', lambda m: m.group(1) + str(max(int(m.group(2)), 10) + 1), s, count=1)
    if ns != 1:
        raise RuntimeError('index.html: não encontrei versão do CSS')
    s, nj = re.subn(r'(app\.js\?v=)(\d+)', lambda m: m.group(1) + str(max(int(m.group(2)), 10) + 1), s, count=1)
    if nj != 1:
        raise RuntimeError('index.html: não encontrei versão do JS')
    return s


def transform_test_mastery(s: str) -> str:
    old = "assert 'Entender prioridade e critérios de domínio' in script"
    new = "assert 'Entenda sua prioridade e seu progresso' in script"
    s = replace_once(s, old, new, 'test_priority_and_mastery_v6.py')
    old = "assert 'Prazo atingido nesta matéria' in script"
    new = "assert 'Prazo de revisão alcançado nesta matéria' in script"
    return replace_once(s, old, new, 'test_priority_and_mastery_v6.py')


def transform_test_cache(s: str, version: int) -> str:
    # Os testes antigos verificam o número exato da versão do asset.
    count = 0
    def repl(m):
        nonlocal count
        count += 1
        return '/static/app.js?v=' + str(version)
    s = re.sub(r'/static/app\.js\?v=\d+', repl, s)
    if count < 1:
        raise RuntimeError('Teste: não encontrei referência ao cache-buster do app.js')
    return s


TEST_NEW = '''"""A interface explica o progresso em linguagem comum sem alterar o algoritmo."""


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
    assert '0,35D + 0,30T' not in script
    assert 'Ajuste pelas dificuldades observadas no assunto' in script


def test_explicacao_nao_muda_estados_nem_prioridades(client):
    subject = client.post('/api/subjects', json={'name': 'Português'}).json()
    client.post('/api/topics', json={'subject_id': subject['id'], 'title': 'Crase'})
    row = client.get(f'/api/queue?subject_id={subject["id"]}').json()['topics'][0]
    assert row['learning_state'] == 'em_aprendizagem'
    assert row['mastered'] is False
    assert row['priority'] >= 0
    assert row['ranking_score'] >= row['priority']
'''


def main():
    if not (ROOT / 'app/static/app.js').exists() or not (ROOT / 'app/engine.py').exists():
        raise SystemExit('Abra o terminal na raiz de estudo-adaptativo antes de executar.')
    js_path = ROOT / 'app/static/app.js'
    current = js_path.read_text(encoding='utf-8')
    if MARKER in current:
        print('Os textos já foram atualizados nesta pasta. Nada foi alterado.')
        return
    if "currentTab: 'performance'" not in current:
        raise RuntimeError('A versão encontrada não é a v0.9 esperada. Nenhum arquivo foi alterado.')
    specs = {
        'app/static/app.js': transform_js,
        'app/static/style.css': transform_css,
        'app/static/index.html': transform_html,
        '.gitignore': lambda text: text if '*.antes-textos.bak' in text else text + '\n# Copias locais feitas pela revisao de linguagem\n*.antes-textos.bak\n',
        'tests/test_priority_and_mastery_v6.py': transform_test_mastery,
    }
    files = {}
    for rel, fn in specs.items():
        p = ROOT / rel
        files[rel] = fn(p.read_text(encoding='utf-8'))
    match = re.search(r'/static/app\.js\?v=(\d+)', files['app/static/index.html'])
    version = int(match.group(1))
    for rel in ('tests/test_semi_novel_risk_v8.py', 'tests/test_catalog_management_v5.py'):
        files[rel] = transform_test_cache((ROOT / rel).read_text(encoding='utf-8'), version)
    newtest = ROOT / 'tests/test_explicacoes_v09.py'
    if newtest.exists():
        raise RuntimeError('O arquivo tests/test_explicacoes_v09.py já existe. Nenhum arquivo alterado.')
    # Só alteramos os originais DEPOIS de validar todas as âncoras.
    for rel, result in files.items():
        target = ROOT / rel
        backup = target.with_name(target.name + '.antes-textos.bak')
        if not backup.exists():
            copy2(target, backup)
        target.write_text(result, encoding='utf-8')
        print('Atualizado:', rel)
    newtest.write_text(TEST_NEW, encoding='utf-8')
    print('Novo teste:', newtest.relative_to(ROOT))
    print('Concluído localmente. Rode: python -m pytest -q')
    print('Este script NÃO realizou push nem deploy.')

if __name__ == '__main__':
    main()
