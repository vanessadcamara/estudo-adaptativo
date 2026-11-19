# Estudo Adaptativo BB — versão 0.11

**Sistema pessoal de revisão adaptativa para Banco do Brasil — Escriturário (Agente Comercial).** A interface oferece **cinco abas**: Desempenho, Cards, Caderno de erros, Questões Inéditas, Configurações. Sem cronômetro, sem cotas diárias e sem calendário obrigatório.

A aplicação entrega o frontend pelo próprio **FastAPI** e persiste revisões, tentativas e sessões no **PostgreSQL** (local ou Neon). Login com senha Argon2, sessão protegida por cookie e controle CSRF.

## v0.11 — alternância flexível entre sessões

- Dentro da sessão, o mesmo card ou a mesma questão já avaliados não voltam à fila. Duas questões diferentes do mesmo assunto continuam permitidas.
- Entre sessões, as três sessões anteriores **da própria matéria** orientam a diversificação, mesmo quando a disciplina é estudada só uma vez por semana.
- A manutenção vencida recebe bônus de preferência (12–20 pontos), mas não bloqueia itens não vencidos. Um item muito repetido recebe penalidade relativa (30 pontos por sessão excedente, até 90).
- Itens revistos muito antes do prazo podem receber penalidade de 12 pontos, para não desfazer o espaçamento conquistado.
- A fórmula de prioridade, as estimativas de risco, os critérios de domínio e os intervalos de 1–60 dias permanecem independentes da ordenação diversificada.
- A interface mostra a pontuação real de ordenação e seus ajustes. São heurísticas para organizar a fila, não garantias de retenção nem de 90% de acertos.

## Histórico: v0.9 — desempenho em inéditas, por matéria, sem coaching

**Cinco abas, nesta ordem:** Desempenho; Cards; Caderno de erros; Questões Inéditas; Configurações.

- **Questões Inéditas:** um lançamento por data, matéria, quantidade feita e acertos; sem assunto, sem cadastrar cada acerto, com edição e exclusão reversível. Os resultados são **autodeclarados** e não se atribuem a assuntos.
- **Desempenho:** percentual de acertos e faixa de incerteza Wilson 95% por matéria usando somente os registros declarados em Questões Inéditas. Por assunto, exibe evidências separadas dos Cards e dos links do Caderno de erros. **Não atribui inéditas a assuntos.** Sem histórico, os percentuais ficam vazios. Taxas agregadas corretas (somatório de acertos / somatório de tentativas), faixa de Wilson 95% para amostra registrada e tamanho da amostra, sem presumir seleção aleatória.
- **Domínio:** meta de pelo menos 90% nos resultados distintos do Caderno, sem chutes, mais confirmações de recuperação espaçada, conceito e explicação. Essa métrica não é garantia de 90% em questões inéditas por assunto. Exige >=90% de acertos confiáveis no último resultado de cada link distinto do Caderno, além das evidências espaçadas e conceituais já exigidas. A amostra enviesada do Caderno **não prova 90% em inéditas por assunto**.
- **Prioridade:** soma até 6 pontos por oportunidade observada nos assuntos com erros, conservando fórmula-base, priorização de manutenção vencida e separação por matéria. Um bônus conservador de 0–6 pontos apenas na ordenação local de Cards, baseado em erros já observados no assunto, com menor efeito em amostras pequenas. A fórmula-base e a precedência local dos itens vencidos permanecem intactas; vincular link sem tentativa não dá bônus.
- **Risco:** correção conservadora com no mínimo 12 observações e auditoria retrospectiva, com pontuação Brier divulgada pela API somente após 20 observações; sem pretender probabilidade calibrada. Segue com correção heurística limitada. Não é probabilidade validada.
- **Exclusões:** sem matriz de edital, sem orientação automática de como resolver questões, sem peso de prova, sem cronômetro nem metas diárias obrigatórias. Sem coaching, sugestões de exercícios nem correção automática dos tipos de erro; a estudante faz a interpretação.

**Persistência:** migração `0007_novel_practice.py` cria somente a nova tabela `novel_practice` e seu índice, sem alterar as avaliações anteriores. Atualize com `alembic upgrade head` antes de iniciar a API. Versão `0.9.0`.

## Instalação e Atualização

### Instalação no seu repositório (v0.9)

**O conector do GitHub recusou escrita (403)**. Por isso este arquivo é um **pacote de atualização** e não um commit feito no GitHub. O instalador exige um clone do código da v0.8; não execute contra outra versão sem revisar as diferenças.

1. Extraia este ZIP em uma pasta à parte. Abra um terminal na **raiz do seu clone** `estudo-adaptativo` na versão v0.8.
2. Rode, ajustando o caminho do arquivo extraído:

   ```powershell
   python "C:\caminho\estudo-adaptativo-v0.9\aplicar_v09.py"
   python -m pip install -e ".[dev]"
   python -m pytest -q
   ```

3. Confira os resultados e as alterações:

   ```powershell
   git diff --stat
   git status
   ```

4. Se os testes passarem, faça backup do banco Neon e publique as mudanças:

   ```powershell
   git add .gitignore README.md app migrations tests scripts
   git commit -m "feat: estudo adaptativo v0.9 - desempenho e ineditas"
   git push origin master
   ```

5. O serviço Render conectado à `master` pode iniciar deploy automaticamente. A configuração existente executa `alembic upgrade head` antes de subir o FastAPI. Confirme que a migration `0007` ocorreu e o deploy está **Live** antes de testar a versão publicada.

A migração `0007_novel_practice` **só acrescenta** uma tabela e um índice. Não apaga nem substitui histórico de Cards ou Caderno de erros. O código fonte preexistente é preservado em backups `*.v08.bak` locais, ignorados no `.gitignore`; não os publique.

### Validação

Foram verificados localmente: sintaxe Python do instalador e dos três arquivos novos; sintaxe JS dos novos blocos; e a presença dos principais pontos de inserção na v0.8 do GitHub. **Não foi possível executar a suíte `pytest` contra o repositório completo nem testar o deploy**, pois a conexão permitiu leitura, mas não o checkout/publicação automática.

### Arquivos desta versão

- `aplicar_v09.py`: aplica as alterações aos arquivos existentes e instala os novos.
- `app/performance.py`: agregação de inéditas e indicadores por assunto, mantendo os grupos separados.
- `migrations/versions/0007_novel_practice.py`: migração aditiva de banco.
- `tests/test_performance_v9.py`: novos testes de persistência, edição, separação de métricas, auditoria e interface.

### Atualizar o projeto já publicado no Render

1. Extraia o ZIP desta versão. Copie os arquivos para a pasta do repositório Git existente, preservando a pasta oculta `.git` e seu arquivo `.env` local.
2. No terminal, dentro da pasta, execute:

   ```powershell
   git status
   git add -A
   git commit -m "feat: estudo adaptativo v0.9 - desempenho e ineditas"
   git push origin master
   ```
3. O serviço `estudo-adaptativo-bb`, já conectado à branch **master**, deve detectar o push e começar o deploy. Acompanhe o status no [Render Dashboard](https://dashboard.render.com/web/srv-dbunfkpsrm7s73feeqrg).
4. O `startCommand` existente (`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`) mantém as migrações existentes em dia (até **0007**).
5. Quando estiver `Live`, acesse [a aplicação](https://estudo-adaptativo-bb.onrender.com/) e teste o login e as filas.

**Não** crie um novo banco ou serviço no Render para atualizar esse projeto. Use o Neon e serviço atuais. Antes de uma alteração em produção, faça backup dos dados importantes; não execute `alembic downgrade base`.

### Variáveis de ambiente do Render

| Nome | Valor |
|---|---|
| `APP_ENV` | `production` |
| `DATABASE_URL` | Connection string do Neon (com SSL), guardada no painel privado |
| `ADMIN_USERNAME` | Nome de usuário escolhido |
| `ADMIN_PASSWORD_HASH` | Hash Argon2 gerado com `python -m app.auth hash-password` |
| `APP_SECRET_KEY` | Chave secreta longa e estável, configurada no painel privado |

Se você já cadastrou essas variáveis, **não as substitua** durante a atualização. Nunca compartilhe `DATABASE_URL`, a senha do banco, o hash da senha nem `APP_SECRET_KEY` em commits ou capturas de tela.

## Executar localmente (PowerShell)

Pré-requisitos: Python 3.11+, PostgreSQL e Git.

```powershell
git clone https://github.com/vanessadcamara/estudo-adaptativo.git
cd estudo-adaptativo
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m app.auth hash-password
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Preencha **somente no `.env` local** a URL de PostgreSQL, o usuário, o hash de sua senha e a chave secreta. O arquivo `.env` está no `.gitignore`.

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Acesse http://127.0.0.1:8000/ e faça login. A documentação da API em `/docs` existe somente fora do ambiente `production`.

## Arquitetura

```text
Navegador ── HTTPS ── Render (FastAPI + HTML/CSS/JS)
                          │
                          └── Neon (PostgreSQL)
```

O próprio FastAPI serve os arquivos em `app/static`. A aplicação funciona com SQLAlchemy e migrações Alembic. **Nenhuma senha deve ser salva no repositório.**

## Histórico de Versões

### Novidades da v0.7 — autonomia da matéria e estimativa de esquecimento

- **Fila estritamente separada por matéria:** Cards e Caderno de erros exigem selecionar a matéria antes de apresentar recomendações. Cada tela busca `/api/queue?subject_id=ID` separadamente; `subject_id=0` mostra somente questões legadas sem matéria. O caderno e os Cards podem mostrar matérias distintas simultaneamente.
- **Prazo vencido não é cobrança:** o vencimento faz um item subir apenas entre itens da matéria escolhida. Não define a matéria a estudar, não dispara revisões automáticas, não cria metas e não causa penalidade por ausência. A data de vencimento é uma referência, não um compromisso obrigatório.
- **Intervalos reajustados conforme desempenho:** notas baixas e lacunas mantêm intervalos curtos; dificuldade elevada os reduz; notas boas e acertos seguros repetidos permitem expansão até 60 dias. Erros recentes atenuam temporariamente esse crescimento, inclusive após um acerto isolado no Caderno de erros. Os critérios rigorosos de domínio da v0.6 permanecem.
- **Risco estimado de esquecimento:** Cards e questões apresentam um indicador de 0 a 100% calculado com uma curva exponencial, tempo decorrido, intervalo individual, notas, esforço, erros e confiança (de acordo com o tipo). **É uma estimativa heurística, não uma probabilidade calibrada nem inteligência artificial treinada**; sem histórico é exibido "sem histórico". Por ora, é informativo e não altera a fórmula exata de prioridade dos Cards.
- **Compatibilidade:** dados existentes continuam válidos, sem migração adicional de banco na v0.7. Os campos de risco são calculados a partir do histórico já salvo. O endpoint `/api/queue` sem filtro continua disponível para clientes antigos, mas não é usado para escolher matérias na nova interface.
- **Testes de regressão:** verificam isolamento de assuntos, questões, pesos, históricos e vencimentos; evolução temporal do risco; efeito do feedback nos intervalos; seleção no frontend e compatibilidade dos endpoints.

### Novidades da v0.6 — regras estritas de priorização e domínio

- **Fórmula exata dos Cards:** `P = 0,35D + 0,30T + 0,25E + 0,10I`, com cada componente em **0 a 100**. O resultado aparece no card e pode ser auditado expandindo **Entender prioridade e critérios de domínio**. **Não há bônus fora da fórmula.**
- **Precedência de vencimento na pilha:** se o prazo individual de um assunto vencer, ele ocupa o topo da pilha antes de qualquer não vencido, mesmo com `P` menor. Entre vencidos, maior atraso tem precedência; a pontuação desempata. Intervalos são individualizados entre **1 e 60 dias**, com limite conservador de **30 dias enquanto não houver domínio confirmado**.
- **Três estados explícitos:** Em aprendizagem, Em consolidação, Dominado. São derivados exclusivamente das avaliações persistidas e de tentativas vinculadas ao assunto.
- **Critérios rigorosos de domínio:** 3 notas 4 consecutivas, espaçadas em intervalos crescentes incluindo pelo menos 14 dias; **pelo menos 5 questões distintas e 8 tentativas**, taxa final de **85% ou mais**, sem erros conceituais graves pendentes; confirmação explícita de que explicou sem consulta e aplicou o conteúdo a questões inéditas/variadas. O último resultado de cada link conta para a taxa, evitando repetição inflar domínio.
- **Evidência explícita:** o questionário de Cards inclui duas opções novas: explicar sem consulta e aplicar a questões inéditas e variadas. A aplicação **não presume** que uma questão seja inédita nem interpreta seu conteúdo automaticamente; esse aspecto depende da sua confirmação. Para atingir `Dominado`, é necessário vincular questões ao assunto no cadastro.
- **Erros conceituais pendentes:** um erro marcado `Conceito` só é considerado resolvido após novo acerto com confiança `Estava segura` para a mesma questão. Uma lacuna grave declarada no Card só é resolvida por uma nova avaliação satisfatória com explicação sem consulta.
- **Histórico preservado:** a migração `0006_mastery_evidence.py` adiciona duas colunas booleanas sem apagar registros; avaliações antigas recebem `false` nesses campos e não viram evidência por suposição.
- **Caderno de erros:** a pontuação da pilha também é exibida em escala 0–100; questões com prazo vencido ganham prioridade sobre não vencidas. A fórmula de Cards **não é aplicada às questões**, que continuam com métricas próprias de erros e confiança.

### Frontend funcional e persistência (v0.5)

- **Cadastros que abrem de verdade:** ao tocar em `Nova matéria`, `Novo assunto` ou `Cadastrar questão`, o navegador abre um formulário em janela própria. Salvar aciona a API e persiste o registro em PostgreSQL.
- **Gerenciamento completo:** matérias, assuntos e links têm **Editar**, **Arquivar** e **Restaurar** (o último aparece com `Exibir arquivados`). O arquivamento é reversível e mantém os eventos históricos.
- **Telas próprias de avaliação:** `Marcar como finalizado` abre o questionário de Cards; `Avaliar desempenho` abre o formulário da questão. `Enviar respostas` persiste e atualiza a pilha.
- **Estados vazios clicáveis:** se o Neon estiver sem matérias/assuntos/links, cada tela oferece um botão para iniciar o cadastro. Nada é criado automaticamente em nome da usuária.
- **Atualização confiável:** scripts/CSS versionados (`?v=7`) e `Cache-Control: no-store` para estáticos evitam continuar vendo um frontend antigo.
- **Persistência explícita:** todas as ações de criação, edição, arquivo/restauração, revisão e tentativa usam o banco configurado em `DATABASE_URL`. `Refresh` fecha somente o lote técnico; não exclui avaliações.

#### Primeiro uso — banco vazio

1. Em **Cards** clique **Cadastrar matéria**. Preencha e clique em **Salvar matéria**.
2. Em **Configurações → Cards e assuntos**, clique **Novo assunto**, escolha a matéria e salve.
3. Volte a **Cards** e **selecione a matéria**: o primeiro assunto aparece; clique **Marcar como finalizado**, preencha as 3 avaliações e **Enviar respostas**.
4. Em **Configurações → Caderno de erros**, clique **Cadastrar questão**, cole o link e escolha a matéria.
5. Em **Caderno de erros**, **selecione a matéria**, abra o link, clique **Avaliar desempenho** e salve sua tentativa. Use **Atualizar prioridades** para reordenar e iniciar uma nova passagem.
6. Recarregue a página (`Ctrl + Shift + R`): matérias, tópicos, questões e avaliações continuam salvos. Para ver itens arquivados use as opções de gerenciamento em Configurações.

### Novidades da v0.4

- **Sem banner grande, ícones decorativos ou indicadores de "rodada do dia".** A pilha de Cards considera **todos os assuntos** da matéria selecionada, em ordem dinâmica de prioridade.
- **Caderno de erros como pilha adaptativa:** questões únicas por link; ordenação por histórico de erros, acertos, confiança, tempo transcorrido e necessidade de cobertura. Filtros por matéria e navegação Anterior/Próxima.
- **Sugestão de arquivamento reversível:** após pelo menos seis tentativas, com quatro acertos seguros consecutivos espalhados por pelo menos 14 dias e acurácia de 80% ou mais. O sistema **nunca arquiva automaticamente**. É possível retirar manualmente da pilha ou restaurar um link em Configurações sem apagar as tentativas.
- **Configurações com duas subabas:** *Cards* (cartões separados para Matérias e Assuntos) e *Caderno de erros* (cadastro de link e gerenciamento de links ativos/arquivados).
- **Registrar conteúdo novo removido da interface.** Um assunto cadastrado sem avaliações já é tratado como novo. A API legada de registro de aula foi preservada apenas por compatibilidade.
- **Refresh** está nas duas pilhas e consolida as avaliações desde a última atualização, depois recalcula a ordenação integral. Pode ser acionado a qualquer momento. Não representa o fim do dia nem reinicia o histórico.

A especificação de interface, formulários e algoritmo fica em [`docs/ESPECIFICACAO_FUNCIONAL.md`](docs/ESPECIFICACAO_FUNCIONAL.md).

## Como as pilhas funcionam

**Cards:** após você selecionar a matéria, todos os assuntos dela fazem parte do conjunto de revisão, inclusive os não vencidos. O algoritmo pondera recuperação (nota 0–4), dificuldade percebida, lacunas, importância, cobertura histórica e tempo real desde a última revisão. O estado "novo" é inferido pela ausência de avaliações.

**Caderno de erros:** após selecionar a matéria, só são mostradas as questões correspondentes; cada URL é única. As tentativas consideradas no cálculo incluem acerto/erro e nível de confiança (chute, dúvida ou segurança); erros recorrentes e maior tempo desde a última tentativa elevam a prioridade. Acertos seguros repetidos espaçam revisões. Arquivar tira da pilha ativa, mas mantém os dados e permite restaurar.

**Refresh:** encerra o lote técnico em aberto para permitir nova avaliação de um item no lote seguinte; **não tem duração e não é um dia de estudo**. O histórico e os últimos feedbacks permanecem no PostgreSQL. Pular ou deixar de estudar não equivale a errar.

## Rotas principais

As rotas de atualização utilizam `PATCH`; archive/restauração recebe `{"archived":true|false}`:

- `PATCH /api/subjects/{id}` — altera o nome da matéria.
- `PATCH /api/subjects/{id}/archive` — arquiva ou restaura matéria.
- `PATCH /api/topics/{id}` — edita assunto (e atualiza a matéria das questões vinculadas, se necessário).
- `PATCH /api/topics/{id}/archive` — arquiva ou restaura assunto.
- `PATCH /api/questions/{id}` — edita link, texto e associação da questão.

| Método | Caminho | Função |
|---|---|---|
| `GET/POST` | `/api/subjects` | Listar / cadastrar matérias |
| `GET/POST` | `/api/topics` | Listar / cadastrar assuntos |
| `GET/POST` | `/api/questions` | Listar / cadastrar questões (GET aceita `include_archived=true`) |
| `PATCH` | `/api/questions/{id}/archive` | `{"archived":true}` retira; `false` restaura |
| `GET` | `/api/queue?subject_id=ID` | Filas independentes e ordenadas da matéria escolhida, sem limite diário |
| `POST` | `/api/sessions` | Reutilizar ou abrir lote técnico de avaliações |
| `GET` | `/api/sessions/{id}/progress` | Itens avaliados no lote atual |
| `POST` | `/api/sessions/{id}/topic-reviews` | Nota 0–4, esforço e lacunas |
| `POST` | `/api/sessions/{id}/question-attempts` | Acerto, confiança e tipo de erro |
| `POST` | `/api/sessions/{id}/refresh` | Consolidar sem apagar histórico e reabrir a pilha |

As rotas do caderno exigem login e token CSRF para operações de escrita. A API `POST /api/sessions/{id}/new-content` permanece disponível para compatibilidade, mas **não aparece na interface**.

## Segurança e limitações

Esta é uma aplicação pessoal com uma conta administradora. Cookie `HttpOnly`, `Secure` em produção, `SameSite=Strict`; proteção CSRF e limitação simples de tentativas de login. Não há recuperação de senha por e-mail ou múltiplos usuários. A limitação de tentativas é em memória por instância e não substitui um rate limiter dedicado em escala. Faça backup do Neon conforme seu nível de risco.

O Render Free pode suspender serviços ociosos; consulte o painel para os limites vigentes. O sistema não acessa automaticamente o conteúdo de questões em plataformas que exigem login.

## Testes

```powershell
python -m pytest -q
```

Há testes automatizados, além do teste de navegação real em Chromium (script `scripts/smoke_navegador.py`), para autenticação, CSRF, preservação de histórico, filas completas, feedback e intervalos, arquivamento/restauração, sugestão conservadora e estrutura da interface. Os testes usam SQLite em memória; produção usa PostgreSQL. Migração **0007** é necessária para persistir as novas evidências de domínio; a gestão de matérias e assuntos permanece na migração **0005**.

## Limitações deliberadas da v0.9

- O risco de esquecimento é estimado de forma determinística, com coeficientes iniciais de projeto; não representa chance estatística validada individualmente. Ainda não utiliza histórico suficiente para ajuste de parâmetros por usuário.
- A importância do tópico já participa dos Cards via `I`; não há seleção automática da matéria pelo sistema nem otimização pelo tempo disponível. Essas capacidades são consideradas para versões futuras, sem comprometer a autonomia da estudante.
- A API sem `subject_id` é mantida exclusivamente por compatibilidade com clientes v0.6 e pode agregar dados de múltiplas matérias; a interface v0.9 sempre exige seleção e usa o filtro validado no servidor.

### v0.12 — proteção de retenção

- Revisões com atraso significativo (pelo menos 14 dias desde a última avaliação) reduzem progressivamente a penalização de diversificação; quando o atraso alcança três vezes o intervalo previsto, a penalização pode zerar. Isso não força revisões diárias nem escolhe automaticamente a matéria.
- Intervalos de cards e questões podem ser ajustados conservadoramente a partir de sucessos e falhas observados após intervalos reais, com mínimo de seis observações elegíveis por item ou doze na matéria. Sem dados suficientes, mantém-se o intervalo original. O ajuste é limitado a aproximadamente 25%, com teto de 60 dias e limites de domínio preservados.
- Os critérios de não repetição dentro da sessão e as filas independentes por matéria permanecem inalterados.
- A calibração é heurística e não garante desempenho em prova.
