const state = { session: null, subjects: [], topics: [], queue: null, csrf: null };
const $ = id => document.getElementById(id);
const escapeHtml = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = async (path, method='GET', data) => {
  const res = await fetch('/api' + path, {method, credentials: 'same-origin', headers: {'Content-Type':'application/json', ...(method !== 'GET' ? {'X-CSRF-Token': state.csrf} : {})}, body: data===undefined?undefined:JSON.stringify(data)});
  if (res.status === 401) { window.location.replace('/login'); throw new Error('Sessão expirada. Faça login novamente.'); }
  const result = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof result.detail === 'string'?result.detail:JSON.stringify(result.detail || 'Falha na comunicação'));
  return result;
};
function toast(message, error=false) {
  const box = $('message'); box.hidden = false; box.className = 'message'+(error?' error':''); box.textContent = message;
}
async function safe(task) {try {await task();} catch (e) {toast(e.message, true);}}
function optionList(items, empty='Selecione', allowEmpty=false) {
  return (allowEmpty?'<option value="">'+escapeHtml(empty)+'</option>':'') + items.map(x=>`<option value="${x.id}">${escapeHtml(x.label)}</option>`).join('');
}
function redrawSelects() {
  const subjects = state.subjects.map(s => ({id:s.id,label:s.name}));
  $('subjectSelect').innerHTML=optionList(subjects);
  const topics = state.topics.map(t => ({id:t.id,label:(t.code?t.code+' · ':'')+t.title}));
  $('studyTopic').innerHTML=optionList(topics);
  $('questionTopic').innerHTML=optionList(topics,'Nenhum (somente link)',true);
}
async function loadBasics() {
  [state.subjects,state.topics] = await Promise.all([api('/subjects'),api('/topics')]);
  redrawSelects();
}
async function updateDashboard() {
  const d=await api('/dashboard');
  $('stats').innerHTML = [
    [d.total_topics,'Tópicos cadastrados'],[d.total_questions,'Questões no caderno'],
    [d.due_topics,'Tópicos vencidos'],[d.due_questions,'Questões para rever']
  ].map(([n,name])=>`<div class="stat"><strong>${n}</strong><small>${name}</small></div>`).join('');
  if(d.recent_sessions.length){let s=d.recent_sessions[0]; $('lastSummary').innerHTML=`Último refresh (sessão ${s.id}): <strong>${s.summary.topics_reviewed}</strong> tópicos, <strong>${s.summary.questions_attempted}</strong> questões e <strong>${s.summary.new_content_minutes}</strong> min de conteúdo novo.`;}
}
function sessionUI() {
  $('sessionBadge').textContent=state.session?`Sessão #${state.session.id} aberta`:'Nenhuma sessão aberta';
  $('refreshBtn').disabled=!state.session;
  $('startBtn').textContent=state.session?'Sessão em andamento':'Iniciar / retomar sessão';
  $('startBtn').disabled=!!state.session;
}
function queueCard(topic) {
  const code=topic.code?escapeHtml(topic.code)+' · ':'';
  const grades=[0,1,2,3,4].map(n=>`<button class="score" data-topic="${topic.id}" data-grade="${n}" ${!state.session?'disabled':''} title="Nota ${n}">${n}</button>`).join('');
  return `<article class="item"><h3>${code}${escapeHtml(topic.title)}</h3><p>${escapeHtml(topic.reason)}</p>
    <div class="meta"><span class="chip ${topic.due?'due':''}">${topic.due?'Na hora de revisar':'Manutenção futura'}</span><span class="chip">Intervalo ${topic.interval_days}d</span><span class="chip">Prioridade ${Math.round(topic.priority*100)}%</span>${topic.mastered?'<span class="chip">Consolidado</span>':''}</div>
    <div class="item-actions"><small>Como lembrou?</small>${grades}</div></article>`;
}
function questionCard(q) {
  const link = q.url?`<a href="${escapeHtml(q.url)}" target="_blank" rel="noopener noreferrer">Abrir questão</a>`:'Sem link';
  return `<article class="item"><h3>Questão #${q.id} · ${escapeHtml(q.reason)}</h3><p>${link}${q.statement?' · '+escapeHtml(q.statement.slice(0,130)):''}</p>
    <div class="meta"><span class="chip ${q.due?'due':''}">${q.due?'Revisar':'Manutenção'}</span><span class="chip">${q.errors} erro(s) · ${q.attempts} tentativa(s)</span><span class="chip">Prioridade ${Math.round(q.priority*100)}%</span></div>
    <div class="item-actions"><button class="fail" data-question="${q.id}" data-correct="false" ${!state.session?'disabled':''}>Errei</button><button class="success" data-question="${q.id}" data-correct="true" ${!state.session?'disabled':''}>Acertei</button></div></article>`;
}
async function loadQueue() {
  state.queue=await api(state.session?`/sessions/${state.session.id}/queue`:'/queue');
  $('topicQueue').innerHTML=state.queue.topics.map(queueCard).join('') || '<div class="empty">Nenhum tópico na fila. Cadastre o primeiro tópico.</div>';
  $('questionQueue').innerHTML=state.queue.questions.map(questionCard).join('') || '<div class="empty">Nenhuma questão no caderno. Cole o primeiro link.</div>';
  document.querySelectorAll('[data-topic][data-grade]').forEach(button=>button.addEventListener('click',()=>safe(async()=>{
    await api(`/sessions/${state.session.id}/topic-reviews`,'POST',{topic_id:Number(button.dataset.topic),grade:Number(button.dataset.grade)});
    toast('Recuperação salva! A próxima prioridade será calculada pelo histórico.'); await refreshUI();
  })));
  document.querySelectorAll('[data-question][data-correct]').forEach(button=>button.addEventListener('click',()=>safe(async()=>{
    await api(`/sessions/${state.session.id}/question-attempts`,'POST',{question_id:Number(button.dataset.question),is_correct:button.dataset.correct==='true'});
    toast('Tentativa registrada no caderno de erros.'); await refreshUI();
  })));
}
async function refreshUI() {sessionUI();await Promise.all([updateDashboard(),loadQueue()]);}
$('startBtn').addEventListener('click',()=>safe(async()=>{
  state.session=await api('/sessions','POST'); toast('Sessão iniciada. Use a fila e registre suas notas.');await refreshUI();
}));
$('refreshBtn').addEventListener('click',()=>safe(async()=>{
  const closed=await api(`/sessions/${state.session.id}/refresh`,'POST');
  state.session=null;toast(`Refresh concluído: ${closed.refresh_summary.topics_reviewed} tópicos e ${closed.refresh_summary.questions_attempted} questões. Histórico preservado.`);await refreshUI();
}));
$('subjectForm').addEventListener('submit', e=>{e.preventDefault();safe(async()=>{
  await api('/subjects','POST',{name:$('subjectName').value});$('subjectForm').reset();await loadBasics();toast('Matéria cadastrada.');
});});
$('topicForm').addEventListener('submit', e=>{e.preventDefault();safe(async()=>{
  await api('/topics','POST',{subject_id:Number($('subjectSelect').value),code:$('topicCode').value||null,title:$('topicTitle').value,importance:Number($('topicImportance').value)});
  $('topicForm').reset();await loadBasics();await refreshUI();toast('Tópico adicionado à fila.');
});});
$('questionForm').addEventListener('submit', e=>{e.preventDefault();safe(async()=>{
  await api('/questions','POST',{url:$('questionUrl').value||null,statement:$('questionText').value||null,topic_id:$('questionTopic').value?Number($('questionTopic').value):null});
  $('questionForm').reset();await refreshUI();toast('Questão salva! Você só precisava do link.');
});});
$('newContentForm').addEventListener('submit', e=>{e.preventDefault();safe(async()=>{
  if(!state.session) throw new Error('Inicie uma sessão para registrar conteúdo novo.');
  await api(`/sessions/${state.session.id}/new-content`,'POST',{topic_id:Number($('studyTopic').value),minutes:Number($('studyMinutes').value)});
  toast('Conteúdo novo registrado. A primeira revisão ficará programada para depois.');await refreshUI();
});});
$('logoutBtn').addEventListener('click',()=>safe(async()=>{
  await api('/auth/logout','POST'); window.location.replace('/login');
}));
safe(async()=>{
  const auth = await api('/auth/me');
  state.csrf = auth.csrf_token;
  $('accountName').textContent = auth.username;
  await loadBasics(); state.session=await api('/sessions/open'); await refreshUI();
});
