/* v0.4 — pilhas contínuas de Cards e Caderno de erros, sem limites diários. */
const state = {
  csrf: null, session: null, subjects: [], topics: [], allQuestions: [],
  queue: {topics: [], questions: []}, currentTab: 'cards', settingsTab: 'cards',
  cardsSubject: 'all', errorsSubject: 'all', activeTopicId: null,
  skippedTopics: new Set(), reviewedTopics: new Set(), answeredQuestions: new Set(),
  questionIndex: 0,
};
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
async function api(path, method='GET', payload) {
  const response=await fetch('/api'+path,{
    method,credentials:'same-origin',
    headers:{'Content-Type':'application/json',...(method!=='GET'?{'X-CSRF-Token':state.csrf}:{})},
    body:payload===undefined?undefined:JSON.stringify(payload),
  });
  const data=await response.json().catch(()=>({}));
  if(response.status===401){window.location.replace('/login');throw Error('Sua sessão expirou. Entre novamente.');}
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Não foi possível concluir. Verifique sua conexão.');
  return data;
}
function toast(message,error=false){const node=$('message');node.textContent=message;node.className=`message${error?' error':''}`;node.hidden=false;}
async function safe(work){try{await work();}catch(e){toast(e.message||'Não foi possível concluir.',true);}}
function gotoTab(name){
  state.currentTab=name;
  document.querySelectorAll('[data-tab]').forEach(button=>{
    const active=button.dataset.tab===name;button.classList.toggle('active',active);
    button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;
  });
  ['cards','errors','settings'].forEach(tab=>$('tab-'+tab).hidden=tab!==name);
}
function gotoSettingsTab(name){
  state.settingsTab=name;
  document.querySelectorAll('[data-settings-tab]').forEach(button=>{
    const active=button.dataset.settingsTab===name;
    button.classList.toggle('active',active);button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;
  });
  ['cards','errors'].forEach(tab=>$('settings-'+tab).hidden=tab!==name);
}
function options(items,placeholder,allowEmpty=true){
  return (allowEmpty?`<option value="">${escapeHtml(placeholder)}</option>`:'')+
    items.map(item=>`<option value="${item.id}">${escapeHtml(item.label)}</option>`).join('');
}
function syncSelect(id, html, fallback=''){
  const node=$(id),previous=node.value;
  node.innerHTML=html;node.value=previous||fallback;
  if(node.selectedIndex<0)node.value=fallback;
}
function topicLabel(t){return `${t.code?t.code+' · ':''}${t.title}`;}
function refreshSelects(){
  const subjects=state.subjects.map(s=>({id:s.id,label:s.name}));
  const filters='<option value="all">Todas as matérias</option>'+options(subjects,'',false);
  syncSelect('cardsSubject',filters,state.cardsSubject);
  syncSelect('errorsSubject',filters+'<option value="unassigned">Sem matéria</option>',state.errorsSubject);
  $('cardsSubject').value=state.cardsSubject;
  $('errorsSubject').value=state.errorsSubject;
  syncSelect('subjectSelect',options(subjects,'Selecione uma matéria'));
  syncSelect('questionSubject',options(subjects,'Selecione uma matéria'));
  updateQuestionTopicOptions();
}
function updateQuestionTopicOptions(){
  const subjectId=Number($('questionSubject').value);
  const candidates=state.topics.filter(t=>t.subject_id===subjectId).map(t=>({id:t.id,label:topicLabel(t)}));
  syncSelect('questionTopic',options(candidates,'Sem assunto específico'));
}
function renderCatalog(){
  $('subjectsList').innerHTML='<p class="registered-heading">Matérias cadastradas</p>'+
    (state.subjects.length?state.subjects.map(s=>{
      const n=state.topics.filter(t=>t.subject_id===s.id).length;
      return `<div class="registered-item"><div><strong>${escapeHtml(s.name)}</strong><span class="item-note">${n} assunto${n===1?'':'s'}</span></div></div>`;
    }).join(''):'<p class="empty-inline">Nenhuma matéria cadastrada.</p>');
  const subject=$('subjectSelect').value;
  const topics=state.topics.filter(t=>!subject||String(t.subject_id)===subject);
  $('topicsList').innerHTML='<p class="registered-heading">Assuntos da matéria selecionada</p>'+
    (topics.length?topics.map(t=>`<div class="registered-item"><div><strong>${escapeHtml(topicLabel(t))}</strong><span class="item-note">Importância ${t.importance}/5 · entra na pilha automaticamente</span></div></div>`).join(''):'<p class="empty-inline">Nenhum assunto cadastrado nesta matéria.</p>');
}
function renderQuestionManagement(){
  const archived=$('manageQuestionsFilter').value==='archived';
  const entries=state.allQuestions.filter(q=>Boolean(q.archived_at)===archived);
  const priorityById=new Map(state.queue.questions.map(q=>[q.id,q]));
  $('managedQuestionsList').innerHTML=`<p class="registered-heading">${archived?'Arquivadas':'Na pilha'} · ${entries.length}</p>`+
    (entries.length?entries.map(q=>{
      const priority=priorityById.get(q.id);
      const title=q.url||q.statement||`Questão #${q.id}`;
      return `<div class="registered-item"><div><strong>${escapeHtml(title)}</strong><span class="item-note">${q.subject_id?escapeHtml(state.subjects.find(s=>s.id===q.subject_id)?.name||'Matéria não identificada'):'Sem matéria'}${priority?.archive_suggested?' · Arquivamento recomendado':''}</span></div><button class="button ${archived?'secondary':'danger-outline'}" type="button" data-archive-id="${q.id}" data-archive-value="${!archived}">${archived?'Restaurar':'Retirar da pilha'}</button></div>`;
    }).join(''):'<p class="empty-inline">Nenhum link aqui.</p>');
}
async function loadBasics(){
  [state.subjects,state.topics]=await Promise.all([api('/subjects'),api('/topics')]);
  refreshSelects();renderCatalog();
}
async function loadProgress(){
  if(!state.session){state.reviewedTopics=new Set();state.answeredQuestions=new Set();return;}
  const progress=await api(`/sessions/${state.session.id}/progress`);
  state.reviewedTopics=new Set(progress.topics);state.answeredQuestions=new Set(progress.questions);
}
async function loadQueue({keepQuestion=true}={}){
  const previousId=keepQuestion?filteredQuestions()[state.questionIndex]?.id:null;
  [state.queue,state.allQuestions]=await Promise.all([api('/queue'),api('/questions?include_archived=true')]);
  await loadProgress();
  if(previousId!=null){const index=filteredQuestions().findIndex(q=>q.id===previousId);state.questionIndex=index>=0?index:0;}
  else state.questionIndex=0;
  renderCards();renderQuestions();renderQuestionManagement();
}
function matchesSubject(entry,selected){
  if(selected==='all')return true;
  if(selected==='unassigned')return entry.subject_id==null;
  return String(entry.subject_id)===selected;
}
function filteredTopics(){return state.queue.topics.filter(t=>matchesSubject(t,state.cardsSubject));}
function availableTopics(){return filteredTopics().filter(t=>!state.reviewedTopics.has(t.id)&&!state.skippedTopics.has(t.id));}
function filteredQuestions(){return state.queue.questions.filter(q=>matchesSubject(q,state.errorsSubject));}
function priorityLabel(entry){return entry.priority>=0.58?'Alta':entry.priority>=0.38?'Moderada':'Baixa';}
function timeInfo(entry){
  if(entry.days_since==null)return 'Sem avaliações anteriores';
  const d=entry.days_since;
  return d<1?'Última avaliação há menos de um dia':`Última avaliação há ${Math.floor(d)} dia${Math.floor(d)===1?'':'s'}`;
}
function details(entry){
  return `<div class="priority-line"><span><strong>Prioridade: ${priorityLabel(entry)}</strong></span><span>${timeInfo(entry)}</span></div>`;
}
function emptyState(title,message,settingsAction=''){
  return `<div class="empty-state"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p>${settingsAction?`<button type="button" class="button secondary" data-settings-action="${settingsAction}">Abrir configurações</button>`:''}</div>`;
}
function renderCards(){
  const all=filteredTopics(),remaining=availableTopics();
  const active=remaining.find(t=>t.id===state.activeTopicId)||remaining[0];
  if(!active){state.activeTopicId=null;
    $('topicStudyCard').innerHTML=all.length?
      emptyState('Assuntos já avaliados ou pulados','Nenhum limite de tempo: use Atualizar prioridades para voltar a percorrer a pilha quando desejar.'):
      emptyState('Nenhum assunto cadastrado','Cadastre uma matéria e seus assuntos em Configurações.','cards');
    return;
  }
  state.activeTopicId=active.id;
  $('topicStudyCard').innerHTML=`<article class="card">
    <div class="card-overline"><span>PRÓXIMO ASSUNTO RECOMENDADO</span></div>
    <h3 class="card-title">${active.code?`<span class="eyebrow">${escapeHtml(active.code)}</span> · `:''}${escapeHtml(active.title)}</h3>
    <p class="card-description">${escapeHtml(active.reason)}. Explique livremente antes de avaliar sua lembrança.</p>
    ${details(active)}
    <div id="topicActions" class="card-actions"><button id="topicFinish" type="button" class="button primary">Marcar como finalizado</button><button id="topicSkip" class="button outline" type="button">Pular por agora →</button></div>
    <form id="topicFeedback" class="questionnaire" hidden>
      <h3>Como foi sua revisão?</h3><p class="questionnaire-intro">Sua avaliação atualiza os pesos do assunto e influencia os próximos intervalos.</p>
      <fieldset class="question-block"><legend>1. O quanto conseguiu lembrar sem consultar?</legend><div class="radio-stack">
      ${[['0','0 · Não lembrei do assunto'],['1','1 · Lembrei fragmentos, com muitas lacunas'],['2','2 · Lembrei parcialmente, com erros importantes'],['3','3 · Lembrei bem, com pequenas lacunas'],['4','4 · Expliquei corretamente, com segurança']].map(([v,txt])=>`<label class="radio-row"><input type="radio" name="grade" value="${v}" required><span>${txt}</span></label>`).join('')}
      </div></fieldset>
      <fieldset class="question-block"><legend>2. Qual foi o esforço para recuperar a informação?</legend><div class="radio-grid">
        <label class="radio-row"><input type="radio" name="difficulty" value="1" required>Fácil</label>
        <label class="radio-row"><input type="radio" name="difficulty" value="2" required>Moderado</label>
        <label class="radio-row"><input type="radio" name="difficulty" value="3" required>Muito difícil</label>
      </div></fieldset>
      <fieldset class="question-block"><legend>3. Ficou alguma lacuna conceitual importante?</legend><div class="chip-row">
        <label class="radio-row"><input type="radio" name="critical_gap" value="false" required>Não</label>
        <label class="radio-row"><input type="radio" name="critical_gap" value="true" required>Sim, preciso reforçar</label>
      </div></fieldset>
      <label class="field">Anotação (opcional)<textarea name="notes" rows="2" maxlength="3000" placeholder="Conceitos a retomar..."></textarea></label>
      <div class="card-actions"><button type="submit" class="button primary">Enviar respostas</button><button type="button" id="topicCancel" class="button outline">Voltar</button></div>
    </form>
  </article>`;
  $('topicFinish').addEventListener('click',()=>{$('topicActions').hidden=true;$('topicFeedback').hidden=false;});
  $('topicCancel').addEventListener('click',()=>{$('topicActions').hidden=false;$('topicFeedback').hidden=true;});
  $('topicSkip').addEventListener('click',()=>{state.skippedTopics.add(active.id);state.activeTopicId=null;renderCards();});
  $('topicFeedback').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
    const d=new FormData(event.currentTarget),session=await ensureSession();
    await api(`/sessions/${session.id}/topic-reviews`,'POST',{
      topic_id:active.id,grade:Number(d.get('grade')),difficulty:Number(d.get('difficulty')),
      critical_gap:d.get('critical_gap')==='true',notes:String(d.get('notes')||'').trim()||null,
    });
    state.activeTopicId=null;await loadQueue();toast('Avaliação registrada. A pilha já considera seu desempenho.');
  });});
}
function renderQuestions(){
  const questions=filteredQuestions();
  if(state.questionIndex>=questions.length)state.questionIndex=Math.max(0,questions.length-1);
  const q=questions[state.questionIndex];
  $('questionPrevious').disabled=!q||state.questionIndex===0;
  $('questionNext').disabled=!q||state.questionIndex===questions.length-1;
  $('questionPosition').textContent=q?`${state.questionIndex+1} de ${questions.length}`:'Sem questões';
  if(!q){$('questionStudyCard').innerHTML=emptyState('Nenhuma questão na pilha','Adicione um link em Configurações ou restaure uma questão arquivada.','errors');return;}
  const done=state.answeredQuestions.has(q.id);
  $('questionStudyCard').innerHTML=`<article class="card">
    <div class="card-overline"><span>QUESTÃO RECOMENDADA</span><span>${done?'Avaliada desde a última atualização':''}</span></div>
    <h3 class="card-title">${q.statement?escapeHtml(q.statement.length>155?q.statement.slice(0,155)+'…':q.statement):'Retome esta questão'}</h3>
    <p class="card-description">${escapeHtml(q.reason)}.</p>
    ${q.url?`<a href="${escapeHtml(q.url)}" target="_blank" rel="noopener noreferrer" class="question-link">Abrir link da questão ↗</a>`:''}
    ${q.statement&&q.statement.length>155?`<p class="question-text">${escapeHtml(q.statement)}</p>`:''}
    ${details(q)}
    ${q.archive_suggested?`<aside class="archive-suggestion"><strong>Sugestão do algoritmo: retirar esta questão da pilha</strong><p>${escapeHtml(q.archive_reason||'Os acertos já demonstram consistência.')}</p><button class="button secondary" id="archiveRecommended" type="button">Arquivar link recomendado</button></aside>`:''}
    ${done?'<div class="summary-box">Sua tentativa está salva. O próximo refresh permitirá revisitá-la conforme a prioridade calculada.</div>':`<form id="questionFeedback" class="questionnaire">
      <h3>Como você se saiu?</h3><p class="questionnaire-intro">Responda à questão no site de origem e registre seu desempenho.</p>
      <fieldset class="question-block"><legend>1. Você acertou?</legend><div class="chip-row">
        <label class="radio-row"><input type="radio" name="is_correct" value="false" required>Errei</label>
        <label class="radio-row"><input type="radio" name="is_correct" value="true" required>Acertei</label>
      </div></fieldset>
      <fieldset class="question-block"><legend>2. Qual foi sua confiança na resposta?</legend><div class="radio-grid">
        <label class="radio-row"><input type="radio" name="confidence" value="1" required>Chutei</label>
        <label class="radio-row"><input type="radio" name="confidence" value="2" required>Tive dúvidas</label>
        <label class="radio-row"><input type="radio" name="confidence" value="3" required>Estava segura</label>
      </div></fieldset>
      <label class="field">3. Se errou, qual foi a dificuldade? (opcional)
        <select name="error_type"><option value="">Não classificar</option><option value="concept">Não entendi o conceito</option><option value="interpretation">Interpretação do enunciado</option><option value="attention">Desatenção</option><option value="calculation">Cálculo / procedimento</option><option value="other">Outro motivo</option></select>
      </label>
      <label class="field">Anotação (opcional)<textarea name="notes" rows="2" maxlength="3000" placeholder="O que devo lembrar?"></textarea></label>
      <button class="button primary" type="submit">Salvar avaliação e continuar</button>
    </form>`}
    ${!q.archive_suggested?'<div class="archival-row"><button id="archiveManual" class="button danger-outline" type="button">Retirar da pilha</button></div>':''}
  </article>`;
  const form=$('questionFeedback');
  if(form)form.addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
    const d=new FormData(event.currentTarget),session=await ensureSession(),isCorrect=d.get('is_correct')==='true';
    await api(`/sessions/${session.id}/question-attempts`,'POST',{
      question_id:q.id,is_correct:isCorrect,confidence:Number(d.get('confidence')),
      error_type:!isCorrect&&d.get('error_type')?String(d.get('error_type')):null,
      notes:String(d.get('notes')||'').trim()||null,
    });
    await loadQueue();
    const list=filteredQuestions();
    const candidate=list.findIndex(item=>item.id!==q.id&&!state.answeredQuestions.has(item.id));
    if(candidate!==-1)state.questionIndex=candidate;
    renderQuestions();toast('Tentativa registrada. As prioridades foram recalculadas.');
  });});
  for(const id of ['archiveRecommended','archiveManual']){
    const button=$(id);if(button)button.addEventListener('click',()=>safe(async()=>{
      if(!window.confirm('Retirar esta questão da pilha? Você poderá restaurá-la em Configurações, sem perder o histórico.'))return;
      await toggleArchive(q.id,true);toast('Questão arquivada. Histórico preservado.');
    }));
  }
}
async function toggleArchive(id,archived){
  await api(`/questions/${id}/archive`,'PATCH',{archived});
  await loadQueue({keepQuestion:false});
}
async function ensureSession(){if(!state.session)state.session=await api('/sessions','POST');return state.session;}
async function refreshRecommendations(){
  if(state.session)await api(`/sessions/${state.session.id}/refresh`,'POST');
  state.session=null;state.reviewedTopics=new Set();state.answeredQuestions=new Set();
  state.skippedTopics=new Set();state.activeTopicId=null;state.questionIndex=0;
  await loadQueue({keepQuestion:false});
  toast('Pilha atualizada conforme o histórico e o tempo transcorrido. Nenhum dado foi apagado.');
}
// Navegação principal e secundária.
document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>gotoTab(button.dataset.tab)));
document.querySelectorAll('[data-settings-tab]').forEach(button=>button.addEventListener('click',()=>gotoSettingsTab(button.dataset.settingsTab)));
document.addEventListener('click',event=>{
  const action=event.target.closest('[data-settings-action]');if(action){gotoTab('settings');gotoSettingsTab(action.dataset.settingsAction);}
  const archive=event.target.closest('[data-archive-id]');if(archive)safe(async()=>{
    const archived=archive.dataset.archiveValue==='true';
    if(archived&&!window.confirm('Retirar da pilha? O histórico será preservado.'))return;
    await toggleArchive(Number(archive.dataset.archiveId),archived);
    toast(archived?'Questão arquivada.':'Questão restaurada na pilha.');
  });
});
$('cardsSubject').addEventListener('change',event=>{state.cardsSubject=event.target.value;state.activeTopicId=null;state.skippedTopics=new Set();renderCards();});
$('errorsSubject').addEventListener('change',event=>{state.errorsSubject=event.target.value;state.questionIndex=0;renderQuestions();});
$('cardsRefresh').addEventListener('click',()=>safe(refreshRecommendations));
$('errorsRefresh').addEventListener('click',()=>safe(refreshRecommendations));
$('questionPrevious').addEventListener('click',()=>{if(state.questionIndex>0){state.questionIndex--;renderQuestions();}});
$('questionNext').addEventListener('click',()=>{if(state.questionIndex<filteredQuestions().length-1){state.questionIndex++;renderQuestions();}});
$('questionSubject').addEventListener('change',updateQuestionTopicOptions);
$('subjectSelect').addEventListener('change',renderCatalog);
$('manageQuestionsFilter').addEventListener('change',renderQuestionManagement);
$('subjectForm').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  await api('/subjects','POST',{name:$('subjectName').value.trim()});$('subjectForm').reset();
  await loadBasics();toast('Matéria cadastrada.');
});});
$('topicForm').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  await api('/topics','POST',{
    subject_id:Number($('subjectSelect').value),code:$('topicCode').value.trim()||null,
    title:$('topicTitle').value.trim(),importance:Number($('topicImportance').value),
  });
  $('topicForm').reset();await loadBasics();await loadQueue();toast('Assunto incluído na pilha contínua de Cards.');
});});
$('questionForm').addEventListener('submit',event=>{event.preventDefault();safe(async()=>{
  await api('/questions','POST',{
    subject_id:Number($('questionSubject').value),
    topic_id:$('questionTopic').value?Number($('questionTopic').value):null,
    url:$('questionUrl').value.trim()||null,statement:$('questionText').value.trim()||null,
  });
  $('questionForm').reset();updateQuestionTopicOptions();await loadQueue();toast('Questão adicionada à pilha do caderno.');
});});
$('logoutBtn').addEventListener('click',()=>safe(async()=>{await api('/auth/logout','POST');window.location.replace('/login');}));
safe(async()=>{
  const auth=await api('/auth/me');state.csrf=auth.csrf_token;$('accountName').textContent=auth.username;
  await loadBasics();state.session=await api('/sessions/open');await loadQueue();
});
