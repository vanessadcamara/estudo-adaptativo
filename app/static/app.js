/* v0.13 — retenção estruturada e duas escalas de diversificação. */
'use strict';
const state = {
  csrf: null, session: null, lastRefreshAt: null,
  subjects: [], allSubjects: [], topics: [], allTopics: [], allQuestions: [], novelRecords: [], performance: null,
  cardsQueue: {topics: [], questions: []}, errorsQueue: {topics: [], questions: []},
  currentTab: 'performance', settingsTab: 'cards', cardsSubject: '', errorsSubject: '',
  activeTopicId: null, questionIndex: 0, queueRequest: {cards: 0, errors: 0},
  skippedTopics: new Set(), reviewedTopics: new Set(), answeredQuestions: new Set(),
  reviewTopicId: null, attemptQuestionId: null,
};
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const titleOf = topic => `${topic.code ? topic.code + ' · ' : ''}${topic.title}`;
const nameOf = id => state.allSubjects.find(s => s.id === id)?.name || 'Sem matéria';
function notice(text, isError = false) {
  const node = $('message'); node.hidden = false;
  node.className = `message${isError ? ' error' : ''}`; node.textContent = text;
}
async function safe(action) {
  try { await action(); }
  catch (error) { console.error('Falha na ação:', error); notice(error.message || 'Erro inesperado. Tente novamente.', true); }
}
async function api(path, method='GET', payload) {
  const result = await fetch(`/api${path}`, {
    method, credentials:'same-origin',
    headers: {'Content-Type':'application/json', ...(method === 'GET' ? {} : {'X-CSRF-Token': state.csrf})},
    body: payload === undefined ? undefined : JSON.stringify(payload),
    cache: 'no-store',
  });
  const data = await result.json().catch(() => ({}));
  if (result.status === 401) { window.location.replace('/login'); throw new Error('Sua sessão expirou. Entre novamente.'); }
  if (!result.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d=>d.msg).join('; ') : 'Não foi possível salvar.');
  }
  return data;
}
function showDialog(id) { const dialog = $(id); if (!dialog.open) dialog.showModal(); }
function closeDialog(id) { const dialog = $(id); if (dialog.open) dialog.close(); }
function goTo(tab, subtab = state.settingsTab, writeHash = true) {
  state.currentTab = tab; state.settingsTab = subtab;
  for (const name of ['performance', 'cards', 'errors', 'novel', 'settings']) {
    const active = name === tab;
    $(`tab-${name}`).hidden = !active;
    const button = $(`tab-button-${name}`);
    button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active));
  }
  for (const name of ['cards', 'errors']) {
    const active = name === subtab;
    $(`settings-${name}`).hidden = !active;
    const button = $(`settings-button-${name}`);
    button.classList.toggle('active', active); button.setAttribute('aria-selected', String(active));
  }
  if (writeHash) {
    const route = tab === 'settings' ? `#configuracoes/${subtab}` : tab === 'errors' ? '#caderno' : tab === 'novel' ? '#ineditas' : tab === 'cards' ? '#cards' : '#desempenho';
    if (window.location.hash !== route) window.history.replaceState(null, '', route);
  }
}
function parseRoute() {
  const hash = location.hash;
  if (hash.startsWith('#configuracoes')) goTo('settings', hash.endsWith('/errors') ? 'errors' : 'cards', false);
  else if (hash === '#caderno') goTo('errors', 'cards', false);
   else if (hash === '#ineditas') goTo('novel', 'cards', false);
   else if (hash === '#cards') goTo('cards', 'cards', false);
   else goTo('performance', 'cards', false);
}
function selectOptions(entries, placeholder, includeEmpty = true) {
  return `${includeEmpty ? `<option value="">${esc(placeholder)}</option>` : ''}${entries.map(x=>`<option value="${x.id}">${esc(x.label)}</option>`).join('')}`;
}
function updateSelect(id, html, fallback='') {
  const element = $(id), before = element.value;
  element.innerHTML = html;
  element.value = before || fallback;
  if (element.selectedIndex < 0) element.value = fallback;
}
function updateOptions() {
  const active = state.subjects.map(s=>({id:s.id,label:s.name}));
  // Nenhum assunto de outra matéria entra na fila: escolha explícita.
  updateSelect('cardsSubject', selectOptions(active,'Escolha uma matéria'),state.cardsSubject);
  updateSelect('errorsSubject', selectOptions(active,'Escolha uma matéria') + '<option value="unassigned">Sem matéria (legado)</option>',state.errorsSubject);
  state.cardsSubject = $('cardsSubject').value || '';
  state.errorsSubject = $('errorsSubject').value || '';
  updateSelect('topicSubjectFilter', '<option value="all">Todas as matérias</option>'+selectOptions(state.allSubjects.map(s=>({id:s.id,label:s.name})),'',false),'all');
  updateSelect('subjectSelect', selectOptions(active, 'Selecione a matéria'));
  updateSelect('questionSubject', selectOptions(active, 'Selecione a matéria'));
  updateSelect('novelSubject', selectOptions(active, 'Selecione a matéria'));
  updateSelect('performanceSubject', '<option value="all">Todas as matérias</option>'+selectOptions(active,'',false),'all');
  updateQuestionTopics();
}
function updateQuestionTopics(selected=null) {
  const id = Number($('questionSubject').value);
  const topics = state.topics.filter(t=>t.subject_id === id).map(t=>({id:t.id,label:titleOf(t)}));
  updateSelect('questionTopic', selectOptions(topics,'Sem assunto específico'));
  if (selected != null && topics.some(t=>t.id===selected)) $('questionTopic').value = String(selected);
}
const emptyQueue = () => ({topics: [], questions: []});
async function loadSelectedQueue(kind) {
  const subject = kind === 'cards' ? state.cardsSubject : state.errorsSubject;
  const request = ++state.queueRequest[kind];
  const key = kind === 'cards' ? 'cardsQueue' : 'errorsQueue';
  if (!subject) {state[key]=emptyQueue(); return;}
  const subjectId = subject === 'unassigned' ? 0 : Number(subject);
  const route = state.session ? `/sessions/${state.session.id}/queue` : "/queue";
  const queue = await api(`${route}?subject_id=${subjectId}`);
  // Uma resposta antiga nunca substitui a fila após trocar rapidamente a matéria.
  if (state.queueRequest[kind] === request &&
      (kind === 'cards' ? state.cardsSubject : state.errorsSubject) === subject) state[key]=queue;
}
async function reloadAll({preserveQuestion=true}={}) {
  const oldQuestion = preserveQuestion ? visibleQuestions()[state.questionIndex]?.id : null;
  const [allSubjects,allTopics,allQuestions,openSession,novelRecords,performance,dashboard] = await Promise.all([
    api('/subjects?include_archived=true'),api('/topics?include_archived=true'),
    api('/questions?include_archived=true'),api('/sessions/open'),
    api('/novel-practice?include_archived=true'),api('/performance'),api('/dashboard'),
  ]);
  state.allSubjects=allSubjects;state.allTopics=allTopics;state.allQuestions=allQuestions;
  state.novelRecords=novelRecords;state.performance=performance;
  state.subjects=allSubjects.filter(s=>!s.archived_at);
  state.topics=allTopics.filter(t=>!t.archived_at && state.subjects.some(s=>s.id===t.subject_id));
  state.session=openSession;
  state.lastRefreshAt=dashboard.recent_sessions?.[0]?.refreshed_at || null;
  renderRefreshInfo();
  if (openSession) {
    const progress=await api(`/sessions/${openSession.id}/progress`);
    state.reviewedTopics = new Set(progress.topics); state.answeredQuestions = new Set(progress.questions);
  } else {state.reviewedTopics = new Set();state.answeredQuestions = new Set();}
  updateOptions();renderCatalog();renderManagedQuestions();renderNovelRecords();renderPerformance();
  await Promise.all([loadSelectedQueue('cards'),loadSelectedQueue('errors')]);
  const updatedIndex = visibleQuestions().findIndex(q=>q.id===oldQuestion);
  state.questionIndex = updatedIndex >= 0 ? updatedIndex : 0;
  renderCards();renderQuestions();
}
function subjectsVisible() {return $('showArchivedCatalog').checked?state.allSubjects:state.subjects;}
function topicsVisible() {
  const collection = $('showArchivedCatalog').checked ? state.allTopics : state.topics;
  const filter=$('topicSubjectFilter').value;
  return collection.filter(t=>filter==='all' || String(t.subject_id)===filter);
}
function renderCatalog() {
  $('subjectsList').innerHTML = subjectsVisible().length ? subjectsVisible().map(s=>`<div class="list-item"><div class="item-text"><strong>${esc(s.name)}</strong><small>${state.allTopics.filter(t=>t.subject_id===s.id && !t.archived_at).length} assunto(s) ${s.archived_at?' · Arquivada':''}</small></div><div class="item-actions">${s.archived_at?'':`<button class="button quiet small" data-edit-subject="${s.id}">Editar</button>`}<button class="button ${s.archived_at?'quiet':'danger-outline'} small" data-archive-subject="${s.id}" data-value="${!s.archived_at}">${s.archived_at?'Restaurar':'Arquivar'}</button></div></div>`).join('') : '<p class="empty-list">Nenhuma matéria cadastrada. Clique em Nova matéria.</p>';
  $('topicsList').innerHTML = topicsVisible().length ? topicsVisible().map(t=>`<div class="list-item"><div class="item-text"><strong>${esc(titleOf(t))}</strong><small>${esc(nameOf(t.subject_id))} · importância ${t.importance}/5 ${t.archived_at?'· Arquivado':''}</small></div><div class="item-actions">${t.archived_at?'':`<button class="button quiet small" data-edit-topic="${t.id}">Editar</button>`}<button class="button ${t.archived_at?'quiet':'danger-outline'} small" data-archive-topic="${t.id}" data-value="${!t.archived_at}">${t.archived_at?'Restaurar':'Arquivar'}</button></div></div>`).join('') : '<p class="empty-list">Nenhum assunto nesta seleção. Clique em Novo assunto.</p>';
}
function renderManagedQuestions() {
  const archived=$('manageQuestionsFilter').value==='archived';
  const records=state.allQuestions.filter(q=>Boolean(q.archived_at)===archived);
  $('managedQuestionsList').innerHTML=records.length?records.map(q=>`<div class="list-item"><div class="item-text"><strong>${esc(q.url||q.statement?.slice(0,100)||`Questão ${q.id}`)}</strong><small>${esc(nameOf(q.subject_id))}</small></div><div class="item-actions">${q.archived_at?'':`<button type="button" class="button quiet small" data-edit-question="${q.id}">Editar</button>`}<button type="button" class="button ${q.archived_at?'quiet':'danger-outline'} small" data-archive-question="${q.id}" data-value="${!q.archived_at}">${q.archived_at?'Restaurar':'Arquivar'}</button></div></div>`).join(''):'<p class="empty-list">Nenhuma questão nessa lista.</p>';
}
function availableTopics(){return state.cardsQueue.topics.filter(t=>!state.reviewedTopics.has(t.id)&&!state.skippedTopics.has(t.id));}
function visibleQuestions(){return state.errorsQueue.questions;}
/* explicacoes claras v0.9.1 */
// Todos os números de prioridade organizam a fila: NÃO são taxas de acerto.
const displayNumber = n => n == null || !Number.isFinite(Number(n)) ? '—' :
  Number(n).toLocaleString('pt-BR', {minimumFractionDigits:1, maximumFractionDigits:1});
const dayLabel = n => `${n} ${Number(n) === 1 ? 'dia' : 'dias'}`;
const STATE_LABELS = {em_aprendizagem:'Em aprendizagem',em_consolidacao:'Em consolidação',dominado:'Dominado'};

// A pontuação de ordenação é RELATIVA à matéria; não existe classificação
// universal Alta/Média/Baixa quando a diversidade pode torná-la negativa.
function orderingScore(entry) {
  return entry.queue_order_score ?? entry.ranking_score ?? entry.priority;
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
  const score = orderingScore(entry);
  const status = entry.starvation_protected ? 'Retorno protegido após várias visitas à matéria' :
    entry.maintenance_required ? 'Prazo de revisão alcançado nesta matéria (preferência flexível)' :
    entry.learning_state ? `Progresso: ${STATE_LABELS[entry.learning_state] || 'Em aprendizagem'}` :
    entry.attempts ? 'Questão em acompanhamento' : 'Questão ainda sem reavaliação';
  return `<div class="priority-line">
    <span><strong>Ordenação: ${displayNumber(score)} pontos relativos</strong></span>
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
    return entry.days_since == null
      ? 'Ainda não há revisões deste assunto registradas no sistema. Por enquanto, não existem dados suficientes para avaliar quanto você já domina.'
      : 'O estudo inicial foi registrado, mas ainda não existe uma revisão espaçada. A lembrança logo após a aula não é evidência suficiente de retenção duradoura.';
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
  const delta = Number(entry.interval_adjustment_days) || 0;
  const adjustment = delta === 0 ? 'O histórico ainda não alterou esse prazo.' :
    `O histórico de recuperações ajustou o prazo-base de ${dayLabel(entry.base_interval_days)} para ${dayLabel(interval)}.`;
  if (entry.maintenance_required) {
    return `O intervalo de ${dayLabel(interval)} já foi alcançado. O item recebe preferência flexível, mas não supera automaticamente todos os outros. ${adjustment} Você escolhe quando voltar à matéria.`;
  }
  return `O intervalo de referência é de ${dayLabel(interval)} desde a última revisão. ${adjustment} O item continua disponível, sem exigir um retorno diário.`;
}

function rotationDescription(entry) {
  const short = Number(entry.recent_review_count_3_sessions) || 0;
  const long = Number(entry.recent_review_count_12_sessions) || 0;
  const visits = Number(entry.visits_without_review) || 0;
  const messages = [
    `Nas últimas 3 sessões com atividade desta matéria, o item foi avaliado em ${short}. Nas últimas 12, foi avaliado em ${long}.`,
    `Foram ${visits} sessões da matéria com atividade desde o último registro deste item.`,
  ];
  if (entry.starvation_protected) {
    messages.push('Retorno protegido: após 7 ou mais visitas sem revisão de um item elegível, ele vai à frente da fila da própria matéria. Isso não obriga você a estudar a matéria hoje.');
  } else if (Number(entry.long_term_fairness_bonus) > 0) {
    messages.push('Foi aplicado um bônus de equilíbrio para dar mais oportunidade a itens pouco revisitados no longo prazo.');
  } else {
    messages.push('A alternância considera a repetição recente, sem obrigar a revisão de itens ainda estáveis.');
  }
  if (Number(entry.overdue_protection_strength) > 0) {
    messages.push('O atraso acumulado reduziu a penalização por repetição para proteger a retenção.');
  }
  return messages.join(' ');
}

function orderingCalculation(entry, card=false) {
  const risk = Number(entry.risk_priority_bonus) || 0;
  const opportunity = Number(entry.opportunity_priority_bonus) || 0;
  const score = orderingScore(entry);
  const prefix = card
    ? `<p><strong>Fórmula-base dos Cards:</strong> P = 0,35D + 0,30T + 0,25E + 0,10I (componentes entre 0 e 100).</p>`
    : `<p><strong>Caderno de erros:</strong> pontuação própria com erros, acertos, confiança, repetição e tempo. Não usa a fórmula dos Cards.</p>`;
  return `${prefix}
    <p><strong>Nota inicial:</strong> ${displayNumber(entry.priority)} de 100.</p>
    <p><strong>Risco de esquecimento:</strong> ajuste de até 8 pontos, aplicado com limite final de 100 (bônus calculado: +${displayNumber(risk)}).</p>
    ${card ? `<p><strong>Ajuste pelas dificuldades observadas no assunto:</strong> até 6 pontos (calculado: +${displayNumber(opportunity)}), limitado a 100.</p>` : ''}
    <p><strong>Prioridade final:</strong> ${displayNumber(entry.ranking_score)} de 100, antes da alternância e da proteção por retorno.</p>
    <p><strong>Preferência por vencimento:</strong> +${displayNumber(entry.due_order_bonus || 0)} ponto(s); não é prioridade absoluta.</p>
    <p><strong>Equilíbrio nas últimas 12 sessões:</strong> +${displayNumber(entry.long_term_fairness_bonus || 0)} ponto(s).</p>
    <p><strong>Redução por repetição recente (já considerando proteção por atraso):</strong> −${displayNumber(entry.diversification_penalty || 0)} ponto(s).</p>
    <p><strong>Redução por antecipação excessiva:</strong> −${displayNumber(entry.early_review_penalty || 0)} ponto(s).</p>
    <p><strong>Ordenação calculada:</strong> ${displayNumber(score)} pontos relativos. Pode ser negativa ou ultrapassar 100; isso não significa desempenho ou probabilidade de acertar.</p>
    ${entry.starvation_protected ? '<p><strong>Exceção de retorno:</strong> este item elegível aparece à frente dos não protegidos, mesmo quando sua pontuação relativa é menor. Por isso, a ordem não depende apenas da soma dos pontos.</p>' : ''}
    <p>Risco e intervalos são estimativas baseadas nos registros disponíveis; não são probabilidades de esquecimento comprovadas.</p>`;
}

// Apenas uma tradução dos motivos existentes: não sugere como responder à questão.
const REASON_TEXT = {
  'Assunto novo — primeira avaliação disponível': 'Você ainda não registrou revisões deste assunto.',
  'Primeira revisão após estudo inicial': 'Este assunto já foi estudado, mas ainda não tem uma revisão registrada.',
  'Primeira revisão programada': 'Este assunto está disponível para sua primeira revisão.',
  'Prazo de revisão atingido — prioridade nesta matéria': 'O intervalo de revisão chegou. O item recebe preferência, mas a diversificação e a proteção de retorno também influenciam a posição.',
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
    ['three_grade_fours', 'Recuperar corretamente o conteúdo em três revisões consecutivas (nota inferida 4, sem lacunas importantes).'],
    ['spaced_recoveries', 'Manter essas recuperações em dias distintos, com intervalos crescentes e pelo menos 14 dias entre as duas últimas.'],
    ['varied_questions_90_percent', `Atingir pelo menos 90% de acertos seguros nos links distintos do Caderno de erros vinculados a este assunto: ${count} questões distintas, ${attempts} avaliações e ${accuracy} de acertos registrados. São necessárias ao menos 5 questões distintas e 8 avaliações.`],
    ['no_critical_gaps', 'Não apresentar lacunas conceituais críticas pendentes.'],
    ['explained_without_consulting', 'Recuperar e explicar o assunto sem consulta ao material.'],
    ['applied_to_new_questions', 'Registrar aplicação em questões diferentes, sem consulta, na revisão mais recente.']
  ];
  const achieved = checks.filter(([key]) => Boolean(e[key])).length;
  const values = [
    ['Dificuldade para lembrar', c.D, '35%'],
    ['Tempo desde a revisão', c.T, '30%'],
    ['Falhas registradas nas revisões', c.E, '25%'],
    ['Importância cadastrada', c.I, '10%']
  ];
  return `<details class="mastery-details">
    <summary>Entenda sua prioridade e seu progresso</summary>
    <div class="mastery-content">
      <section class="mastery-section mastery-state">
        <h4>Progresso do assunto: ${esc(STATE_LABELS[entry.learning_state] || 'Em aprendizagem')}</h4>
        <p>${esc(stateDescription(entry, e))}</p>
        <p>${entry.attempts} revisão(ões) registrada(s). ${achieved} de ${checks.length} evidências de domínio atendidas. O estado não representa a porcentagem do edital estudada nem a nota prevista na prova.</p>
      </section>
      <section class="mastery-section">
        <h4>Por que está nesta posição?</h4>
        <p><strong>Ordenação relativa: ${displayNumber(orderingScore(entry))} pontos.</strong> A pontuação não é sua porcentagem de acertos nem uma previsão da nota na prova. A pontuação combina urgência, risco e alternância somente na matéria escolhida.</p>
        <p>${esc(rotationDescription(entry))}</p>
      </section>
      <section class="mastery-section">
        <h4>Quando revisar novamente?</h4>
        <p>${esc(reviewDescription(entry))}</p>
        <p>Você escolhe a matéria e quando voltar a estudá-la. Um prazo alcançado não cria uma obrigação diária.</p>
      </section>
      <section class="mastery-section">
        <h4>${entry.learning_state === 'dominado' ? 'Como o domínio foi confirmado?' : 'O que falta para ser considerado dominado?'}</h4>
        <p><strong>${achieved} de ${checks.length} critérios atendidos.</strong> O sistema marca somente o que já encontrou nos seus registros.</p>
        <ul class="mastery-checklist">${checks.map(([key,label])=>`<li class="${e[key]?'criterion-done':'criterion-pending'}"><span class="criterion-symbol" aria-hidden="true">${e[key]?'✓':'○'}</span><span><strong>${e[key]?'Atendido':'Ainda não comprovado'}:</strong> ${esc(label)}</span></li>`).join('')}</ul>
        <p class="mastery-note">A autoavaliação é um indício; a retenção espaçada precisa ser observada após intervalos reais. Os links do Caderno de erros não são questões inéditas por assunto; o desempenho em inéditas permanece agregado por matéria.</p>
      </section>
      <details class="calculation-details">
        <summary>Ver a fórmula e todos os ajustes de ordenação</summary>
        <p>Os pesos a seguir são fixos na fórmula dos Cards; o botão de nova sessão não os modifica.</p>
        <dl class="calculation-list">${values.map(([label,value,weight])=>`<div><dt>${esc(label)} <small>(peso ${weight})</small></dt><dd>${displayNumber(value)} de 100</dd></div>`).join('')}</dl>
        ${orderingCalculation(entry, true)}
      </details>
    </div>
  </details>`;
}

function questionDetails(entry) {
  const rate = entry.attempts ? `${displayNumber(100 * entry.correct / entry.attempts)}%` : 'sem avaliações';
  const status = entry.archive_suggested
    ? 'Há indícios consistentes de acertos seguros espaçados; você pode arquivar a questão, se desejar.'
    : entry.attempts
      ? `Foram ${entry.attempts} tentativas registradas, ${entry.correct} acertos e ${entry.errors} erros (taxa histórica ${rate}). Um acerto inseguro não comprova retenção.`
      : 'Ainda não há tentativas registradas nesta questão. Não é possível avaliar retenção a partir do cadastro do link.';
  return `<details class="mastery-details">
    <summary>Entenda a prioridade e o histórico desta questão</summary>
    <div class="mastery-content">
      <section class="mastery-section">
        <h4>Seu progresso nesta questão</h4><p>${esc(status)}</p>
        <p>Esse histórico é do Caderno de erros, não é sua taxa de acerto em questões inéditas nem evidência de domínio da matéria inteira.</p>
      </section>
      <section class="mastery-section">
        <h4>Por que aparece nesta posição?</h4>
        <p><strong>Ordenação relativa: ${displayNumber(orderingScore(entry))} pontos.</strong> ${esc(rotationDescription(entry))}</p>
      </section>
      <section class="mastery-section">
        <h4>Quando esta questão volta?</h4>
        <p>${esc(reviewDescription(entry))}</p>
      </section>
      <details class="calculation-details"><summary>Ver os ajustes de ordenação</summary>${orderingCalculation(entry)}</details>
    </div>
  </details>`;
}

function empty(title,description,command,label) {return `<div class="empty-state"><h3>${esc(title)}</h3><p>${esc(description)}</p>${command?`<button type="button" class="button primary" data-action="${command}">${esc(label)}</button>`:''}</div>`;}
function renderCards() {
  const candidates=availableTopics();const all=state.cardsQueue.topics;
  const hasCatalogedTopics=state.topics.some(t=>String(t.subject_id)===state.cardsSubject);
  const topic=candidates.find(t=>t.id===state.activeTopicId)||candidates[0];
  if (!topic) {
    state.activeTopicId=null;
    $('topicStudyCard').innerHTML=!state.subjects.length?empty('Comece cadastrando sua primeira matéria','O banco ainda não tem matérias. Abra Configurações para cadastrar e depois adicione assuntos.','new-subject','Cadastrar matéria'):
      !state.cardsSubject?empty('Escolha a matéria que quer estudar','Cada matéria tem sua própria fila. Nenhum vencimento força você a escolher uma disciplina.'): 
      !hasCatalogedTopics?empty('Cadastre um assunto para começar','Sua matéria está cadastrada, mas ainda não há assuntos disponíveis na pilha.','new-topic','Cadastrar assunto'):
      empty('Você percorreu esta pilha','Os itens avaliados nesta sessão não reaparecem nela. Conclua a sessão para começar outra passagem com a fila recalculada; as revisões anteriores permanecem salvas.','refresh','Concluir sessão e iniciar outra');
    return;
  }
  state.activeTopicId=topic.id;
  $('topicStudyCard').innerHTML=`<article class="study-card"><div class="card-eyebrow">PRÓXIMO ASSUNTO RECOMENDADO</div><h3>${topic.code?`<span class="card-code">${esc(topic.code)}</span> `:''}${esc(topic.title)}</h3><p class="card-description">${esc(readableReason(topic.reason))}.</p>${meta(topic)}${masteryDetails(topic)}<div class="actions"><button type="button" class="button primary" data-action="finish-topic" data-id="${topic.id}">Avaliar recuperação</button><button type="button" class="button outline" data-action="new-content" data-id="${topic.id}">Registrar estudo inicial</button><button type="button" class="button outline" data-action="skip-topic" data-id="${topic.id}">Pular por agora</button></div></article>`;
}
function renderQuestions() {
  const progress=state.errorsQueue.semi_novel_progress;
  $('semiNovelProgress').textContent=!state.errorsSubject?'':!progress?'':
    progress.spaced_secure_percent==null
      ? `Questões semi-inéditas: ${progress.registered} cadastradas, ${progress.reviewed_in_app} reavaliadas. Acompanhamento de retenção começa após duas tentativas separadas por ≥ 7 dias.`
      : `Retenção em questões semi-inéditas: ${progress.spaced_secure}/${progress.spaced_distinct} links distintos com acerto seguro após ≥ 7 dias (${progress.spaced_secure_percent}%). Meta de referência: ${progress.target_percent}%. ${progress.sufficient_sample?'':'Amostra ainda pequena. '}${progress.trend_pp==null?'':`Variação observada entre períodos: ${progress.trend_pp>0?'+':''}${progress.trend_pp} p.p. `}Não prevê nota na prova.`;
  const questions=visibleQuestions();
  const hasCatalogedQuestions=state.allQuestions.some(q=>{
    const subject=q.subject_id || state.allTopics.find(t=>t.id===q.topic_id)?.subject_id || 0;
    const wanted=state.errorsSubject==='unassigned'?'0':state.errorsSubject;
    return !q.archived_at && String(subject)===String(wanted);
  });
  if (state.questionIndex>=questions.length)state.questionIndex=Math.max(0,questions.length-1);
  const q=questions[state.questionIndex];
  $('questionPrevious').disabled=!q||state.questionIndex===0;
  $('questionNext').disabled=!q||state.questionIndex===questions.length-1;
  $('questionPosition').textContent=q?`${state.questionIndex+1} de ${questions.length}`:'Sem questões';
  if(!q){$('questionStudyCard').innerHTML=!state.errorsSubject?empty('Escolha a matéria do caderno de erros','Os vencimentos só ordenam questões da matéria que você selecionar.'):
    hasCatalogedQuestions?empty('Questões desta sessão concluídas','As questões já avaliadas ficam fora desta sessão. Para uma nova passagem, conclua a sessão e atualize a fila.','refresh','Concluir sessão e iniciar outra'):
    empty('Seu caderno está vazio nesta matéria','Cadastre o link de uma questão errada nessa matéria para começar a revisão.','new-question','Adicionar questão');return;}
  const done=state.answeredQuestions.has(q.id);
  $('questionStudyCard').innerHTML=`<article class="study-card"><div class="card-eyebrow">LINK RECOMENDADO · ${state.questionIndex+1}/${questions.length}</div><h3>${esc(q.statement?q.statement.slice(0,150):'Retome esta questão')}</h3><p class="card-description">${esc(readableReason(q.reason))}.</p>${q.url?`<a class="link-question" href="${esc(q.url)}" target="_blank" rel="noopener noreferrer">Abrir link da questão ↗</a>`:''}${q.statement&&q.statement.length>150?`<p class="statement">${esc(q.statement)}</p>`:''}${meta(q)}${questionDetails(q)}${q.archive_suggested?`<div class="suggestion"><strong>Arquivamento sugerido</strong><p>${esc(q.archive_reason||'Você demonstrou domínio consistente.')}</p></div>`:''}<div class="actions"><button type="button" class="button primary" data-action="assess-question" data-id="${q.id}" ${done?'disabled':''}>${done?'Avaliação salva':'Avaliar desempenho'}</button><button type="button" class="button outline" data-action="archive-question" data-id="${q.id}">${q.archive_suggested?'Arquivar link recomendado':'Arquivar link'}</button></div>${done?'<p class="helper">Esta questão já foi avaliada nesta sessão. Para iniciar outra passagem, conclua a sessão; o histórico continuará salvo.</p>':''}</article>`;
}

// v0.9 — apenas resultados observados. Nenhuma tentativa agregada é atribuída a um assunto.
const localToday = () => {
  const d=new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
};
const pct = n => n == null ? '—' : `${Number(n).toFixed(1).replace('.',',')}%`;
const ciText = range => range ? `Faixa de Wilson 95%: ${pct(range.low)}–${pct(range.high)} (amostra declarada; não garante representatividade)` : 'Sem amostra para estimar incerteza';

function renderPerformance(){
  const report=state.performance||{subjects:[],topics:[]};
  const selected=$('performanceSubject').value || 'all';
  const subjects=report.subjects.filter(x=>selected==='all'||String(x.id)===selected);
  const topics=report.topics.filter(x=>selected==='all'||String(x.subject_id)===selected);
  $('performanceSubjects').innerHTML=subjects.length?subjects.map(x=>`<article class="v09-metric">
    <h4>${esc(x.name)}</h4><div class="big-number">${pct(x.accuracy_percent)}</div>
    <div class="helper">${x.total ? `${x.correct} acertos em ${x.total} questões inéditas declaradas · ${x.records} registro(s)` : 'Nenhuma questão inédita registrada'}</div>
    <p class="panel-help">${esc(ciText(x.interval_95))}</p>
    ${x.accuracy_percent != null?`<p class="panel-help">${x.observed_target_met?'Meta observada de 90% atingida na amostra':'Abaixo de 90% na amostra registrada'}</p>`:''}
    <p class="panel-help">Cobertura dos assuntos cadastrados: ${x.reviewed_topics}/${x.registered_topics} revisados (não equivale à cobertura de todo o edital).</p>
    <p class="panel-help">Revisões com intervalo real de pelo menos 7 dias: ${x.spaced_recall_7d?.samples||0}; recuperação completa sem lacunas: ${x.spaced_recall_7d?.strong_recall||0}. Não é teste independente.</p>
    <p class="panel-help">Questões em condições de prova declaradas: ${x.exam_like?.total||0} · ${pct(x.exam_like?.accuracy_percent)} de acertos. Exige condições de prova, ausência de consulta e questões diferentes.</p>
  </article>`).join(''):'<p class="v09-empty">Cadastre uma matéria em Configurações para começar.</p>';
  $('performanceTopics').innerHTML=topics.length?topics.map(t=>`<div class="list-item">
    <div class="v09-topic-info"><strong>${t.code?esc(t.code)+' · ':''}${esc(t.title)}</strong>
      <small>${esc(nameOf(t.subject_id))} · ${esc(STATE_LABELS[t.learning_state]||'Em aprendizagem')}${t.mastered?' · manutenção espaçada':''}</small>
      <small>${t.reviews} revisão(ões) de Cards · ${t.distinct_links} link(s) distintos avaliados</small>
    </div>
    <div class="v09-topic-value"><strong>${pct(t.qualified_accuracy_percent)}</strong>
      <span>${t.distinct_links?`${t.qualified_correct}/${t.distinct_links} acertos sem chute; ${esc(ciText(t.interval_95))}`:'Sem evidência de questões vinculadas'}</span>
    </div>
  </div>`).join(''):'<p class="v09-empty">Nenhum assunto cadastrado nesta seleção.</p>';
  $('performanceDisclosure').textContent=report.note||'Não há dados suficientes para estimar o desempenho.';
}

function updateNovelPreview(){
  const total=Number($('novelTotal').value),correct=Number($('novelCorrect').value);
  const filled=$('novelTotal').value!==''&&$('novelCorrect').value!=='';
  const valid=filled&&Number.isInteger(total)&&Number.isInteger(correct)&&total>=1&&total<=10000&&correct>=0&&correct<=total;
  $('novelPreview').innerHTML=!filled?'Preencha as quantidades para calcular seu aproveitamento.':!valid?
    '<span>Confira as quantidades: acertos não podem superar o total e ambos precisam ser inteiros.</span>':
    `<strong>${pct(100*correct/total)}</strong> · ${correct} acerto(s) em ${total} questão(ões) · referência 90%.`;
}

function resetNovelForm(){
  $('novelForm').reset();$('novelEditId').value='';$('novelDate').value=localToday();
  $('novelFormTitle').textContent='Novo registro';$('novelSaveBtn').textContent='Salvar registro';
  $('novelCancel').hidden=true;updateNovelPreview();
}

function editNovel(id){
  const item=state.novelRecords.find(x=>x.id===id);
  if(!item||item.archived_at)return;
  $('novelEditId').value=String(item.id);
  $('novelDate').value=item.practice_date;
  $('novelSubject').value=String(item.subject_id);
  $('novelTotal').value=String(item.total);
  $('novelCorrect').value=String(item.correct);
  $('novelExamConditions').value=item.exam_conditions===null?'':String(item.exam_conditions);
  $('novelNoConsultation').value=item.no_consultation===null?'':String(item.no_consultation);
  $('novelDistinct').value=item.distinct_questions===null?'':String(item.distinct_questions);
  $('novelFormTitle').textContent='Corrigir registro';$('novelSaveBtn').textContent='Salvar correção';
  $('novelCancel').hidden=false;updateNovelPreview();
  goTo('novel');$('novelDate').focus();
}

function renderNovelRecords(){
  const showArchived=$('novelShowArchived').checked;
  const items=state.novelRecords.filter(x=>showArchived||!x.archived_at);
  $('novelRecordsList').innerHTML=items.length?items.map(x=>`<div class="list-item"><div class="item-text">
    <strong>${esc(x.practice_date)} · ${esc(nameOf(x.subject_id))}</strong>
    <small>${x.correct}/${x.total} acertos · ${pct(100*x.correct/x.total)}${x.archived_at?' · Excluído':''}</small></div>
    <div class="item-actions">${x.archived_at?`<button type="button" class="button quiet small" data-restore-novel="${x.id}">Restaurar</button>`:
      `<button type="button" class="button quiet small" data-edit-novel="${x.id}">Editar</button><button type="button" class="button danger-outline small" data-delete-novel="${x.id}">Excluir</button>`}</div>
  </div>`).join(''):'<p class="v09-empty">Nenhum registro nesta seleção. Registre suas questões inéditas acima.</p>';
}

function openSubject(id=null) {
  $('subjectForm').reset();const s=id==null?null:state.allSubjects.find(x=>x.id===id);
  $('subjectEditId').value=s?.id||'';$('subjectName').value=s?.name||'';
  $('subjectDialogTitle').textContent=s?'Editar matéria':'Nova matéria';showDialog('subjectDialog');
}
function openTopic(id=null) {
  if(!state.subjects.length) {goTo('settings','cards');notice('Primeiro cadastre uma matéria.');openSubject();return;}
  $('topicForm').reset();const t=id==null?null:state.allTopics.find(x=>x.id===id);
  $('topicEditId').value=t?.id||'';
  updateSelect('subjectSelect',selectOptions(state.subjects.map(s=>({id:s.id,label:s.name})),'Selecione a matéria'));
  $('subjectSelect').value=String(t?.subject_id||($('topicSubjectFilter').value!=='all'&&state.subjects.some(s=>String(s.id)===$('topicSubjectFilter').value)?$('topicSubjectFilter').value:''));
  $('topicTitle').value=t?.title||'';$('topicCode').value=t?.code||'';$('topicImportance').value=String(t?.importance||3);
  $('topicDialogTitle').textContent=t?'Editar assunto':'Novo assunto';showDialog('topicDialog');
}
function openQuestion(id=null) {
  if(!state.subjects.length){goTo('settings','cards');notice('Cadastre uma matéria antes de adicionar questões.');openSubject();return;}
  $('questionForm').reset();const q=id==null?null:state.allQuestions.find(x=>x.id===id);
  $('questionEditId').value=q?.id||'';$('questionSubject').value=String(q?.subject_id||'');
  $('questionUrl').value=q?.url||'';$('questionText').value=q?.statement||'';
  updateQuestionTopics(q?.topic_id);
  $('questionEditorTitle').textContent=q?'Editar questão':'Adicionar questão errada';showDialog('questionEditorDialog');
}
async function ensureSession(){if(!state.session)state.session=await api('/sessions','POST');return state.session;}
function renderRefreshInfo(){
  const fmt=iso=>{
    const date=new Date(iso);
    return Number.isNaN(date.getTime())?'':new Intl.DateTimeFormat('pt-BR', {
      day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'
    }).format(date);
  };
  const current=state.session ? `Sessão ${state.session.id} em andamento.` : 'Nenhuma sessão de avaliação aberta.';
  const last=state.lastRefreshAt ? ` Última conclusão: ${fmt(state.lastRefreshAt)}.` : '';
  for (const id of ['cardsRefreshInfo','errorsRefreshInfo']) $(id).textContent=current+last;
}
async function refresh() {
  // Os pesos são fixos. Este botão separa historicamente as sessões e refaz
  // as filas a partir dos registros já salvos, sem zerar os aprendizados.
  for(const id of ['cardsRefresh','errorsRefresh']) $(id).disabled=true;
  try {
    if(state.session) await api(`/sessions/${state.session.id}/refresh`,'POST');
    state.session = null;
    // A próxima sessão já fica aberta e pronta, sem esperar uma avaliação.
    state.session = await api('/sessions','POST');
    state.skippedTopics.clear();state.reviewedTopics.clear();state.answeredQuestions.clear();
    state.activeTopicId=null;state.questionIndex=0;
    await reloadAll({preserveQuestion:false});
    notice('Sessão anterior concluída. Nova sessão iniciada e recomendações atualizadas. Os pesos da fórmula e o histórico foram preservados.');
  } finally {
    for(const id of ['cardsRefresh','errorsRefresh']) $(id).disabled=false;
  }
}

async function afterChange(message) {await reloadAll({preserveQuestion:false});notice(message);}
async function archive(entity,id,archived){
  if(archived&&!window.confirm('Arquivar este item? Seu histórico continuará salvo e será possível restaurá-lo.'))return;
  await api(`/${entity}/${id}/archive`,'PATCH',{archived});
  state.activeTopicId=null;await afterChange(archived?'Arquivado com sucesso. Histórico mantido.':'Restaurado com sucesso.');
}

// Todos os botões globais são vinculados uma só vez; itens criados dinamicamente usam delegação.
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>goTo(b.dataset.tab)));
document.querySelectorAll('[data-settings-tab]').forEach(b=>b.addEventListener('click',()=>goTo('settings',b.dataset.settingsTab)));
window.addEventListener('hashchange',parseRoute);
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>closeDialog(b.dataset.close)));
$('newSubject').addEventListener('click',()=>openSubject());
$('newTopic').addEventListener('click',()=>openTopic());
$('newQuestion').addEventListener('click',()=>openQuestion());
$('showArchivedCatalog').addEventListener('change',renderCatalog);
$('topicSubjectFilter').addEventListener('change',renderCatalog);
$('manageQuestionsFilter').addEventListener('change',renderManagedQuestions);
$('questionSubject').addEventListener('change',()=>updateQuestionTopics());
$('cardsSubject').addEventListener('change',event=>safe(async()=>{state.cardsSubject=event.target.value;state.skippedTopics.clear();state.activeTopicId=null;state.cardsQueue=emptyQueue();renderCards();await loadSelectedQueue('cards');renderCards();}));
$('errorsSubject').addEventListener('change',event=>safe(async()=>{state.errorsSubject=event.target.value;state.questionIndex=0;state.errorsQueue=emptyQueue();renderQuestions();await loadSelectedQueue('errors');renderQuestions();}));
$('questionPrevious').addEventListener('click',()=>{if(state.questionIndex>0){state.questionIndex--;renderQuestions();}});
$('questionNext').addEventListener('click',()=>{if(state.questionIndex<visibleQuestions().length-1){state.questionIndex++;renderQuestions();}});
$('cardsRefresh').addEventListener('click',()=>safe(refresh));
$('errorsRefresh').addEventListener('click',()=>safe(refresh));

$('performanceSubject').addEventListener('change',renderPerformance);
$('novelCancel').addEventListener('click',resetNovelForm);
$('novelShowArchived').addEventListener('change',renderNovelRecords);
for(const id of ['novelTotal','novelCorrect'])$(id).addEventListener('input',updateNovelPreview);
$('novelForm').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  const id=$('novelEditId').value;
  const total=Number($('novelTotal').value), correct=Number($('novelCorrect').value);
  if(!Number.isInteger(total)||total<1||total>10000||!Number.isInteger(correct)||correct<0||correct>total)
    throw new Error('Informe quantidades inteiras e acertos entre 0 e o total.');
  if(!$('novelSubject').value||!$('novelDate').value)throw new Error('Informe a data e a matéria.');
  const optionalBool=id=>$(id).value===''?null:$(id).value==='true';
  const payload={subject_id:Number($('novelSubject').value),practice_date:$('novelDate').value,total,correct,
    exam_conditions:optionalBool('novelExamConditions'),no_consultation:optionalBool('novelNoConsultation'),
    distinct_questions:optionalBool('novelDistinct')};
  await api(id?`/novel-practice/${id}`:'/novel-practice',id?'PATCH':'POST',payload);
  await reloadAll();resetNovelForm();notice(id?'Registro de inéditas corrigido.':'Questões inéditas registradas.');
});});
$('logoutBtn').addEventListener('click',()=>safe(async()=>{await api('/auth/logout','POST');window.location.replace('/login');}));

document.addEventListener('click',event=>{
  const el=event.target.closest('button[data-action],button[data-edit-subject],button[data-edit-topic],button[data-edit-question],button[data-archive-subject],button[data-archive-topic],button[data-archive-question],button[data-edit-novel],button[data-delete-novel],button[data-restore-novel]');
  if(!el)return;
  if(el.dataset.editNovel){editNovel(Number(el.dataset.editNovel));return;}
  if(el.dataset.deleteNovel){safe(async()=>{if(!window.confirm('Excluir este registro de inéditas? Ele poderá ser restaurado.'))return;await api(`/novel-practice/${Number(el.dataset.deleteNovel)}`,'DELETE');await reloadAll();resetNovelForm();notice('Registro excluído; histórico preservado.');});return;}
  if(el.dataset.restoreNovel){safe(async()=>{await api(`/novel-practice/${Number(el.dataset.restoreNovel)}/restore`,'PATCH');await reloadAll();notice('Registro restaurado.');});return;}
  if(el.dataset.editSubject){openSubject(Number(el.dataset.editSubject));return;}
  if(el.dataset.editTopic){openTopic(Number(el.dataset.editTopic));return;}
  if(el.dataset.editQuestion){openQuestion(Number(el.dataset.editQuestion));return;}
  if(el.dataset.archiveSubject){safe(()=>archive('subjects',Number(el.dataset.archiveSubject),el.dataset.value==='true'));return;}
  if(el.dataset.archiveTopic){safe(()=>archive('topics',Number(el.dataset.archiveTopic),el.dataset.value==='true'));return;}
  if(el.dataset.archiveQuestion){safe(()=>archive('questions',Number(el.dataset.archiveQuestion),el.dataset.value==='true'));return;}
  const id=Number(el.dataset.id);
  switch(el.dataset.action){
    case 'new-subject':goTo('settings','cards');openSubject();break;
    case 'new-topic':goTo('settings','cards');openTopic();break;
    case 'new-question':goTo('settings','errors');openQuestion();break;
    case 'refresh':safe(refresh);break;
    case 'skip-topic':state.skippedTopics.add(id);state.activeTopicId=null;renderCards();break;
    case 'new-content': {
      const topic=state.cardsQueue.topics.find(t=>t.id===id);if(!topic)return;
      state.reviewTopicId=id;$('newContentFeedback').reset();$('newContentContext').textContent=topic.title;
      showDialog('newContentDialog');break;
    }
    case 'finish-topic': {
      const topic=state.cardsQueue.topics.find(t=>t.id===id);if(!topic)return;
      state.reviewTopicId=id;$('topicFeedback').reset();$('reviewContext').textContent=topic.title;
      showDialog('reviewDialog');break;
    }
    case 'assess-question': {
      const q=state.errorsQueue.questions.find(t=>t.id===id);if(!q||state.answeredQuestions.has(id))return;
      state.attemptQuestionId=id;$('questionFeedback').reset();$('attemptContext').textContent=q.statement?.slice(0,140)||q.url||`Questão ${id}`;
      showDialog('attemptDialog');break;
    }
    case 'archive-question':safe(()=>archive('questions',id,true));break;
  }
});

$('subjectForm').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  const id=$('subjectEditId').value;const data={name:$('subjectName').value.trim()};
  await api(id?`/subjects/${id}`:'/subjects',id?'PATCH':'POST',data);
  closeDialog('subjectDialog');await afterChange(id?'Matéria atualizada.':'Matéria salva. Agora cadastre um assunto para criar seus Cards.');
});});
$('topicForm').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  const id=$('topicEditId').value;
  await api(id?`/topics/${id}`:'/topics',id?'PATCH':'POST',{
    subject_id:Number($('subjectSelect').value),title:$('topicTitle').value.trim(),code:$('topicCode').value.trim()||null,importance:Number($('topicImportance').value),
  });
  closeDialog('topicDialog');await afterChange(id?'Assunto atualizado.':'Assunto incluído na pilha de Cards.');
});});
$('questionForm').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  const id=$('questionEditId').value,url=$('questionUrl').value.trim(),statement=$('questionText').value.trim();
  if(!url&&!statement)throw new Error('Informe o link ou o enunciado da questão.');
  await api(id?`/questions/${id}`:'/questions',id?'PATCH':'POST',{
    subject_id:Number($('questionSubject').value),topic_id:$('questionTopic').value?Number($('questionTopic').value):null,url:url||null,statement:statement||null,
  });
  closeDialog('questionEditorDialog');await afterChange(id?'Questão atualizada.':'Questão salva no caderno de erros.');
});});
$('topicFeedback').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  const data=new FormData(event.currentTarget),session=await ensureSession();
  const saved=await api(`/sessions/${session.id}/topic-reviews`,'POST',{
    topic_id:state.reviewTopicId,difficulty:Number(data.get('difficulty')),
    recall_level:Number(data.get('recall_level')),
    accuracy_level:Number(data.get('accuracy_level')),
    assistance_level:Number(data.get('assistance_level')),
    gap_level:Number(data.get('gap_level')),
    applied_to_new_questions:data.get('applied_to_new_questions')==='on',
    notes:String(data.get('notes')||'').trim()||null,
  });
  closeDialog('reviewDialog');state.activeTopicId=null;await afterChange(`Revisão registrada: nota inferida ${saved.inferred_grade}/4. Fila atualizada.`);
});});
$('newContentFeedback').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  const data=new FormData(event.currentTarget),session=await ensureSession();
  await api(`/sessions/${session.id}/new-content`,'POST',{
    topic_id:state.reviewTopicId,
    minutes:data.get('minutes')?Number(data.get('minutes')):null,
    recall_level:Number(data.get('recall_level')),
    accuracy_level:Number(data.get('accuracy_level')),
    gap_level:Number(data.get('gap_level')),
    notes:String(data.get('notes')||'').trim()||null,
  });
  closeDialog('newContentDialog');state.activeTopicId=null;
  await afterChange('Estudo inicial registrado. A retenção será observada em uma revisão futura.');
});});
$('questionFeedback').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  const data=new FormData(event.currentTarget),session=await ensureSession();
  await api(`/sessions/${session.id}/question-attempts`,'POST',{
    question_id:state.attemptQuestionId,is_correct:data.get('is_correct')==='true',confidence:Number(data.get('confidence')),
    error_type:data.get('is_correct')==='false'&&data.get('error_type')?String(data.get('error_type')):null,
    notes:String(data.get('notes')||'').trim()||null,
  });
  closeDialog('attemptDialog');await reloadAll({preserveQuestion:false});
  const next=visibleQuestions().findIndex(q=>q.id!==state.attemptQuestionId&&!state.answeredQuestions.has(q.id));
  if(next>=0){state.questionIndex=next;renderQuestions();}
  notice('Avaliação da questão salva. Prioridades reajustadas.');
});});

resetNovelForm();
renderRefreshInfo();
parseRoute();
safe(async()=>{
  const auth=await api('/auth/me');state.csrf=auth.csrf_token;$('accountName').textContent=auth.username;
  await reloadAll();
});
