# Estudo Adaptativo BB — versão 0.5

Sistema pessoal de revisão adaptativa para **Banco do Brasil — Escriturário (Agente Comercial)**. A interface tem **três abas**: Cards, Caderno de erros e Configurações. Sem cronômetro, sem cotas diárias e sem calendário obrigatório.

A aplicação entrega o frontend pelo próprio **FastAPI** e persiste revisões, tentativas e sessões no **PostgreSQL** (local ou Neon). Login com senha Argon2, sessão protegida por cookie e controle CSRF.

## Novidades da v0.5 — telas funcionais e persistência

- **Cadastros que abrem de verdade:** ao tocar em `Nova matéria`, `Novo assunto` ou `Cadastrar questão`, o navegador abre um formulário em janela própria. Salvar aciona a API e persiste o registro em PostgreSQL.
- **Gerenciamento completo:** matérias, assuntos e links têm **Editar**, **Arquivar** e **Restaurar** (o último aparece com `Exibir arquivados`). O arquivamento é reversível e mantém os eventos históricos.
- **Telas próprias de avaliação:** `Marcar como finalizado` abre o questionário de Cards; `Avaliar desempenho` abre o formulário da questão. `Enviar respostas` persiste e atualiza a pilha.
- **Estados vazios clicáveis:** se o Neon estiver sem matérias/assuntos/links, cada tela oferece um botão para iniciar o cadastro. Nada é criado automaticamente em nome da usuária.
- **Atualização confiável:** scripts/CSS versionados (`?v=5`) e `Cache-Control: no-store` para estáticos evitam continuar vendo um frontend antigo.
- **Persistência explícita:** todas as ações de criação, edição, arquivo/restauração, revisão e tentativa usam o banco configurado em `DATABASE_URL`. `Refresh` fecha somente o lote técnico; não exclui avaliações.

### Primeiro uso — banco vazio

1. Em **Cards** clique **Cadastrar matéria**. Preencha e clique em **Salvar matéria**.
2. Em **Configurações → Cards e assuntos**, clique **Novo assunto**, escolha a matéria e salve.
3. Volte a **Cards**: o primeiro assunto aparece; clique **Marcar como finalizado**, preencha as 3 avaliações e **Enviar respostas**.
4. Em **Configurações → Caderno de erros**, clique **Cadastrar questão**, cole o link e escolha a matéria.
5. Em **Caderno de erros**, abra o link, clique **Avaliar desempenho** e salve sua tentativa. Use **Atualizar prioridades** para reordenar e iniciar uma nova passagem.
6. Recarregue a página (`Ctrl + Shift + R`): matérias, tópicos, questões e avaliações continuam salvos. Para ver itens arquivados use as opções de gerenciamento em Configurações.

## O que mudou na v0.4

- **Sem banner grande, ícones decorativos ou indicadores de “rodada do dia”.** A pilha de Cards considera **todos os assuntos** da matéria selecionada, em ordem dinâmica de prioridade.
- **Caderno de erros como pilha adaptativa:** questões únicas por link; ordenação por histórico de erros, acertos, confiança, tempo transcorrido e necessidade de cobertura. Filtros por matéria e navegação Anterior/Próxima.
- **Sugestão de arquivamento reversível:** após pelo menos seis tentativas, com quatro acertos seguros consecutivos espalhados por pelo menos 14 dias e acurácia de 80% ou mais. O sistema **nunca arquiva automaticamente**. É possível retirar manualmente da pilha ou restaurar um link em Configurações sem apagar as tentativas.
- **Configurações com duas subabas:** *Cards* (cartões separados para Matérias e Assuntos) e *Caderno de erros* (cadastro de link e gerenciamento de links ativos/arquivados).
- **Registrar conteúdo novo removido da interface.** Um assunto cadastrado sem avaliações já é tratado como novo. A API legada de registro de aula foi preservada apenas por compatibilidade.
- **Refresh** está nas duas pilhas e consolida as avaliações desde a última atualização, depois recalcula a ordenação integral. Pode ser acionado a qualquer momento. Não representa o fim do dia nem reinicia o histórico.

A especificação de interface, formulários e algoritmo fica em [`docs/ESPECIFICACAO_FUNCIONAL.md`](docs/ESPECIFICACAO_FUNCIONAL.md).

## Arquitetura

```text
Navegador ── HTTPS ── Render (FastAPI + HTML/CSS/JS)
                          │
                          └── Neon (PostgreSQL)
```

O próprio FastAPI serve os arquivos em `app/static`. A aplicação funciona com SQLAlchemy e migrações Alembic. **Nenhuma senha deve ser salva no repositório.**

## Atualizar o projeto já publicado no Render

1. Extraia o ZIP desta versão. Copie os arquivos para a pasta do repositório Git existente, preservando a pasta oculta `.git` e seu arquivo `.env` local.
2. No terminal, dentro da pasta, execute:

   ```powershell
   git status
   git add -A
   git commit -m "fix: frontend funcional e persistencia de cadastros"
   git push origin master
   ```
3. O serviço `estudo-adaptativo-bb`, já conectado à branch **master**, deve detectar o push e começar o deploy. Acompanhe o status no [Render Dashboard](https://dashboard.render.com/web/srv-dbunfkpsrm7s73feeqrg).
4. O `startCommand` existente (`alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`) aplica automaticamente a migração **0005**, que adiciona arquivamento reversível a matérias e tópicos sem apagar dados. As migrações anteriores também são mantidas.
5. Quando estiver `Live`, acesse [a aplicação](https://estudo-adaptativo-bb.onrender.com/) e teste o login e as duas filas.

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

## Como as pilhas funcionam

**Cards:** todos os assuntos cadastrados fazem parte do conjunto de revisão da matéria, inclusive os não vencidos. O algoritmo pondera recuperação (nota 0–4), dificuldade percebida, lacunas, importância, cobertura histórica e tempo real desde a última revisão. O estado "novo" é inferido pela ausência de avaliações.

**Caderno de erros:** cada URL é única. As tentativas consideradas no cálculo incluem acerto/erro e nível de confiança (chute, dúvida ou segurança); erros recorrentes e maior tempo desde a última tentativa elevam a prioridade. Acertos seguros repetidos espaçam revisões. Arquivar tira da pilha ativa, mas mantém os dados e permite restaurar.

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
| `GET` | `/api/queue` | Pilhas completas, ordenadas e sem limite diário |
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

São **23 testes automatizados**, além do teste de navegação real em Chromium (script `scripts/smoke_navegador.py`), para autenticação, CSRF, preservação de histórico, filas completas, feedback e intervalos, arquivamento/restauração, sugestão conservadora e estrutura da interface. Os testes usam SQLite em memória; produção usa PostgreSQL. Migração **0005** é necessária para a nova gestão de matérias e assuntos.
