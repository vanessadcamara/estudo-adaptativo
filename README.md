# Estudo Adaptativo · Banco do Brasil (Agente Comercial)

Aplicação local para **revisão inteligente por duas filas**, caderno de erros e registro de conteúdo novo, com histórico persistido no **PostgreSQL**. Interface em português no navegador e API FastAPI.

> **Privacidade:** não inclua credenciais nem dados pessoais no GitHub. `.env` é ignorado pelo Git. As respostas e sessões ficam apenas no banco que você configurar. O repositório do código pode ser público ou privado; recomenda-se privado.

## Como funciona

**Duas horas de estudo, como referência (configurável):**
- **60 min de revisão**: Fila A (40 min para explicação sem consulta) + Fila B (20 min para questões do caderno de erros).
- **60 min de conteúdo novo**: assistir à aula, cadastrar o tópico e registrar o tempo. Isso não cria uma nota fictícia.

**Fila A: tópicos de revisão.** Avalie sua recuperação: `0` não lembrou; `1` lembrou fragmentos; `2` recuperação parcial com erros; `3` boa com pequenas lacunas; `4` excelente sem consulta. Prioridade: `0,35×dificuldade + 0,30×urgência + 0,25×histórico de lacunas + 0,10×importância`. Os fatores são normalizados de 0 a 1.

**Fila B: questões.** Cadastre apenas a URL da questão errada. Se o site exigir login, pode colar o enunciado e as alternativas (API). Não há tags obrigatórias. O sistema prioriza frequência de erros, tentativas recentes e incerteza (suavização por Laplace para não superestimar domínio com um único acerto). **O sistema não acessa automaticamente questões protegidas por login e não classifica o link por IA nesta primeira versão.** A associação ao tópico é opcional.

**Refresh:** fecha a sessão, consolida apenas respostas efetivamente registradas, mantém todas as tentativas e retorna as estatísticas. Na próxima sessão as filas são recalculadas. Dias sem estudar, mesmo após **uma semana ou mais**, não são registrados como faltas. Tópicos e questões não revisados não recebem notas artificiais. A urgência cresce conforme os dias efetivos desde a última revisão, e o limite de manutenção é de **60 dias**. Itens ainda não vencidos só aparecem se houver espaço na fila.

**Domínio:** exige no mínimo três recuperações seguidas com nota 4, em intervalos crescentes (último de ao menos 14 dias), e desempenho de pelo menos 85% na última tentativa de cinco questões diferentes do tópico, com no mínimo oito tentativas no histórico. Mesmo consolidado, o tópico continua em manutenção.

## Instalar no Windows (PowerShell)

Pré-requisitos: **Python 3.11+** e **PostgreSQL local** instalado/rodando.

```powershell
git clone https://github.com/vanessadcamara/estudo-adaptativo.git
cd estudo-adaptativo
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Crie um banco vazio no PostgreSQL, por exemplo usando `psql`:

```sql
CREATE DATABASE estudo_bb;
```

Abra **`.env` somente na sua máquina** e substitua `usuario`, `senha`, host/porta e banco na `DATABASE_URL`. Se sua senha contiver caracteres reservados (como `@`, `:`, `/`), use codificação URL (percent-encoding). Nunca envie `.env` para o GitHub.

Depois:

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Acesse **http://127.0.0.1:8000** para usar a interface ou **http://127.0.0.1:8000/docs** para a documentação interativa da API.

Se o PowerShell bloquear `Activate.ps1`, use diretamente `.\venv\Scripts\python.exe -m pip install -e ".[dev]"` e `.\venv\Scripts\python.exe -m uvicorn app.main:app --reload`; no lugar de `alembic`, use `.\venv\Scripts\python.exe -m alembic upgrade head`.

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

A suíte usa SQLite **somente nos testes automatizados** (em memória, sem afetar seu PostgreSQL), incluindo: histórico preservado, duplicidade no mesmo lote, link inválido, conteúdo novo sem nota e retorno depois de sete dias.

## Estrutura

```text
app/
  main.py            API FastAPI
  engine.py          Regras de priorização e manutenção
  models.py          Tabelas persistidas
  schemas.py         Validação
  db.py              Conexão local via .env
  static/             Interface HTML, CSS e JS
migrations/           Versão inicial do esquema (Alembic)
tests/                Testes de API e algoritmo
```

### Limitações desta versão

- O backend deve rodar em um computador/servidor com acesso ao PostgreSQL. **O GitHub não acessa o banco da sua máquina.**
- A interface não tem login; execute em `127.0.0.1`, não a exponha à internet sem autenticação e HTTPS.
- A associação automática do conceito de uma questão por IA, a geração de questões equivalentes e a importação de questões de plataformas fechadas **não estão implementadas**.
- O controle da hora de conteúdo novo é registro de estudo, não um temporizador. As estimativas de 40/20/60 min são referências, não bloqueios.
- Não execute `alembic downgrade base` com histórico real: a operação remove as tabelas e os dados.
