# Estudo Adaptativo BB — v0.13

Sistema pessoal de estudo para **Banco do Brasil — Escriturário (Agente Comercial)**, com filas adaptativas independentes por matéria. Interface FastAPI + JavaScript; histórico persistido no **PostgreSQL configurado em `DATABASE_URL`** (por exemplo, Neon). As avaliações não são armazenadas no navegador.

## O que a v0.13 faz

- **Uma sessão, uma avaliação por item:** o mesmo assunto ou a mesma questão avaliada não reaparece na mesma sessão. Questões diferentes sobre um mesmo assunto são permitidas.
- **Filas por matéria:** você escolhe qual estudar; vencimento não força estudo diário nem interfere na fila de outra disciplina.
- **Alternância em 3 sessões:** reduz a posição dos itens revisados repetidamente nas últimas três sessões com atividade naquela matéria.
- **Equilíbrio em 12 sessões:** concede bônus moderado a itens elegíveis pouco revisitados nesse período.
- **Proteção de retorno:** depois de sete visitas com atividade à matéria sem avaliar um item elegível (vencido ou nunca revisado), ele recebe precedência sobre itens não protegidos, sem obrigar você a estudar naquele dia. Se vários itens estiverem protegidos, os mais adiados recebem preferência. Pular é permitido.
- **Proteção contra atraso:** a penalização de repetição é reduzida quando o atraso em relação ao intervalo recomendado aumenta.
- **Espaçamento e retenção observada:** intervalos-base de 1 a 60 dias são modulados conservadoramente por recuperações feitas após intervalos reais. Com poucas evidências, a regra-base permanece.
- **Estudo inicial separado de retenção:** o questionário do primeiro contato registra aprendizagem, mas não é computado como revisão espaçada.
- **Questionário de revisão:** recuperação sem consulta, precisão após conferência, dependência de ajuda, lacunas e dificuldade. A nota 0–4 é **inferida** pelas respostas; ainda é autoavaliação, não prova objetiva.
- **Questões inéditas:** registra total de tentativas e acertos por matéria; condições semelhantes à prova são opcionais. Esses acertos **não são atribuídos artificialmente a assuntos específicos**.
- **Domínio:** critérios exigentes de recuperações espaçadas, ausência de lacunas, explicação, aplicação e resultados em links diferentes do Caderno de erros. Não equivale a garantia de 90% na prova.

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

Em produção, use `APP_ENV=production`. A configuração `render.yaml` executa `alembic upgrade head` antes de subir a aplicação. A migração **`0008_v13_assessments.py`** adiciona campos de avaliação estruturada de forma compatível com os registros anteriores. **Faça backup do PostgreSQL antes de aplicar atualizações.**

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

As ações exigem autenticação e alterações usam proteção CSRF. A aplicação foi concebida para uma conta administrativa pessoal.

## Validação e limites

Execute `python -m pytest -q` para testes automatizados. O aplicativo é um **auxiliar de decisão**, não uma garantia de aprovação ou 90% de acertos. O desempenho em questões diferentes, com condições próximas às da prova e amostras suficientes, continua sendo evidência externa importante. Não há atualmente garantia de cobertura de todo o edital: os assuntos não cadastrados não entram nas filas.
