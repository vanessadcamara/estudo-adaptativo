/* v0.8 — risco empírico conservador, filas isoladas e evolução semi-inédita. */
'use strict';
const state = {
  csrf: null, session: null,
  subjects: [], allSubjects: [], topics: [], allTopics: [], allQuestions: [],
  cardsQueue: {topics: [], questions: []}, errorsQueue: {topics: [], questions: []},
  currentTab: 'cards', settingsTab: 'cards', cardsSubject: '', errorsSubject: '',
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
  for (const name of ['cards', 'errors', 'settings']) {
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
    const route = tab === 'settings' ? `#configuracoes/${subtab}` : tab === 'errors' ? '#caderno' : '#cards';
    if (window.location.hash !== route) window.history.replaceState(null, '', route);
  }
}
function parseRoute() {
  const hash = location.hash;
  if (hash.startsWith('#configuracoes')) goTo('settings', hash.endsWith('/errors') ? 'errors' : 'cards', false);
  else if (hash === '#caderno') goTo('errors', 'cards', false);
  else goTo('cards', 'cards', false);
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
  const queue = await api(`/queue?subject_id=${subjectId}`);
  // Uma resposta antiga nunca substitui a fila após trocar rapidamente a matéria.
  if (state.queueRequest[kind] === request &&
      (kind === 'cards' ? state.cardsSubject : state.errorsSubject) === subject) state[key]=queue;
}
async function reloadAll({preserveQuestion=true}={}) {
  const oldQuestion = preserveQuestion ? visibleQuestions()[state.questionIndex]?.id : null;
  const [allSubjects,allTopics,allQuestions,openSession] = await Promise.all([
    api('/subjects?include_archived=true'),api('/topics?include_archived=true'),
    api('/questions?include_archived=true'),api('/sessions/open'),
  ]);
  state.allSubjects=allSubjects;state.allTopics=allTopics;state.allQuestions=allQuestions;
  state.subjects=allSubjects.filter(s=>!s.archived_at);
  state.topics=allTopics.filter(t=>!t.archived_at && state.subjects.some(s=>s.id===t.subject_id));
  state.session=openSession;
  if (openSession) {
    const progress=await api(`/sessions/${openSession.id}/progress`);
    state.reviewedTopics = new Set(progress.topics); state.answeredQuestions = new Set(progress.questions);
  } else {state.reviewedTopics = new Set();state.answeredQuestions = new Set();}
  updateOptions();renderCatalog();renderManagedQuestions();
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
function priority(entry) {return entry.priority>=58?'Alta':entry.priority>=38?'Média':'Baixa';}
function dateInfo(entry) {return entry.days_since==null?'Sem avaliações anteriores':`Última avaliação: ${entry.days_since<1?'há menos de 1 dia':`há ${Math.floor(entry.days_since)} dia(s)`}`;}
const STATE_LABELS = {em_aprendizagem:'Em aprendizagem',em_consolidacao:'Em consolidação',dominado:'Dominado'};
function meta(entry){
  const status=entry.maintenance_required?'Prazo atingido nesta matéria':
    (entry.learning_state ? (STATE_LABELS[entry.learning_state]||'Em aprendizagem'):
    entry.due?'Precisa de revisão':'Em manutenção');
  const risk=entry.forgetting_risk_percent == null ? 'Risco: sem histórico' :
    `Risco estimado: ${Number(entry.forgetting_risk_percent).toFixed(1)}% (ajuste empírico, não validado)`;
  const finalScore = entry.ranking_score ?? entry.priority;
  const riskBump = entry.risk_priority_bonus || 0;
  return `<div class="priority-line"><span><strong>Prioridade ${priority({...entry,priority:finalScore})} · ${Number(finalScore).toFixed(1)}/100</strong>${riskBump?` <small>(inclui +${riskBump.toFixed(1)} risco)</small>`:''}</span><span>${esc(dateInfo(entry))}</span><span>${esc(status)}</span><span>${esc(risk)}</span></div>`;
}
function masteryDetails(entry) {
  const c=entry.priority_components, e=entry.mastery_evidence;
  if(!c||!e)return '';
  const checks=[
    ['three_grade_fours','3 notas 4 consecutivas'],
    ['spaced_recoveries','Intervalos crescentes, com última lacuna de ≥ 14 dias'],
    ['varied_questions_85_percent',`Acertos ≥ 85% em questões distintas (${e.distinct_questions} questões; ${e.question_accuracy_percent??'—'}% de acertos)`],
    ['no_critical_gaps','Sem lacunas ou erros conceituais graves pendentes'],
    ['explained_without_consulting','Explicação sem consulta confirmada'],
    ['applied_to_new_questions','Aplicação em questões variadas sem consulta confirmada']
  ];
  const breakdown=`D ${c.D.toFixed(1)} · T ${c.T.toFixed(1)} · E ${c.E.toFixed(1)} · I ${c.I.toFixed(1)}`;
  return `<details class="mastery-details"><summary>Entender prioridade e critérios de domínio</summary>
    <p><strong>Fórmula:</strong> 0,35D + 0,30T + 0,25E + 0,10I (0–100). ${esc(breakdown)}.</p>
    <p>Intervalo adaptativo: ${entry.interval_days} dia(s). Se vencer, o assunto sobe na fila <strong>somente desta matéria</strong>. Você escolhe quando voltar a estudá-la.</p>
    <p>Prioridade-base ${Number(entry.priority).toFixed(1)}/100 + risco (até 8 pontos) = ${Number(entry.ranking_score??entry.priority).toFixed(1)}/100 na recomendação. O risco recebe ajuste empírico conservador quando há histórico suficiente, sem ser probabilidade validada.</p>
    <strong>Estado: ${esc(STATE_LABELS[entry.learning_state]||'Em aprendizagem')}</strong>
    <ul class="mastery-checklist">${checks.map(([key,label])=>`<li>${e[key]?'✓':'○'} ${esc(label)}</li>`).join('')}</ul>
    <p class="panel-help">Variedade é confirmada por você; links previamente errados não são questões inéditas e não estimam sua nota na prova.</p>
  </details>`;
}
function empty(title,description,command,label) {return `<div class="empty-state"><h3>${esc(title)}</h3><p>${esc(description)}</p>${command?`<button type="button" class="button primary" data-action="${command}">${esc(label)}</button>`:''}</div>`;}
function renderCards() {
  const candidates=availableTopics();const all=state.cardsQueue.topics;
  const topic=candidates.find(t=>t.id===state.activeTopicId)||candidates[0];
  if (!topic) {
    state.activeTopicId=null;
    $('topicStudyCard').innerHTML=!state.subjects.length?empty('Comece cadastrando sua primeira matéria','O banco ainda não tem matérias. Abra Configurações para cadastrar e depois adicione assuntos.','new-subject','Cadastrar matéria'):
      !state.cardsSubject?empty('Escolha a matéria que quer estudar','Cada matéria tem sua própria fila. Nenhum vencimento força você a escolher uma disciplina.'): 
      !all.length?empty('Cadastre um assunto para começar','Sua matéria está cadastrada, mas ainda não há assuntos disponíveis na pilha.','new-topic','Cadastrar assunto'):
      empty('Você percorreu esta pilha','Os itens avaliados e pulados continuam salvos. Atualize as prioridades para fazer uma nova passagem.','refresh','Reorganizar pilha');
    return;
  }
  state.activeTopicId=topic.id;
  $('topicStudyCard').innerHTML=`<article class="study-card"><div class="card-eyebrow">PRÓXIMO ASSUNTO RECOMENDADO</div><h3>${topic.code?`<span class="card-code">${esc(topic.code)}</span> `:''}${esc(topic.title)}</h3><p class="card-description">${esc(topic.reason)}. Tente explicar sem consultar antes de avaliar.</p>${meta(topic)}${masteryDetails(topic)}<div class="actions"><button type="button" class="button primary" data-action="finish-topic" data-id="${topic.id}">Marcar como finalizado</button><button type="button" class="button outline" data-action="skip-topic" data-id="${topic.id}">Pular por agora</button></div></article>`;
}
function renderQuestions() {
  const progress=state.errorsQueue.semi_novel_progress;
  $('semiNovelProgress').textContent=!state.errorsSubject?'':!progress?'':
    progress.spaced_secure_percent==null
      ? `Questões semi-inéditas: ${progress.registered} cadastradas, ${progress.reviewed_in_app} reavaliadas. Acompanhamento de retenção começa após duas tentativas separadas por ≥ 7 dias.`
      : `Retenção em questões semi-inéditas: ${progress.spaced_secure}/${progress.spaced_distinct} links distintos com acerto seguro após ≥ 7 dias (${progress.spaced_secure_percent}%). Meta de referência: ${progress.target_percent}%. ${progress.sufficient_sample?'':'Amostra ainda pequena. '}${progress.trend_pp==null?'':`Variação observada entre períodos: ${progress.trend_pp>0?'+':''}${progress.trend_pp} p.p. `}Não prevê nota na prova.`;
  const questions=visibleQuestions();
  if (state.questionIndex>=questions.length)state.questionIndex=Math.max(0,questions.length-1);
  const q=questions[state.questionIndex];
  $('questionPrevious').disabled=!q||state.questionIndex===0;
  $('questionNext').disabled=!q||state.questionIndex===questions.length-1;
  $('questionPosition').textContent=q?`${state.questionIndex+1} de ${questions.length}`:'Sem questões';
  if(!q){$('questionStudyCard').innerHTML=state.errorsSubject?empty('Seu caderno está vazio nesta matéria','Cadastre o link de uma questão errada nessa matéria para começar a revisão.','new-question','Adicionar questão'):empty('Escolha a matéria do caderno de erros','Os vencimentos só ordenam questões da matéria que você selecionar.');return;}
  const done=state.answeredQuestions.has(q.id);
  $('questionStudyCard').innerHTML=`<article class="study-card"><div class="card-eyebrow">LINK RECOMENDADO · ${state.questionIndex+1}/${questions.length}</div><h3>${esc(q.statement?q.statement.slice(0,150):'Retome esta questão')}</h3><p class="card-description">${esc(q.reason)}.</p>${q.url?`<a class="link-question" href="${esc(q.url)}" target="_blank" rel="noopener noreferrer">Abrir link da questão ↗</a>`:''}${q.statement&&q.statement.length>150?`<p class="statement">${esc(q.statement)}</p>`:''}${meta(q)}${q.archive_suggested?`<div class="suggestion"><strong>Arquivamento sugerido</strong><p>${esc(q.archive_reason||'Você demonstrou domínio consistente.')}</p></div>`:''}<div class="actions"><button type="button" class="button primary" data-action="assess-question" data-id="${q.id}" ${done?'disabled':''}>${done?'Avaliação salva':'Avaliar desempenho'}</button><button type="button" class="button outline" data-action="archive-question" data-id="${q.id}">${q.archive_suggested?'Arquivar link recomendado':'Arquivar link'}</button></div>${done?'<p class="helper">Esta questão já foi avaliada nesta passagem. O refresh permite um novo ciclo, sem apagar a tentativa.</p>':''}</article>`;
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
async function refresh() {
  if(state.session)await api(`/sessions/${state.session.id}/refresh`,'POST');
  state.session=null;state.skippedTopics.clear();state.reviewedTopics.clear();state.answeredQuestions.clear();state.activeTopicId=null;state.questionIndex=0;
  await reloadAll({preserveQuestion:false});notice('Prioridades recalculadas. O histórico continua salvo.');
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
$('logoutBtn').addEventListener('click',()=>safe(async()=>{await api('/auth/logout','POST');window.location.replace('/login');}));

document.addEventListener('click',event=>{
  const el=event.target.closest('button[data-action],button[data-edit-subject],button[data-edit-topic],button[data-edit-question],button[data-archive-subject],button[data-archive-topic],button[data-archive-question]');
  if(!el)return;
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
  await api(`/sessions/${session.id}/topic-reviews`,'POST',{
    topic_id:state.reviewTopicId,grade:Number(data.get('grade')),difficulty:Number(data.get('difficulty')),
    critical_gap:data.get('critical_gap')==='true',
    explained_without_consulting:data.get('explained_without_consulting')==='on',
    applied_to_new_questions:data.get('applied_to_new_questions')==='on',
    notes:String(data.get('notes')||'').trim()||null,
  });
  closeDialog('reviewDialog');state.activeTopicId=null;await afterChange('Avaliação salva no PostgreSQL. Próximo assunto recomendado.');
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

parseRoute();
safe(async()=>{
  const auth=await api('/auth/me');state.csrf=auth.csrf_token;$('accountName').textContent=auth.username;
  await reloadAll();
});
