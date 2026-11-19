"""Instalador da v0.9 sobre a versão v0.8 (branch master, commit 0339567).

Uso: a partir da raiz do clone do repositório:
    python /caminho/para/aplicar_v09.py
    python -m pytest -q

Não executa migrações nem acessa bancos remotos. Faz cópia local .v08.bak
apenas dos arquivos editados antes de alterá-los. É idempotente por marcador.
"""
from pathlib import Path
from shutil import copy2
import sys

REPO = Path.cwd()
RELEASE = Path(__file__).resolve().parent


def replace_once(src: str, old: str, new: str, where: str) -> str:
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f'{where}: esperado um único trecho, encontrados {count}: {old[:110]!r}')
    return src.replace(old, new, 1)


def update(path: str, transform) -> None:
    target = REPO / path
    if not target.is_file():
        raise RuntimeError(f'Não encontrei {path}; execute na raiz do repositório.')
    original = target.read_text(encoding='utf-8')
    if '# Estudo Adaptativo BB — versão 0.9' in original or '/* v0.9' in original or ('version="0.9.0"' in original):
        print(f'Já atualizado: {path}')
        return
    revised = transform(original)
    if revised == original:
        raise RuntimeError(f'Nada mudou em {path}')
    backup = target.with_name(target.name + '.v08.bak')
    if not backup.exists():
        copy2(target, backup)
    target.write_text(revised, encoding='utf-8')
    print(f'Atualizado: {path}')


def models(s: str) -> str:
    s = replace_once(s, 'from datetime import datetime, timezone', 'from datetime import date, datetime, timezone', 'models.py')
    s = replace_once(s, 'from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint',
        'from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint', 'models.py')
    anchor = '\n\nclass Topic(Base):'
    addition = '''\n\nclass NovelPractice(Base):
    """Resultados inéditos por matéria; SEM assunto e sem tentativas individuais."""
    __tablename__ = 'novel_practice'
    __table_args__ = (
        CheckConstraint('total >= 1 AND total <= 10000', name='ck_novel_practice_total'),
        CheckConstraint('correct >= 0 AND correct <= total', name='ck_novel_practice_correct'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id', ondelete='RESTRICT'), nullable=False)
    practice_date: Mapped[date] = mapped_column(Date(), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
'''
    return replace_once(s, anchor, addition + anchor, 'models.py')


def schemas(s: str) -> str:
    s = replace_once(s, 'from datetime import datetime', 'from datetime import date, datetime', 'schemas.py')
    anchor = '\n\nclass SubjectIn(BaseModel):'
    addition = '''\n\nclass NovelPracticeIn(BaseModel):
    subject_id: int
    practice_date: date
    total: int = Field(ge=1, le=10000)
    correct: int = Field(ge=0, le=10000)

    @model_validator(mode='after')
    def validate_correct(self):
        if self.correct > self.total:
            raise ValueError('Os acertos não podem ultrapassar o total de questões.')
        return self


class NovelPracticeOut(NovelPracticeIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    archived_at: datetime | None = None
'''
    return replace_once(s, anchor, addition + anchor, 'schemas.py')


def main(s: str) -> str:
    s = replace_once(s, 'from app.engine import build_queue', 'from app.engine import build_queue\nfrom app.performance import build_performance', 'main.py')
    s = replace_once(s, 'QuestionAttempt, StudySession, Subject, Topic, TopicReview, utcnow',
        'QuestionAttempt, NovelPractice, StudySession, Subject, Topic, TopicReview, utcnow', 'main.py')
    s = replace_once(s, 'from app.schemas import (NewContentIn, QuestionAttemptIn, QuestionIn, QuestionOut,',
        'from app.schemas import (NovelPracticeIn, NovelPracticeOut, NewContentIn, QuestionAttemptIn, QuestionIn, QuestionOut,', 'main.py')
    s = replace_once(s, 'version="0.8.0"', 'version="0.9.0"', 'main.py')
    anchor = '\n\n@api.get("/subjects", response_model=list[SubjectOut])'
    endpoints = '''\n\n@api.get('/novel-practice', response_model=list[NovelPracticeOut])
def list_novel_practice(include_archived: bool = False, subject_id: int | None = None,
                        db: Session = Depends(get_db)):
    query = select(NovelPractice)
    if not include_archived:
        query = query.where(NovelPractice.archived_at.is_(None))
    if subject_id is not None:
        query = query.where(NovelPractice.subject_id == subject_id)
    return db.scalars(query.order_by(NovelPractice.practice_date.desc(), NovelPractice.id.desc())).all()


def ensure_active_novel_subject(db: Session, subject_id: int):
    subject = db.get(Subject, subject_id)
    if subject is None or subject.archived_at is not None:
        raise HTTPException(404, 'Matéria ativa não encontrada.')


@api.post('/novel-practice', response_model=NovelPracticeOut, status_code=status.HTTP_201_CREATED)
def create_novel_practice(payload: NovelPracticeIn, db: Session = Depends(get_db)):
    ensure_active_novel_subject(db, payload.subject_id)
    item = NovelPractice(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@api.patch('/novel-practice/{record_id}', response_model=NovelPracticeOut)
def edit_novel_practice(record_id: int, payload: NovelPracticeIn, db: Session = Depends(get_db)):
    item = db.get(NovelPractice, record_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(404, 'Registro ativo não encontrado.')
    ensure_active_novel_subject(db, payload.subject_id)
    item.subject_id = payload.subject_id
    item.practice_date = payload.practice_date
    item.total = payload.total
    item.correct = payload.correct
    item.updated_at = utcnow()
    db.commit()
    db.refresh(item)
    return item


@api.delete('/novel-practice/{record_id}', response_model=NovelPracticeOut)
def archive_novel_practice(record_id: int, db: Session = Depends(get_db)):
    item = db.get(NovelPractice, record_id)
    if item is None:
        raise HTTPException(404, 'Registro não encontrado.')
    if item.archived_at is None:
        item.archived_at = utcnow()
        item.updated_at = utcnow()
        db.commit()
        db.refresh(item)
    return item


@api.patch('/novel-practice/{record_id}/restore', response_model=NovelPracticeOut)
def restore_novel_practice(record_id: int, db: Session = Depends(get_db)):
    item = db.get(NovelPractice, record_id)
    if item is None:
        raise HTTPException(404, 'Registro não encontrado.')
    ensure_active_novel_subject(db, item.subject_id)
    if item.archived_at is not None:
        item.archived_at = None
        item.updated_at = utcnow()
        db.commit()
        db.refresh(item)
    return item


@api.get('/performance')
def performance(db: Session = Depends(get_db)):
    return build_performance(db)
'''
    return replace_once(s, anchor, endpoints+anchor, 'main.py')


def engine(s: str) -> str:
    s = replace_once(s, 'sample_ok = distinct_count >= 5 and len(attempts) >= 8 and rate >= 0.85',
                     'sample_ok = distinct_count >= 5 and len(attempts) >= 8 and rate >= 0.90', 'engine.py')
    s = replace_once(s, "'varied_questions_85_percent': sample_ok", "'varied_questions_90_percent': sample_ok", 'engine.py')
    s = replace_once(s, 'if samples < 6:', 'if samples < 12:', 'engine.py')
    risk_anchor = '\n\ndef adjusted_risk(raw_risk:'
    audit_code = '''\n\ndef risk_calibration_audit(histories: list[list[Any]], interval_fn, risk_fn,
                           unsuccessful, now: datetime) -> dict[str, Any]:
    """Audita previsões feitas com o passado contra cada revisão seguinte.

    Brier 0–1 só é publicado com 20 eventos; amostra selecionada e heurística.
    Não é avaliação em amostra aleatória nem probabilidade validada.
    """
    pairs: list[tuple[float, int]] = []
    for events in histories:
        for index in range(1, len(events)):
            prior = events[:index]
            at = aware(events[index].created_at)
            if at <= aware(prior[-1].created_at) or at > now:
                continue
            forecast = risk_fn(prior, elapsed_days(prior[-1].created_at, at), interval_fn(prior))
            if forecast is not None:
                pairs.append((forecast / 100, int(bool(unsuccessful(events[index])))))
    if len(pairs) < 20:
        return {'samples': len(pairs), 'brier': None, 'sufficient': False}
    return {'samples': len(pairs),
            'brier': round(sum((p-y)**2 for p,y in pairs) / len(pairs), 4),
            'sufficient': True}
'''
    s = replace_once(s, risk_anchor, audit_code + risk_anchor, 'engine.py')
    # As evidências por assunto derivam do Caderno, nunca do agregado das inéditas.
    anchor = '\n\ndef semi_novel_progress(questions:'
    addition = '''\n\ndef topic_opportunity_bonus(evidence: dict[str, Any]) -> float:
    """Bônus limitado 0–6 baseado em falhas observadas por assunto.

    Sem evidências = zero bônus; vínculo da questão sem tentativas não pontua.
    Amostras pequenas têm peso reduzido. Não utiliza pesos do edital nem dados
    de inéditas agregadas por matéria.
    """
    n = evidence['distinct_questions']
    rate = evidence['question_accuracy_percent']
    if not n or rate is None:
        return 0.0
    gap = max(0.0, 90.0 - rate) / 90.0
    return round(6.0 * gap * min(1.0, n / 5.0), 2)
'''
    s = replace_once(s, anchor, addition + anchor, 'engine.py')
    s = replace_once(s, 'recommended_priority, risk_bonus = ranking_score(priority, risk)\n        state = topic_state(history, evidence)',
        'recommended_priority, risk_bonus = ranking_score(priority, risk)\n'
        '        opportunity_bonus = topic_opportunity_bonus(evidence)\n'
        '        recommended_priority = round(min(100.0, recommended_priority + opportunity_bonus), 2)\n'
        '        state = topic_state(history, evidence)', 'engine.py')
    s = replace_once(s, '    topic_queue = []\n    for topic in topics:',
        '''    # Auditoria não exibida como promessa de probabilidade individual.
    topic_audits = {scope: risk_calibration_audit(
        rows, topic_interval, topic_forgetting_risk,
        lambda r: r.grade <= 2 or bool(getattr(r, 'critical_gap', False)), now)
        for scope, rows in topic_subject_histories.items()}
    question_audits = {scope: risk_calibration_audit(
        rows, question_interval, question_forgetting_risk,
        lambda r: not r.is_correct or r.confidence != 3, now)
        for scope, rows in question_subject_histories.items()}

    topic_queue = []
    for topic in topics:''', 'engine.py')
    s = replace_once(s, "'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,\n            'mastered': mastered",
        "'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,\n"
        "            'opportunity_priority_bonus': opportunity_bonus,\n            'mastered': mastered", 'engine.py')
    s = replace_once(s, "'risk_calibration_adjustment_pp': round(100 * correction, 2),\n            'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,\n            'opportunity_priority_bonus': opportunity_bonus,",
        "'risk_calibration_adjustment_pp': round(100 * correction, 2),\n            'risk_calibration_audit': topic_audits.get(topic.subject_id),\n            'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,\n            'opportunity_priority_bonus': opportunity_bonus,", 'engine.py')
    s = replace_once(s, "'risk_calibration_adjustment_pp': round(100 * correction, 2),\n            'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,\n            'overdue_days':",
        "'risk_calibration_adjustment_pp': round(100 * correction, 2),\n            'risk_calibration_audit': question_audits.get(scope_id),\n            'ranking_score': recommended_priority, 'risk_priority_bonus': risk_bonus,\n            'overdue_days':", 'engine.py')
    # Somente a última reavaliação pode representar retenção atual: um acerto
    # antigo não substitui o fracasso recente realizado antes da janela de 7 dias.
    s = replace_once(s, '''        last_spaced = None
        for i in range(1, len(events)):
            gap = elapsed_days(events[i-1].created_at, aware(events[i].created_at)) or 0.0
            if gap >= 7:
                last_spaced = events[i]''',
        '''        last_spaced = None
        if len(events) >= 2:
            gap = elapsed_days(events[-2].created_at, aware(events[-1].created_at)) or 0.0
            if gap >= 7:
                last_spaced = events[-1]''', 'engine.py')
    return s


def tests(s: str, path: str) -> str:
    if path.endswith('test_priority_and_mastery_v6.py'):
        s = replace_once(s, '''    # Pelo menos 8 tentativas, 7 questões diferentes e 6/7 acertos finais (85,71%).''',
            '''    # Ao menos 8 tentativas, 10 questões diferentes e 9/10 acertos seguros.''', path)
        s = replace_once(s, '''    for i in range(1, 8):
        attempts.append(QuestionAttempt(question_id=i, is_correct=i != 7, confidence=3,
                                        error_type='concept' if i == 7 and concept_pending else 'attention',''',
            '''    for i in range(1, 11):
        attempts.append(QuestionAttempt(question_id=i, is_correct=i != 10, confidence=3,
                                        error_type='concept' if i == 10 and concept_pending else 'attention',''', path)
        s = s.replace("assert report['question_accuracy_percent']>=85", "assert report['question_accuracy_percent']>=90")
        s = s.replace("assert ev['question_accuracy_percent']>=85", "assert ev['question_accuracy_percent']>=90")
        s = replace_once(s, 'attempts[1:]) is False', 'attempts[-4:]) is False', path)
        s = s.replace('# Apenas 7 tentativas em 7 links não bastam para o tamanho mínimo da amostra.', '# Amostra reduzida não basta para declarar domínio.')
        s = s.replace('QuestionAttempt(question_id=7,is_correct=True', 'QuestionAttempt(question_id=10,is_correct=True')
        return s
    if path.endswith('test_semi_novel_risk_v8.py') or path.endswith('test_catalog_management_v5.py'):
        return replace_once(s, "'/static/app.js?v=8'", "'/static/app.js?v=9'", path)
    if path.endswith('smoke_navegador.py'):
        return replace_once(s, '''html=html.replace('<link rel="stylesheet" href="/static/style.css?v=8">','').replace('<script src="/static/app.js?v=8" defer></script>','')''',
            '''html=html.replace('<link rel="stylesheet" href="/static/style.css?v=9">','').replace('<script src="/static/app.js?v=9" defer></script>','')''', path)
    return s


def readme(s: str) -> str:
    s = replace_once(s, '# Estudo Adaptativo BB — versão 0.8', '# Estudo Adaptativo BB — versão 0.9', 'README.md')
    s = s.replace('São **37 testes automatizados**', 'Há testes automatizados')
    additions = '''\n## v0.9 — desempenho em inéditas, por matéria, sem coaching

**Cinco abas, nesta ordem:** Desempenho; Cards; Caderno de erros; Questões Inéditas; Configurações.

- **Questões Inéditas**: um lançamento por data, matéria, quantidade feita e acertos;
  sem assunto, sem cadastrar cada acerto, com edição e exclusão reversível. Os
  resultados são **autodeclarados** e não se atribuem a assuntos.
- **Desempenho**: taxas agregadas corretamente (somatório de acertos / somatório
  de tentativas), faixa de Wilson 95% para amostra registrada e tamanho da amostra,
  sem presumir seleção aleatória. Assuntos usam exclusivamente dados dos Cards e
  links vinculados ao Caderno; quando faltam dados aparece **sem evidências**.
- **Domínio**: exige >=90% de acertos confiáveis no último resultado de cada
  link distinto do Caderno, além das evidências espaçadas e conceituais já exigidas.
  A amostra enviesada do Caderno **não prova 90% em inéditas por assunto**.
- **Ganho esperado sem pesos de prova**: um bônus conservador de 0–6 pontos
  apenas na ordenação local de Cards, baseado em erros já observados no assunto,
  com menor efeito em amostras pequenas. A fórmula-base e a precedência local dos
  itens vencidos permanecem intactas; vincular link sem tentativa não dá bônus.
- **Risco**: segue com correção heurística limitada, agora exige pelo menos 12
  observações temporais antes de qualquer ajuste. Não é probabilidade validada.
- **Sem orientação de respostas**: não há coaching, sugestões de exercícios
  nem correção automática dos tipos de erro; a estudante faz a interpretação.
- Assuntos dominados continuam na fila para manutenção espaçada.
- Sem matriz de cobertura do edital, sem seleção automática de matéria,
  cronômetro, obrigação diária ou peso de matérias na prova.

**Persistência:** migração `0007_novel_practice.py` cria somente a nova tabela
`novel_practice` e seu índice, sem alterar as avaliações anteriores. Atualize
com `alembic upgrade head` antes de iniciar a API. Versão `0.9.0`.

'''
    return replace_once(s, '\n**Atualização:**', '\n'+additions+'**Atualização (histórico v0.8):**', 'README.md')


def main_install() -> None:
    if not (REPO / 'app/engine.py').is_file():
        raise RuntimeError('Entre na raiz de um clone do estudo-adaptativo antes de executar.')
    if (REPO / 'app/performance.py').exists() or (REPO / 'migrations/versions/0007_novel_practice.py').exists():
        raise RuntimeError('Já encontrei arquivos da v0.9. Reveja alterações antes de aplicar novamente.')
    # Pré-validação: nenhuma alteração parcial se o projeto divergir da v0.8.
    ops = {
        'app/models.py': models,
        'app/schemas.py': schemas,
        'app/main.py': main,
        'app/engine.py': engine,
        'README.md': readme,
        '.gitignore': lambda s: s if '*.v08.bak' in s else s + '\n# Backup local do aplicador v0.9\n*.v08.bak\n',
        'tests/test_priority_and_mastery_v6.py': lambda s: tests(s,'tests/test_priority_and_mastery_v6.py'),
        'tests/test_semi_novel_risk_v8.py': lambda s: tests(s,'tests/test_semi_novel_risk_v8.py'),
        'tests/test_catalog_management_v5.py': lambda s: tests(s,'tests/test_catalog_management_v5.py'),
        'scripts/smoke_navegador.py': lambda s: tests(s,'scripts/smoke_navegador.py'),
        'app/static/index.html': html,
        'app/static/app.js': javascript,
        'app/static/style.css': stylesheet,
    }
    prepared = {}
    for name, fn in ops.items():
        path = REPO / name
        if not path.is_file():
            raise RuntimeError('Arquivo esperado ausente: ' + name)
        prepared[name] = fn(path.read_text(encoding='utf-8'))
    # Só escreve após todas as substituições passarem.
    for name, content in prepared.items():
        path = REPO / name
        bak = path.with_name(path.name + '.v08.bak')
        if not bak.exists():
            copy2(path,bak)
        path.write_text(content,encoding='utf-8')
        print('Atualizado:',name)
    for name in ('app/performance.py','migrations/versions/0007_novel_practice.py','tests/test_performance_v9.py'):
        target = REPO/name
        target.parent.mkdir(parents=True,exist_ok=True)
        copy2(RELEASE/name,target)
        print('Criado:',name)
    print('\nVersão 0.9 aplicada localmente. Rode: python -m pytest -q e depois alembic upgrade head.')
    print('As cópias .v08.bak são locais e NÃO devem ser commitadas.')


# As transformações do frontend são definidas abaixo para manter o escopo coeso.


def html(s: str) -> str:
    s = replace_once(s, '<title>Estudo Adaptativo BB · Pilhas contínuas</title>',
        '<title>Estudo Adaptativo BB · v0.9</title>', 'index.html')
    s = s.replace('style.css?v=8', 'style.css?v=9').replace('app.js?v=8', 'app.js?v=9')
    navigation = '''<nav class="tabs" role="tablist" aria-label="Áreas do sistema">
      <button type="button" class="tab active" role="tab" id="tab-button-performance" aria-controls="tab-performance" aria-selected="true" data-tab="performance">Desempenho</button>
      <button type="button" class="tab" role="tab" id="tab-button-cards" aria-controls="tab-cards" aria-selected="false" data-tab="cards">Cards</button>
      <button type="button" class="tab" role="tab" id="tab-button-errors" aria-controls="tab-errors" aria-selected="false" data-tab="errors">Caderno de erros</button>
      <button type="button" class="tab" role="tab" id="tab-button-novel" aria-controls="tab-novel" aria-selected="false" data-tab="novel">Questões Inéditas</button>
      <button type="button" class="tab" role="tab" id="tab-button-settings" aria-controls="tab-settings" aria-selected="false" data-tab="settings">Configurações</button>
    </nav>'''
    original = '''<nav class="tabs" role="tablist" aria-label="Áreas do sistema">
      <button type="button" class="tab active" role="tab" id="tab-button-cards" aria-controls="tab-cards" aria-selected="true" data-tab="cards">Cards</button>
      <button type="button" class="tab" role="tab" id="tab-button-errors" aria-controls="tab-errors" aria-selected="false" data-tab="errors">Caderno de erros</button>
      <button type="button" class="tab" role="tab" id="tab-button-settings" aria-controls="tab-settings" aria-selected="false" data-tab="settings">Configurações</button>
    </nav>'''
    s = replace_once(s, original, navigation, 'index.html')
    performance = '''\n      <section id="tab-performance" role="tabpanel" aria-labelledby="tab-button-performance">
        <div class="section-heading"><div><span class="eyebrow">EVIDÊNCIAS DO SEU ESTUDO</span><h2>Desempenho</h2><p>90% de acertos é a meta individual de cada assunto. Registros de inéditas são agregados por matéria e não representam acertos por assunto.</p></div></div>
        <div class="toolbar"><label class="field filter-field">Visualizar matéria<select id="performanceSubject"><option value="all">Todas as matérias</option></select></label></div>
        <h3 class="v09-heading">Questões inéditas por matéria</h3>
        <div id="performanceSubjects" class="metrics-grid" aria-live="polite"></div>
        <h3 class="v09-heading">Evidências por assunto</h3>
        <p class="panel-help v09-help">Os acertos abaixo vêm de links distintos do Caderno de erros, previamente errados no site. Não são desempenho em inéditas por assunto.</p>
        <div id="performanceTopics" class="panel v09-performance-topics" aria-live="polite"></div>
        <p class="panel-help" id="performanceDisclosure">Sem dados suficientes, os indicadores ficam sem valor. As faixas de Wilson 95% não garantem representatividade.</p>
      </section>
'''
    s = replace_once(s, '<main>\n      <section id="tab-cards" role="tabpanel" aria-labelledby="tab-button-cards">',
        '<main>'+performance+'      <section id="tab-cards" role="tabpanel" aria-labelledby="tab-button-cards" hidden>', 'index.html')
    novel = '''\n      <section id="tab-novel" role="tabpanel" aria-labelledby="tab-button-novel" hidden>
        <div class="section-heading"><div><span class="eyebrow">SEM CLASSIFICAR ASSUNTOS</span><h2>Questões Inéditas</h2><p>Registre somente a data, a matéria, o número de questões feitas e os acertos. Sem tempo e sem metas diárias.</p></div></div>
        <div class="settings-grid">
          <section class="panel"><div class="panel-head"><div><h3 id="novelFormTitle">Novo registro</h3><p>Resultados declarados por matéria.</p></div></div>
            <form id="novelForm" class="v09-form">
              <input type="hidden" id="novelEditId">
              <label class="field">Data<input id="novelDate" type="date" required></label>
              <label class="field">Matéria<select id="novelSubject" required><option value="">Escolha uma matéria</option></select></label>
              <div class="two-fields">
                <label class="field">Questões feitas<input id="novelTotal" type="number" min="1" max="10000" step="1" inputmode="numeric" required></label>
                <label class="field">Acertos<input id="novelCorrect" type="number" min="0" max="10000" step="1" inputmode="numeric" required></label>
              </div>
              <div class="v09-preview" id="novelPreview" aria-live="polite">Preencha as quantidades para calcular seu aproveitamento.</div>
              <div class="actions"><button class="button primary" id="novelSaveBtn" type="submit">Salvar registro</button><button class="button outline" id="novelCancel" type="button" hidden>Cancelar edição</button></div>
            </form>
          </section>
          <section class="panel"><div class="panel-head"><div><h3>Histórico de inéditas</h3><p>É possível editar ou excluir um registro sem perder as demais avaliações.</p></div></div>
            <label class="checkbox-row"><input type="checkbox" id="novelShowArchived"> Exibir registros excluídos (restauráveis)</label>
            <div id="novelRecordsList" class="registered-list" aria-live="polite"></div>
          </section>
        </div>
      </section>
'''
    s = replace_once(s, '      <section id="tab-settings" role="tabpanel"', novel+'      <section id="tab-settings" role="tabpanel"', 'index.html')
    s = replace_once(s, 'Estudo Adaptativo BB · v0.7 · Tudo o que você salvar permanece no PostgreSQL',
        'Estudo Adaptativo BB · v0.9 · Registros mantidos no PostgreSQL', 'index.html')
    return s


def stylesheet(s: str) -> str:
    if '/* v0.9' in s:
        raise RuntimeError('style.css parece já atualizado')
    return s + '''
/* v0.9 — somente leitura dos indicadores e registro agregado, sem coaching. */
.v09-heading{font-size:17px;letter-spacing:-.25px;margin:22px 0 12px;color:#303c58}
.metrics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.v09-metric{padding:20px;border:1px solid var(--line);background:white;border-radius:14px;display:grid;gap:10px}
.v09-metric h4{font-size:14px;margin:0;font-weight:750;overflow-wrap:anywhere}
.v09-metric .big-number{font-size:32px;font-weight:800;letter-spacing:-1.3px;color:#30479e}
.v09-metric .panel-help{margin-top:0}
.v09-performance-topics{padding:12px 22px}
.v09-performance-topics .list-item{align-items:start}
.v09-topic-info{display:grid;gap:5px;min-width:0}
.v09-topic-value{font-size:12px;text-align:right;color:#344360;max-width:300px;line-height:1.5}
.v09-topic-value strong{font-size:15px;display:block}
.v09-help{margin:0 0 14px}
.v09-form{display:grid;gap:18px}
.v09-preview{background:#f2f5fb;border:1px solid #e0e7f2;border-radius:9px;padding:13px;color:#52617b;font-size:13px;line-height:1.5}
.v09-preview strong{color:#33499c}
.v09-empty{font-size:13px;line-height:1.5;color:#748197;padding:16px 4px}
@media(max-width:540px){.v09-performance-topics .list-item{gap:8px}.v09-topic-value{text-align:left}}
'''


def javascript(s: str) -> str:
    s = replace_once(s, '/* v0.8 — risco empírico conservador, filas isoladas e evolução semi-inédita. */',
        '/* v0.9 — desempenho primeiro, inéditas por matéria e prioridade local sem coaching. */', 'app.js')
    s = replace_once(s, 'subjects: [], allSubjects: [], topics: [], allTopics: [], allQuestions: [],',
        'subjects: [], allSubjects: [], topics: [], allTopics: [], allQuestions: [], novelRecords: [], performance: null,', 'app.js')
    s = replace_once(s, "currentTab: 'cards', settingsTab: 'cards'", "currentTab: 'performance', settingsTab: 'cards'", 'app.js')
    s = replace_once(s, "['cards', 'errors', 'settings']", "['performance', 'cards', 'errors', 'novel', 'settings']", 'app.js')
    s = replace_once(s, "const route = tab === 'settings' ? `#configuracoes/${subtab}` : tab === 'errors' ? '#caderno' : '#cards';",
        "const route = tab === 'settings' ? `#configuracoes/${subtab}` : tab === 'errors' ? '#caderno' : tab === 'novel' ? '#ineditas' : tab === 'cards' ? '#cards' : '#desempenho';", 'app.js')
    s = replace_once(s, "else if (hash === '#caderno') goTo('errors', 'cards', false);\n  else goTo('cards', 'cards', false);",
        "else if (hash === '#caderno') goTo('errors', 'cards', false);\n   else if (hash === '#ineditas') goTo('novel', 'cards', false);\n   else if (hash === '#cards') goTo('cards', 'cards', false);\n   else goTo('performance', 'cards', false);", 'app.js')
    s = replace_once(s, "updateSelect('questionSubject', selectOptions(active, 'Selecione a matéria'));",
        "updateSelect('questionSubject', selectOptions(active, 'Selecione a matéria'));\n"
        "  updateSelect('novelSubject', selectOptions(active, 'Selecione a matéria'));\n"
        "  updateSelect('performanceSubject', '<option value=\"all\">Todas as matérias</option>'+selectOptions(active,'',false),'all');", 'app.js')
    s = replace_once(s, 'const [allSubjects,allTopics,allQuestions,openSession] = await Promise.all([',
        'const [allSubjects,allTopics,allQuestions,openSession,novelRecords,performance] = await Promise.all([', 'app.js')
    s = replace_once(s, "api('/questions?include_archived=true'),api('/sessions/open'),",
        "api('/questions?include_archived=true'),api('/sessions/open'),\n"
        "    api('/novel-practice?include_archived=true'),api('/performance'),", 'app.js')
    s = replace_once(s, 'state.allSubjects=allSubjects;state.allTopics=allTopics;state.allQuestions=allQuestions;',
        'state.allSubjects=allSubjects;state.allTopics=allTopics;state.allQuestions=allQuestions;\n'
        '  state.novelRecords=novelRecords;state.performance=performance;', 'app.js')
    s = replace_once(s, 'updateOptions();renderCatalog();renderManagedQuestions();',
        'updateOptions();renderCatalog();renderManagedQuestions();renderNovelRecords();renderPerformance();', 'app.js')
    s = replace_once(s, "['varied_questions_85_percent',`Acertos ≥ 85% em questões distintas (${e.distinct_questions} questões; ${e.question_accuracy_percent??'—'}% de acertos)`]",
        "['varied_questions_90_percent',`Acertos confiáveis ≥ 90% em links distintos do caderno (${e.distinct_questions} links; ${e.question_accuracy_percent??'—'}%)`]", 'app.js')
    s = replace_once(s, 'const riskBump = entry.risk_priority_bonus || 0;',
        'const riskBump = entry.risk_priority_bonus || 0;\n  const opportunityBump=entry.opportunity_priority_bonus || 0;', 'app.js')
    s = replace_once(s,
        "${riskBump?` <small>(inclui +${riskBump.toFixed(1)} risco)</small>`:''}",
        "${riskBump?` <small>(+${riskBump.toFixed(1)} risco)</small>`:''}${opportunityBump?` <small>(+${opportunityBump.toFixed(1)} oportunidade observada)</small>`:''}", 'app.js')
    s = replace_once(s, 'Prioridade-base ${Number(entry.priority).toFixed(1)}/100 + risco (até 8 pontos) = ${Number(entry.ranking_score??entry.priority).toFixed(1)}/100 na recomendação.',
        'Prioridade-base ${Number(entry.priority).toFixed(1)}/100 + risco (até 8 pontos) + oportunidade observada (até 6 pontos) = ${Number(entry.ranking_score??entry.priority).toFixed(1)}/100 na recomendação.', 'app.js')

    insert = r'''
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
'''
    s = replace_once(s, 'function openSubject(id=null) {', insert+'\nfunction openSubject(id=null) {', 'app.js')

    actions = r'''
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
  const payload={subject_id:Number($('novelSubject').value),practice_date:$('novelDate').value,total,correct};
  await api(id?`/novel-practice/${id}`:'/novel-practice',id?'PATCH':'POST',payload);
  await reloadAll();resetNovelForm();notice(id?'Registro de inéditas corrigido.':'Questões inéditas registradas.');
});});
'''
    s = replace_once(s, "$('logoutBtn').addEventListener('click',", actions+"$('logoutBtn').addEventListener('click',", 'app.js')
    s = replace_once(s,
        "button[data-archive-subject],button[data-archive-topic],button[data-archive-question]'",
        "button[data-archive-subject],button[data-archive-topic],button[data-archive-question],button[data-edit-novel],button[data-delete-novel],button[data-restore-novel]'", 'app.js')
    s = replace_once(s, "if(el.dataset.editSubject){openSubject(Number(el.dataset.editSubject));return;}",
        "if(el.dataset.editNovel){editNovel(Number(el.dataset.editNovel));return;}\n"
        "  if(el.dataset.deleteNovel){safe(async()=>{if(!window.confirm('Excluir este registro de inéditas? Ele poderá ser restaurado.'))return;await api(`/novel-practice/${Number(el.dataset.deleteNovel)}`,'DELETE');await reloadAll();resetNovelForm();notice('Registro excluído; histórico preservado.');});return;}\n"
        "  if(el.dataset.restoreNovel){safe(async()=>{await api(`/novel-practice/${Number(el.dataset.restoreNovel)}/restore`,'PATCH');await reloadAll();notice('Registro restaurado.');});return;}\n"
        "  if(el.dataset.editSubject){openSubject(Number(el.dataset.editSubject));return;}", 'app.js')
    s = replace_once(s, "parseRoute();\nsafe(async()=>{", "resetNovelForm();\nparseRoute();\nsafe(async()=>{", 'app.js')
    return s


if __name__ == '__main__':
    try:
        main_install()
    except Exception as error:
        print('Erro ao aplicar a v0.9:',error,file=sys.stderr)
        sys.exit(1)
