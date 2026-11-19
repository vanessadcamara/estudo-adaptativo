# Estudo Adaptativo BB — v0.16

Sistema pessoal de estudo para **Banco do Brasil — Escriturário (Agente Comercial)**, com filas adaptativas independentes por matéria. Interface FastAPI + JavaScript; histórico persistido no **PostgreSQL configurado em `DATABASE_URL`** (por exemplo, Neon). As avaliações não são armazenadas no navegador.

## v0.16 — Otimização completa FSRS-6 fora do Render

- **Treinamento oficial dos 21 parâmetros FSRS-6** via `fsrs[optimizer]`, executado somente no trabalhador externo `python -m app.optimize_retention --apply`, nunca ao encerrar uma sessão. O **Render gratuito recebe apenas parâmetros aprovados** armazenados no PostgreSQL/Neon.
- **Gatilho automático já codificado**: o workflow `.github/workflows/optimize-fsrs.yml` executa aos domingos 09:00 UTC (05:00 Manaus) e pode ser acionado manualmente. Para a execução real, publique o código no GitHub, ative GitHub Actions e configure o segredo `FSRS_DATABASE_URL` com uma conexão PostgreSQL Neon autorizada. Nenhuma credencial está no repositório.
- **Regra mínima real da biblioteca oficial:** pelo menos 512 recuperações espaçadas no subconjunto de treinamento de **cada matéria/tipo**, além de 100 observações posteriores em holdout, 25 itens distintos no treino, 12 no holdout, 25 erros de recuperação no treino e diversidade em três faixas de intervalo. Sem essas condições, **não** treina nem ativa o novo modelo.
- **Validação temporal sem vazamento:** logs usados no otimizador têm data estritamente anterior ao início do holdout. Previsões FSRS são avaliadas antes de cada resultado observado. O candidato precisa melhorar Brier frente ao FSRS padrão em ≥ 0,005, não piorar a regra v0.14 além de 0,005 e manter erro de calibração ≤ 10 pontos percentuais. Os critérios são salvaguardas de engenharia, não validação científica definitiva.
- **Fallback e monitoramento:** falhas ou candidatos rejeitados não substituem os pesos aprovados. Após evidências novas suficientes, degradação pronunciada pode desativar o modelo completo, retornando à calibração leve/v0.14. Cada tentativa tem trilha no banco.
- **Estrutura preservada:** modelos independentes de Cards (`topic:<matéria>`) e Caderno de erros (`question:<matéria>`); sem misturar avaliações de questões inéditas não vinculadas. A fila continua com diversificação de 3/12 sessões, proteção de retorno, intervalos limitados (mudança máxima de 25%) e nenhuma repetição do mesmo item avaliado na sessão.
- **Interface:** indica se o intervalo veio da regra-base, da calibração leve ou do FSRS-6 completo e mostra métricas de validação e último status. Essa taxa de retenção não equivale a 90% de acertos na prova.

### Uso do otimizador

```bash
# No seu computador ou executor independente, com DATABASE_URL configurado:
python -m pip install -e '.[optimizer]'
python -m app.optimize_retention             # simulação: não grava nada
python -m app.optimize_retention --apply     # grava modelos validados
python -m app.optimize_retention --apply --scope topic:1
```

**Não execute treinamento via endpoint FastAPI.** Consulte `docs/OTIMIZADOR_FSRS_V016.md` para configuração do workflow e limites. Faça backup do Neon antes de aplicar a migração 0011. **O pacote local ainda não executa esse workflow: a ativação agendada depende de publicá-lo e fornecer a conexão ao Neon no GitHub Actions.**

## O que a v0.15 preserva da v0.14

- **Uma sessão, uma avaliação por item:** o mesmo assunto ou a mesma questão avaliada não reaparece na mesma sessão. Questões diferentes sobre um mesmo assunto são permitidas.
- **Filas por matéria:** você escolhe qual estudar; vencimento não força estudo diário nem interfere na fila de outra disciplina.
- **Alternância em 3 sessões:** reduz a posição dos itens revisados repetidamente nas últimas três sessões com atividade naquela matéria.
- **Equilíbrio em 12 sessões:** concede bônus moderado a itens elegíveis pouco revisitados nesse período.
- **Proteção de retorno:** depois de sete visitas com atividade à matéria sem avaliar um item elegível (vencido ou nunca revisado), ele recebe precedência sobre itens não protegidos, sem obrigar você a estudar naquele dia. Se vários itens estiverem protegidos, os mais adiados recebem preferência. Pular é permitido.
- **Proteção contra atraso:** a penalização de repetição é reduzida quando o atraso em relação ao intervalo recomendado aumenta.
- **Espaçamento e retenção observada:** intervalos-base de 1 a 60 dias são modulados conservadoramente por recuperações feitas após intervalos reais. Com poucas evidências, a regra-base permanece.
- **Estudo inicial separado de retenção:** o questionário do primeiro contato registra aprendizagem, mas não é computado como revisão espaçada.
- **Questionário v0.14 em duas etapas:** primeiro a estudante recupera e registra o que lembrou **antes de olhar** (incluindo eventual necessidade de ajuda). Só depois a interface exibe precisão e lacunas, a serem preenchidas após a conferência. A primeira etapa é escondida para evitar alteração retrospectiva após consultar.
- **Aplicação independente opcional:** `não testei` (NULL), `não consegui` (0), `parcial` (1), `questão diferente sem consulta` (2). Não testar não é penalizado; uma tentativa malsucedida limita a nota a 2, uma parcial a 3. A aplicação independente bem-sucedida só valida a evidência de questões diferentes se também houve nota 4.
- **Nota inferida mais rigorosa:** recuperação consultada ou com erros conceituais importantes limita a nota a 1; dicas e lacunas moderadas limitam a 2. A nota 4 exige recuperação completa, precisão, nenhuma ajuda e nenhuma lacuna.
- **Auditoria por intervalo real (Cards e Caderno):** recuperações em dias diferentes são agrupadas por 1–3, 4–7, 8–14, 15–30 e 31+ dias. O detalhe da prioridade mostra quantidade e acertos por faixa, com ressalva de autoavaliação ou de familiaridade com questões antigas.
- **Validação conservadora antes de estender o intervalo além do prazo-base:** para ajuste extra positivo de até 25%, exige pelo menos 8 recuperações recentes em intervalos comparáveis ao intervalo-base (60%–160%), pelo menos 85% de sucessos e limite inferior de Wilson ≥70%. Nos Cards, exige ainda 8 observações com questionário estruturado. A evidência agregada por matéria **não** autoriza aumento individual sem histórico suficiente. Falhas recorrentes antes/próximo do vencimento podem reduzir o prazo em até 25%. **As regras-base de intervalos por nota/confiança permanecem**, não constituem calibração estatística.
- **Questionário de revisão é autoavaliação**, não prova objetiva de retenção. Repetição de uma questão do Caderno não equivale a prova inédita.
- **Questões inéditas:** registra total de tentativas e acertos por matéria; condições semelhantes à prova são opcionais. Esses acertos **não são atribuídos artificialmente a assuntos específicos**.
- **Domínio:** critérios exigentes de recuperações espaçadas, ausência de lacunas, explicação, aplicação e resultados em links diferentes do Caderno de erros. Não equivale a garantia de 90% na prova.

## Modelo estatístico FSRS-6 preparado para ativação automática (v0.15)

A v0.15 integrou **`fsrs` (Py-FSRS, biblioteca oficial da comunidade Open Spaced Repetition)** para reconstruir o estado FSRS a partir de cada histórico elegível. A meta de retenção prevista pelo modelo é **90%**, diferente da meta de **90% de acertos no concurso**. As estimativas são incertas porque Cards abrangem conceitos amplos e as questões do Caderno podem se tornar familiares após repetição.

- **Dois perfis independentes por matéria**: `topic:<id>` para Cards e `question:<id>` para questões do Caderno; registros sem matéria usam `question:0`. Dados de Português nunca calibram Matemática e resultados de inéditas por matéria não são atribuídos artificialmente a assuntos.
- **Mapeamento conservador de avaliações:** notas 0–2, lacunas críticas ou recuperação assistida dos Cards → *Again*; recuperação boa → *Good*; nota 4 independente, correta e completa → *Easy*. No Caderno, erros e acertos inseguros são tratados como recuperação não confirmada; acerto com confiança máxima → *Good*. Registros legados sem questionário estruturado ou sem confiança não são usados no treino FSRS. Os registros continuam no PostgreSQL.
- **Três fases**: `observando` (coleta), `validando` (testes de calibração) e `ativo` (modelo passou os critérios). Até `ativo`, o intervalo continua usando a regra conservadora v0.14. Caso o desempenho do modelo piore ou haja indisponibilidade da biblioteca, o fallback permanece.
- **Ativação automática na conclusão da sessão**, sem depender de mudar o código: exige **180 observações de treinamento e 50 de validação**, no mínimo **18 itens distintos**, **12 falhas no treinamento**, intervalos nas três faixas (1–3, 4–14, 15+ dias) e Brier no conjunto de validação significativamente favorável à v0.14 (melhora ≥ 0,005), não pior que FSRS não calibrado por mais de 0,005 e erro absoluto de calibração ≤ 12 pontos percentuais. Esses limites são parâmetros de engenharia, não certificação estatística.
- **Treino e validação temporal separados**: os 80% mais antigos dos eventos elegíveis estimam um ajuste limitado de estabilidade FSRS; os 20% mais recentes ficam reservados para validação, não participam do ajuste. O modelo registra contagem de sucessos/falhas, faixas temporais, probabilidades previstas e observadas e **Brier**. O histórico das validações também é salvo.
- **Uso seguro após ativação**: previsão FSRS de risco de esquecimento passa a influenciar a fila; o intervalo previsto só pode alterar o intervalo v0.14 em até **25% por ciclo**, com limites de **1 a 60 dias**, e os Cards não dominados continuam limitados a **30 dias**. A diversificação de 3/12 sessões, a proteção de retorno, as filas independentes e a proibição de repetição dentro da sessão seguem intactas.
- **Baixo custo no Render gratuito**: a calibração é leve e executada quando a sessão é concluída, sem carregar PyTorch. A biblioteca oficial FSRS-6 é usada para as estimativas e estados de memória; o otimizador completo dos 21 parâmetros FSRS permanece fora do processo web. Na **v0.16**, uma rotina independente com `fsrs[optimizer]` executa esse treino semanalmente (após publicação da automação e configuração do segredo), valida e grava pesos aprovados no banco. O processo web continua usando apenas `fsrs` leve.
- **Diagnósticos na interface e API**: cada item informa fonte do intervalo, estágio, estabilidade e recuperação previstas; o resumo por matéria mostra métricas do modelo. Rotas `GET /api/retention-models` e `GET /api/retention-models/history?scope=topic:1` (autenticadas) consultam estado e evolução, sem exportar dados.

**Limites importantes:** não há alegação de equivalência com o Anki em predição individual; os questionários são autoavaliações, itens repetidos têm viés de familiaridade, amostras são selecionadas e a validação temporal não constitui ensaio científico. Por isso, os indicadores mostram estimativas e a v0.14 permanece como alternativa segura. A v0.16 também prepara a ativação do treinamento completo, condicionada à automação externa e à validação de evidências.

## Prioridade versus progresso

A pontuação-base dos **Cards** é:

`P = 0,35D + 0,30T + 0,25E + 0,10I`, com componentes entre 0 e 100:

- `D`: dificuldade de recuperação;
- `T`: urgência temporal;
- `E`: falhas de memória registradas;
- `I`: importância cadastrada para o assunto.

**Os pesos 35/30/25/10 são fixos.** O sistema recalcula os componentes e aplica ajustes à **ordenação**, sem modificar esses pesos. Também considera risco estimado, dificuldades observadas, bônus de vencimento, frequência nas últimas três e doze sessões, atraso e proteção por adiamento. A pontuação **relativa de ordenação** pode ficar negativa ou superar 100; ela **não** é porcentagem de acertos, probabilidade de esquecimento ou nota da prova. A precedência de um item protegido pode influenciar a posição mesmo com menor pontuação numérica.

O **progresso** de um assunto aparece separadamente como *Em aprendizagem*, *Em consolidação* ou *Dominado*, com uma lista de evidências atendidas e pendentes. Estudo inicial não constitui prova de retenção após dias. O intervalo atual e o intervalo-base ficam disponíveis nas explicações. A precisão da previsão ainda precisa ser avaliada empiricamente ao longo de várias sessões.

As questões têm uma fórmula de prioridade própria, baseada em erros, acertos, confiança, histórico e tempo. **Não usam a fórmula dos Cards.**

### Botão «Concluir sessão e atualizar fila»

A fila **já é recalculada quando você salva uma revisão ou tentativa**. Esse botão serve a outra finalidade:

1. Finalizar a sessão atual, consolidando seu resumo sem perder as avaliações.
2. Abrir **imediatamente** uma nova sessão de estudo.
3. Exibir as recomendações atualizadas, inclusive itens que foram avaliados na sessão anterior, considerando toda a memória curta/longa e seus prazos.

O botão **não** recalibra os coeficientes 35/30/25/10. A interface mostra o identificador da sessão atual e a última conclusão a partir do **banco de dados**, não de um horário salvo em `localStorage`.

Concluir uma sessão não é obrigatório ao final de cada dia. A contagem de sessões da matéria considera **apenas sessões com atividade naquela matéria**, não cliques vazios. A mudança de sessão se aplica às abas de Cards e Caderno de erros, que compartilham a mesma sessão técnica.

## Uso

1. Em **Configurações**, cadastre as matérias e os assuntos.
2. Em **Cards**, selecione a matéria. Registre o **estudo inicial** na primeira visita ou avalie a **recuperação** após tentar lembrar sem consulta.
3. Em **Caderno de erros**, adicione questões ou links da matéria e registre acerto, confiança e tipo opcional de erro.
4. Em **Questões Inéditas**, registre o resultado total por matéria (por exemplo, 7/10), sem precisar classificar cada questão.
5. Quando quiser iniciar outra passagem, clique em **Concluir sessão e atualizar fila**.
6. Em **Desempenho**, acompanhe as evidências separadamente: inéditas por matéria e histórico de revisão por assunto.

## Instalação e deploy

Requisitos: Python 3.11+, PostgreSQL e variáveis `DATABASE_URL`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `APP_SECRET_KEY` (mín. 32 caracteres). Consulte `.env.example`. **Nunca publique senhas, tokens ou URLs com credenciais no repositório.**

```bash
python -m pip install -e '.[dev]'
alembic upgrade head
python -m pytest -q
uvicorn app.main:app --reload
```

Em produção, use `APP_ENV=production`. A configuração `render.yaml` executa `alembic upgrade head` antes de subir a aplicação. As migrações **`0008_v13_assessments.py`** (questionário) e **`0009_v14_application_retention.py`** (resultado opcional de aplicação) e **`0010_v15_fsrs_profiles.py`** (perfis FSRS e trilha de validação) e **`0011_v16_full_fsrs_optimizer.py`** (parâmetros otimizados e auditoria) preservam os registros anteriores; em linhas legadas, o novo campo fica `NULL`. **Faça backup do PostgreSQL antes de aplicar atualizações.**

O plano gratuito da Render pode suspender o serviço web; isso não apaga automaticamente um banco Neon separado. A persistência real depende do `DATABASE_URL` da aplicação.

### API principal

| Rota | Finalidade |
| --- | --- |
| `GET /api/queue?subject_id=...` | Fila prévia da matéria |
| `POST /api/sessions` | Abre ou reutiliza sessão ativa |
| `GET /api/sessions/open` | Consulta sessão ativa |
| `GET /api/sessions/{id}/queue?subject_id=...` | Recomendações sem itens avaliados nesta sessão |
| `GET /api/sessions/{id}/progress` | Itens avaliados nesta sessão |
| `POST /api/sessions/{id}/topic-reviews` | Salva revisão estruturada ou formulário antigo |
| `POST /api/sessions/{id}/new-content` | Registra estudo inicial |
| `POST /api/sessions/{id}/question-attempts` | Registra tentativa de questão |
| `POST /api/sessions/{id}/refresh` | Encerra sessão e consolida histórico (a interface chama `/api/sessions` em seguida) |
| `GET /api/dashboard` | Estatísticas e últimas conclusões com horário persistido |
| `GET /api/performance` | Evidências de desempenho por matéria e assunto |
| `GET /api/retention-models` | Modelos FSRS por matéria/tipo, fase, Brier e validação temporal |
| `GET /api/retention-models/history?scope=topic:1` | Histórico de calibrações, com limite paginável de registros |

As ações exigem autenticação e alterações usam proteção CSRF. A aplicação foi concebida para uma conta administrativa pessoal.

## Validação e limites

Execute `python -m pytest -q` para testes automatizados. O aplicativo é um **auxiliar de decisão**, não uma garantia de aprovação ou 90% de acertos. Os limiares de crescimento da v0.14 e os portões automáticos da v0.15 são salvaguardas heurísticas para prudência, **não** um modelo cientificamente validado; dados de autoavaliação e questões repetidas têm vieses. O desempenho em questões diferentes, com condições próximas às da prova e amostras suficientes, continua sendo evidência externa importante. Não há atualmente garantia de cobertura de todo o edital: os assuntos não cadastrados não entram nas filas.
