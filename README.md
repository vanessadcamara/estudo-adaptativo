# Estudo Adaptativo · Banco do Brasil (Agente Comercial)

Aplicação web pessoal para **revisão inteligente por duas filas**, caderno de erros e registro de conteúdo novo, com histórico persistido no **PostgreSQL**. Interface em português entregue pelo próprio FastAPI, com login, e API protegida. Pode ser executada localmente ou no Render, usando PostgreSQL local ou Neon.

> **Privacidade:** credenciais são variáveis de ambiente, não arquivos versionados. Não publique `.env`, connection string, senha nem hash de senha. Os registros ficam no banco que você configurar. Recomenda-se repositório privado.

## Como funciona

**Duas horas de estudo, como referência (configurável):**
- **60 min de revisão**: Fila A (40 min para explicação sem consulta) + Fila B (20 min para questões do caderno de erros).
- **60 min de conteúdo novo**: assistir à aula, cadastrar o tópico e registrar o tempo. Isso não cria uma nota fictícia.

**Fila A: tópicos de revisão.** Avalie sua recuperação: `0` não lembrou; `1` lembrou fragmentos; `2` recuperação parcial com erros; `3` boa com pequenas lacunas; `4` excelente sem consulta. Prioridade: `0,35×dificuldade + 0,30×urgência + 0,25×histórico de lacunas + 0,10×importância`. Os fatores são normalizados de 0 a 1.

**Fila B: questões.** Cadastre apenas a URL da questão errada. Se o site exigir login, pode colar o enunciado e as alternativas (API). Não há tags obrigatórias. O sistema prioriza frequência de erros, tentativas recentes e incerteza (suavização por Laplace para não superestimar domínio com um único acerto). **O sistema não acessa automaticamente questões protegidas por login e não classifica o link por IA nesta primeira versão.** A associação ao tópico é opcional.

**Refresh:** fecha a sessão, consolida apenas respostas efetivamente registradas, mantém todas as tentativas e retorna as estatísticas. Na próxima sessão as filas são recalculadas. Dias sem estudar, mesmo após **uma semana ou mais**, não são registrados como faltas. Tópicos e questões não revisados não recebem notas artificiais. A urgência cresce conforme os dias efetivos desde a última revisão, e o limite de manutenção é de **60 dias**. Itens ainda não vencidos só aparecem se houver espaço na fila.

**Domínio:** exige no mínimo três recuperações seguidas com nota 4, em intervalos crescentes (último de ao menos 14 dias), e desempenho de pelo menos 85% na última tentativa de cinco questões diferentes do tópico, com no mínimo oito tentativas no histórico. Mesmo consolidado, o tópico continua em manutenção.

## Hospedagem Render + Neon (planos gratuitos)

A arquitetura é **navegador → Render (HTML/JS + FastAPI) → Neon (PostgreSQL)**. Não precisa hospedar o frontend separadamente. O `render.yaml` define um serviço gratuito, e o login protege as rotas e os dados antes de expor a aplicação à internet.

### 1. Criar o banco Neon

1. No painel [Neon](https://console.neon.tech/), crie um projeto PostgreSQL. Guarde a conexão do tipo **Direct connection** (sem `-pooler`, recomendada aqui por usar conexões persistentes SQLAlchemy). Não compartilhe a senha da conexão.
2. Copie a connection string com `?sslmode=require`. Neon normalmente apresenta `postgresql://...`: nosso código converte automaticamente para `postgresql+psycopg://...` (driver psycopg 3).
3. Mantenha o banco na nuvem como **única fonte do histórico**. Não use uma URL de PostgreSQL local (`localhost`) no Render.

### 2. Gerar credenciais de acesso ao sistema

Na máquina com o código e as dependências instaladas, execute:

```powershell
python -m pip install -e .
python -m app.auth hash-password
```

Informe e confirme **uma senha longa com pelo menos 12 caracteres**. O utilitário imprimirá `ADMIN_PASSWORD_HASH=...`. Copie somente o hash para o painel privado do Render. A senha em si não deve entrar no GitHub. Você também define um nome de usuário particular em `ADMIN_USERNAME`.

`APP_SECRET_KEY` será gerado automaticamente pelo Render no primeiro deploy do Blueprint. Ele é usado para criar a proteção CSRF da sessão; mantenha-o estável.

### 3. Publicar no Render

1. Faça commit dos arquivos desta versão no repositório GitHub (incluindo `render.yaml`, `.python-version`, `migrations/` e `app/static/`; **sem** `.env`).
2. No [Render Dashboard](https://dashboard.render.com/), entre em **New → Blueprint** e escolha o repositório. O Render reconhecerá `render.yaml`.
3. Selecione o plano `Free` e informe as variáveis solicitadas pelo Blueprint, todas no painel privado:

| Variável | Conteúdo |
|---|---|
| `DATABASE_URL` | URL do Neon (com `sslmode=require`) |
| `ADMIN_USERNAME` | Nome de usuário escolhido |
| `ADMIN_PASSWORD_HASH` | Hash Argon2 gerado pelo comando acima |
| `APP_ENV` | `production` (definido em `render.yaml`) |
| `APP_SECRET_KEY` | Gerado automaticamente pelo Render |

4. O build executa `pip install .` e o start executa `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`. A migração cria a tabela de sessões autenticadas sem remover as tabelas ou o histórico de estudo.
5. Quando o serviço estiver `Live`, abra a URL HTTPS `https://<nome-do-serviço>.onrender.com` exibida no painel. Entre com seu usuário e senha e cadastre uma matéria para testar a persistência.

**Atenção:** não use `alembic downgrade base` com dados reais. Se você já tiver estudado no PostgreSQL local, o Neon começará vazio. A migração do histórico local para a nuvem precisa ser feita separadamente, com backup e importação de dados.

**Limites gratuitos:** o Render pode suspender o serviço quando inativo, gerando uma espera na próxima visita. Os limites/planos podem mudar. A aplicação e o Neon precisam estar ativos para acessar os dados; o GitHub sozinho não é deploy.

### Segurança em produção

- Uma única conta administradora (`ADMIN_USERNAME` + hash Argon2 da senha).
- Sessão de login revogável em tabela separada (somente hash SHA-256 do token). Cookie `HttpOnly`, `Secure` em produção, `SameSite=Strict`, validade de 7 dias.
- `X-CSRF-Token` obrigatório para todas as alterações. API e painel só acessíveis com login.
- Limitação de tentativas de login por IP/processo, cabeçalhos de segurança e documentação de API desabilitada em produção.
- **Não há recuperação automática de senha por e-mail:** para redefinir a senha, gere outro hash e atualize `ADMIN_PASSWORD_HASH` no Render. Sessões anteriores continuarão válidas até expirar ou serem encerradas; para invalidar todas, altere `APP_SECRET_KEY` **e** revogue/apague as sessões em `auth_sessions` com orientação técnica apropriada (a chave por si só não invalida a sessão salva).
- Para um projeto pessoal é uma camada inicial de proteção; login limita acesso, mas não substitui backups, atualização de dependências e monitoramento de logs.

## Instalar no Windows (PowerShell)

Pré-requisitos: **Python 3.11+** e **PostgreSQL local** instalado/rodando.

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

Crie um banco vazio no PostgreSQL, por exemplo usando `psql`:

```sql
CREATE DATABASE estudo_bb;
```

Abra **`.env` somente na sua máquina** e substitua `usuario`, `senha`, host/porta e banco na `DATABASE_URL`. Preencha também `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` (resultado do primeiro comando) e `APP_SECRET_KEY` (resultado do segundo comando). Se sua senha contiver caracteres reservados (como `@`, `:`, `/`), use codificação URL (percent-encoding). Nunca envie `.env` para o GitHub.

Depois:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Acesse **http://127.0.0.1:8000** e entre com seu usuário e senha. A documentação interativa da API ficará em **http://127.0.0.1:8000/docs** apenas fora de produção.

Se o PowerShell bloquear `Activate.ps1`, use diretamente `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"` e `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`; no lugar de `alembic`, use `.\.venv\Scripts\python.exe -m alembic upgrade head`.

## Fluxo de uso

1. Crie matérias (Conhecimentos Bancários, Português, Informática etc.) e tópicos (A1, A2...); matérias não precisam conter os tópicos do edital inteiro inicialmente.
2. Guarde links das questões erradas, com ou sem associação manual ao tópico.
3. Inicie ou retome uma sessão. A fila se atualiza ao abrir. Registre suas recuperações e tentativas; o mesmo item aparece apenas uma vez por sessão.
4. Registre seu tempo de conteúdo novo. Clique em **Refresh e finalizar** ao encerrar o lote.
5. Na próxima sessão, o sistema leva em conta o histórico e o tempo transcorrido desde a revisão anterior, não um calendário fixo.

## Rotas principais

| Método | Endpoint | Ação |
|---|---|---|
| `POST` | `/api/subjects`, `/api/topics`, `/api/questions` | Cadastrar matéria, tópico ou questão |
| `GET` | `/api/dashboard`, `/api/queue` | Histórico resumido e prévia das filas |
| `POST` | `/api/sessions` | Iniciar ou retomar a sessão aberta |
| `GET` | `/api/sessions/open` | Recuperar a sessão em andamento |
| `GET` | `/api/sessions/{id}/queue` | Fila da sessão sem itens já feitos nela |
| `POST` | `/api/sessions/{id}/topic-reviews` | Registrar nota de 0 a 4 |
| `POST` | `/api/sessions/{id}/question-attempts` | Registrar acerto ou erro |
| `POST` | `/api/sessions/{id}/new-content` | Registrar aula/conteúdo novo |
| `POST` | `/api/sessions/{id}/refresh` | Fechar sessão e consolidar histórico |

Para personalizar o tempo da fila use `GET /api/queue?topic_minutes=40&question_minutes=20`. Cada tópico ocupa 10 min estimados e cada questão ocupa 5 min estimados (primeira versão).

## Testes

```powershell
python -m pytest -q
```

A suíte usa SQLite **somente nos testes automatizados** (em memória, sem afetar seu PostgreSQL), incluindo: autenticação, CSRF, logout e expiração de sessão, histórico preservado, duplicidade no mesmo lote, link inválido, conteúdo novo sem nota e retorno depois de sete dias.

## Estrutura

```text
app/
  main.py            API FastAPI
  engine.py          Regras de priorização e manutenção
  models.py          Tabelas persistidas
  schemas.py         Validação
  db.py              Conexão PostgreSQL local ou Neon via .env
  auth.py            Login, Argon2, sessões e CSRF
  static/             Interface HTML, CSS e JS
migrations/           Versão inicial do esquema (Alembic)
tests/                Testes de API e algoritmo
```

### Limitações desta versão

- O backend deve rodar em um computador/servidor com acesso ao PostgreSQL. **O GitHub não acessa o banco da sua máquina.**
- A autenticação protege uma conta pessoal. Não há cadastro de múltiplas contas nem recuperação por e-mail. Utilize HTTPS quando publicar.
- A associação automática do conceito de uma questão por IA, a geração de questões equivalentes e a importação de questões de plataformas fechadas **não estão implementadas**.
- O controle da hora de conteúdo novo é registro de estudo, não um temporizador. As estimativas de 40/20/60 min são referências, não bloqueios.
- Não execute `alembic downgrade base` com histórico real: a operação remove as tabelas e os dados.
