"""Smoke-test opcional de interface: requer Playwright e Chromium instalados."""
import json, os, re, sys
from pathlib import Path
from argon2 import PasswordHasher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ.update({'APP_ENV':'test','APP_SECRET_KEY':'1234567890'*7,
'ADMIN_USERNAME':'estudante','ADMIN_PASSWORD_HASH':PasswordHasher(time_cost=1,memory_cost=8192).hash('SenhaTesteSegura!123')})
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
    assert login.status_code==200, login.text
    csrf=login.json()['csrf_token']
    headers={'X-CSRF-Token':csrf}
    subject=client.post('/api/subjects',headers=headers,json={'name':'Conhecimentos Bancários'}).json()['id']
    topic=client.post('/api/topics',headers=headers,json={'subject_id':subject,'title':'Redesconto'}).json()['id']
    question=client.post('/api/questions',headers=headers,json={'subject_id':subject,'url':'https://example.org/questao1'}).json()['id']
    def bridge(req):
        kw={}
        if req.get('body') is not None: kw['json']=json.loads(req['body'])
        result=client.request(req['method'],req['url'],headers=headers,**kw)
        return {'status':result.status_code,'body':result.text}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page()
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.expose_function('bridge',bridge)
        html=(root/'app/static/index.html').read_text()
        html=re.sub(r'<script src="/static/app.js\?v=\d+" defer></script>','',html)
        html=re.sub(r'<link rel="stylesheet" href="/static/style.css\?v=\d+">','',html)
        page.set_content(html,wait_until='domcontentloaded')
        page.add_style_tag(content=(root/'app/static/style.css').read_text())
        page.evaluate('''window.fetch=async (url,init={})=>{const r=await window.bridge({url,method:init.method||'GET',body:init.body||null});return new Response(r.body,{status:r.status,headers:{'Content-Type':'application/json'}});};void 0''')
        page.add_script_tag(content=(root/'app/static/app.js').read_text())
        page.wait_for_function("document.querySelector('#cardsSubject option[value=\""+str(subject)+"\"]') !== null")
        page.locator('#tab-button-cards').click()
        page.locator('#cardsSubject').select_option(str(subject))
        page.wait_for_function("document.querySelector('#topicStudyCard').textContent.includes('Redesconto')")
        page.locator('#topicStudyCard details.mastery-details summary').first.click()
        details=page.locator('#topicStudyCard .mastery-content').inner_text()
        assert 'últimas 3 sessões' in details and 'últimas 12' in details, details
        assert 'não é sua porcentagem de acertos' in details
        page.locator('#topicStudyCard button[data-action="finish-topic"]').click()
        assert not page.locator('#reviewAfter').is_visible()
        page.locator('#reviewDialog input[name="recall_level"][value="3"]').check()
        page.locator('#reviewDialog input[name="assistance_level"][value="0"]').check()
        page.locator('#confirmReviewRecall').click()
        assert page.locator('#reviewAfter').is_visible()
        assert not page.locator('#reviewBefore').is_visible()
        for field,value in [('accuracy_level','3'),('gap_level','0'),('difficulty','1'),('application_level','2')]:
            page.locator(f'#reviewDialog input[name="{field}"][value="{value}"]').check()
        page.locator('#reviewDialog button[type="submit"]').click()
        page.wait_for_function("document.querySelector('#topicStudyCard').textContent.includes('Você percorreu esta pilha')",timeout=3500)
        open_before=client.get('/api/sessions/open').json()['id']
        page.locator('#cardsRefresh').click()
        page.wait_for_function("document.querySelector('#topicStudyCard').textContent.includes('Redesconto')")
        open_after=client.get('/api/sessions/open').json()['id']
        assert open_after!=open_before
        assert 'Última conclusão:' in page.locator('#cardsRefreshInfo').inner_text()
        assert client.get('/api/dashboard').json()['recent_sessions'][0]['id']==open_before
        page.locator('#tab-button-errors').click()
        page.locator('#errorsSubject').select_option(str(subject))
        page.wait_for_function("document.querySelector('#questionStudyCard').textContent.includes('Entenda a prioridade e o histórico desta questão')")
        page.locator('#questionStudyCard details.mastery-details summary').first.click()
        question_details=page.locator('#questionStudyCard .mastery-content').inner_text()
        assert 'Caderno de erros' in question_details
        page.locator('#questionStudyCard button[data-action="assess-question"]').click()
        page.locator('#attemptDialog input[name="is_correct"][value="false"]').check()
        page.locator('#attemptDialog input[name="confidence"][value="1"]').check()
        page.locator('#attemptDialog button[type="submit"]').click()
        page.wait_for_function("document.querySelector('#questionStudyCard').textContent.includes('Questões desta sessão concluídas')")
        page.locator('#errorsRefresh').click()
        page.wait_for_function("document.querySelector('#questionStudyCard').textContent.includes('Entenda a prioridade e o histórico desta questão')")
        assert client.get('/api/queue?subject_id='+str(subject)).json()['questions'][0]['attempts'] == 1
        assert not errors,errors
        print('BROWSER v0.14: Cards e Caderno reiniciados, resultados salvos, progresso explicado, sem erros JS')
        browser.close()
app.dependency_overrides.clear()
engine.dispose()
