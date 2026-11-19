import os,sys,json
from pathlib import Path
from argon2 import PasswordHasher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
os.environ.update({'APP_ENV':'test','APP_SECRET_KEY':'local_test_secret_for_e2e_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ','ADMIN_USERNAME':'estudante','ADMIN_PASSWORD_HASH':PasswordHasher(time_cost=1,memory_cost=8192).hash('SenhaTesteSegura!123')})
from app import models
from app.db import Base,get_db
from app.main import app
engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
Base.metadata.create_all(engine)
def override_db():
 with Session(engine) as db:yield db
app.dependency_overrides[get_db]=override_db
with TestClient(app) as client:
 login=client.post('/api/auth/login',json={'username':'estudante','password':'SenhaTesteSegura!123'})
 assert login.status_code==200,login.text
 csrf=login.json()['csrf_token']
 def bridge(req):
  kwargs={}
  if 'body' in req and req['body'] is not None:kwargs['json']=json.loads(req['body'])
  if not req.get('url'):
   return {'status':400,'body':'{}'}
  result=client.request(req['method'],req['url'],headers={'X-CSRF-Token':csrf},**kwargs)
  return {'status':result.status_code,'body':result.text}
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page()
  errors=[]
  page.on('pageerror',lambda e:errors.append('page error: '+str(e)))
  page.on('console',lambda m:errors.append('console '+m.text) if m.type=='error' else None)
  page.expose_function('bridge',bridge)
  html=(root/'app/static/index.html').read_text()
  html=html.replace('<link rel="stylesheet" href="/static/style.css?v=8">','').replace('<script src="/static/app.js?v=8" defer></script>','')
  page.set_content(html,wait_until='domcontentloaded')
  page.add_style_tag(content=(root/'app/static/style.css').read_text())
  page.evaluate('''window.fetch=async (path,init={})=>{const result=await window.bridge({url:path,method:init.method||'GET',body:init.body||null});return new Response(result.body,{status:result.status,headers:{'Content-Type':'application/json'}});}''')
  page.add_script_tag(content=(root/'app/static/app.js').read_text())
  print('bootstrap...',page.locator('#topicStudyCard').inner_text()[:200], 'console',errors)
  page.get_by_role('button',name='Cadastrar matéria').click()
  print('dialog open?',page.locator('#subjectDialog').is_visible())
  page.locator('#subjectName').fill('Conhecimentos Bancários');page.get_by_role('button',name='Salvar matéria').click();page.wait_for_timeout(150)
  print('after save',page.locator('#subjectsList').inner_text(),errors)
  page.locator('#newTopic').click();page.locator('#subjectSelect').select_option(label='Conhecimentos Bancários');page.locator('#topicTitle').fill('Sistema Financeiro Nacional');page.get_by_role('button',name='Salvar assunto').click();page.wait_for_timeout(150)
  print('after topic',page.locator('#topicsList').inner_text(),errors)
  page.locator('#subjectsList [data-edit-subject]').first.click();page.locator('#subjectName').fill('Bancários e Economia');page.get_by_role('button',name='Salvar matéria').click();page.wait_for_timeout(150)
  assert 'Bancários e Economia' in page.locator('#subjectsList').inner_text()
  page.locator('#topicsList [data-edit-topic]').first.click();page.locator('#topicTitle').fill('SFN e Mercado');page.get_by_role('button',name='Salvar assunto').click();page.wait_for_timeout(150)
  assert 'SFN e Mercado' in page.locator('#topicsList').inner_text()
  page.locator('#tab-button-cards').click()
  print('cards',page.locator('#topicStudyCard').inner_text()[:200],errors)
  page.locator('#cardsSubject').select_option(label='Bancários e Economia')
  page.wait_for_timeout(150)
  page.get_by_role('button',name='Marcar como finalizado').click()
  print('questionnaire?',page.locator('#reviewDialog').is_visible())
  page.locator('#reviewDialog input[name="grade"][value="2"]').check();page.locator('#reviewDialog input[name="difficulty"][value="3"]').check();page.locator('#reviewDialog input[name="critical_gap"][value="true"]').check()
  page.get_by_role('button',name='Enviar respostas').click();page.wait_for_timeout(200)
  print('after review',page.locator('#topicStudyCard').inner_text()[:150],page.locator('#message').inner_text(),errors)
  page.get_by_role('tab',name='Configurações').click();page.locator('#settings-button-errors').click();page.get_by_role('button',name='Cadastrar questão').click();page.locator('#questionSubject').select_option(label='Bancários e Economia');page.locator('#questionUrl').fill('https://example.com/questao-1');page.locator('#questionTopic').select_option(label='SFN e Mercado');page.get_by_role('button',name='Salvar questão').click();page.wait_for_timeout(200)
  print('after question',page.locator('#managedQuestionsList').inner_text(),errors)
  page.locator('#tab-button-errors').click()
  print('caderno',page.locator('#questionStudyCard').inner_text()[:200],errors)
  page.locator('#errorsSubject').select_option(label='Bancários e Economia')
  page.wait_for_timeout(150)
  page.get_by_role('button',name='Avaliar desempenho').click();page.locator('#attemptDialog input[name=is_correct][value="false"]').check();page.locator('#attemptDialog input[name=confidence][value="1"]').check();page.get_by_role('button',name='Salvar avaliação').click();page.wait_for_timeout(200)
  print('after attempt',page.locator('#questionStudyCard').inner_text()[:150],errors)
  # Simular reload do cliente JS para confirmar persistência no backend
  data=client.get('/api/queue').json()
  print('PERSISTENT:',data['total_topics'],data['total_questions'],data['topics'][0]['attempts'],data['questions'][0]['attempts'])
  page.locator('#errorsRefresh').click();page.wait_for_timeout(200)
  print('after refresh',page.locator('#questionStudyCard').inner_text()[:150],errors)
  assert not errors,errors
  page.locator('#tab-button-settings').click();page.locator('#settings-button-errors').click()
  page.once('dialog',lambda dlg: dlg.accept())
  page.locator('#managedQuestionsList [data-archive-question]').first.click()
  # Arquivar usando ação de configuração (também disponível na pilha).
  page.wait_for_timeout(150)
  assert client.get('/api/queue').json()['total_questions']==0
  page.locator('#manageQuestionsFilter').select_option('archived')
  page.locator('#managedQuestionsList [data-archive-question]').first.click()
  page.wait_for_timeout(150)
  assert client.get('/api/queue').json()['total_questions']==1
  page.locator('#settings-button-cards').click()
  page.once('dialog',lambda dlg: dlg.accept())
  page.locator('#topicsList [data-archive-topic]').first.click()
  page.wait_for_timeout(100)
  # A confirmação nativa é aceita pelo Chromium nesta validação.
  assert client.get('/api/queue').json()['total_topics']==0
  page.locator('#showArchivedCatalog').check()
  page.locator('#topicsList [data-archive-topic]').first.click()
  page.wait_for_timeout(100)
  assert client.get('/api/queue').json()['total_topics']==1
  # Reabrir como uma nova página para conferir que nada dependia do estado anterior de JS.
  again=browser.new_page()
  again.expose_function('bridge',bridge)
  again.set_content(html,wait_until='domcontentloaded')
  again.add_style_tag(content=(root/'app/static/style.css').read_text())
  again.evaluate('''window.fetch=async (path,init={})=>{const r=await window.bridge({url:path,method:init.method||'GET',body:init.body||null});return new Response(r.body,{status:r.status,headers:{'Content-Type':'application/json'}});}''')
  again.add_script_tag(content=(root/'app/static/app.js').read_text())
  again.wait_for_function("document.getElementById('subjectsList').textContent.includes('Bancários e Economia')")
  again.locator('#cardsSubject').select_option(label='Bancários e Economia')
  again.wait_for_timeout(150)
  assert 'SFN e Mercado' in again.locator('#topicStudyCard').inner_text()
  again.locator('#tab-button-settings').click()
  assert 'SFN e Mercado' in again.locator('#topicsList').inner_text()
  print('BROWSER SMOKE: navegação, cadastros, edições, avaliações, refresh, arquivar/restaurar e recarga OK')
  browser.close()
app.dependency_overrides.clear();engine.dispose()
