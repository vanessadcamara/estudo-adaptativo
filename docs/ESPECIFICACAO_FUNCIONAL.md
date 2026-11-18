# Especificação funcional — Estudo Adaptativo BB v0.7

## Princípios

- Não há cronômetro, sessões fixas por data, cobrança diária, limite de tópicos por dia ou penalidade por ausência.
- Toda matéria tem **filas independentes** de Cards e questões ativas, sem mistura de vencimentos, pesos ou históricos entre matérias. Nenhuma fila ativa antes de selecionar a matéria.
- A avaliação é explícita; itens não vistos ou pulados não geram nota, erro nem tentativa.
- Refresh recalcula prioridades com o histórico acumulado e o tempo corrido; pode ser usado quando desejar.
- Dados e tentativas são preservados; remover questão da pilha significa arquivar de forma reversível.

## Tela 1 — Cards

**Controles:** dropdown `Matéria`, botão `Atualizar prioridades`, cartão do assunto recomendado, ações `Marcar como finalizado` e `Pular por agora`.

**Pilha:** a matéria precisa ser selecionada explicitamente; não existe opção “Todas as matérias” na interface de estudo. Somente assuntos da matéria selecionada aparecem em ordenação dinâmica por prioridade. Não são exibidos totalizadores de rodada, meta diária, chips de intervalos nem contagem de revisões do dia.

**Ao finalizar:** abre-se uma tela modal própria com um questionário com os seguintes campos:

| Campo | Valores | Obrigatório |
|---|---|---|
| Memória sem consultar | 0 (não lembrei), 1 (fragmentos), 2 (parcial com erros), 3 (bom com lacunas pequenas), 4 (correto e seguro) | Sim |
| Esforço de recuperação | Fácil, Moderado, Muito difícil | Sim |
| Lacuna conceitual grave | Não / Sim | Sim |
| Explicação sem consulta | Checkbox afirmativo | Não (obrigatório somente para Dominado) |
| Aplicação em questões inéditas e variadas | Checkbox afirmativo | Não (obrigatório somente para Dominado) |
| Anotações | Texto livre | Não |

`Enviar respostas` registra o feedback e exibe o próximo assunto não avaliado desde o último refresh. `Pular` oculta somente durante essa passagem, sem reduzir peso ou registrar erro.

## Tela 2 — Caderno de erros

**Controles:** dropdown `Matéria` de seleção obrigatória, botão `Atualizar prioridades`, card de uma questão única, `Anterior` e `Próxima`. A matéria do Caderno de erros pode ser distinta da selecionada nos Cards; questões legadas sem matéria permanecem em grupo separado.

**Card:** link (quando informado), enunciado (quando informado), motivo da recomendação, prioridade, risco heurístico de esquecimento e data relativa da última avaliação. Nenhuma ligação com dias fixos de estudo.

**Ao clicar em Avaliar desempenho:** abre-se uma janela com o formulário:

| Campo | Valores | Obrigatório |
|---|---|---|
| Resultado | Errei / Acertei | Sim |
| Confiança | Chutei / Tive dúvidas / Estava segura | Sim |
| Dificuldade em caso de erro | Conceito, Interpretação, Atenção, Cálculo, Outro | Não |
| Anotação | Texto livre | Não |

Após salvar, o algoritmo recalcula a fila e a UI tenta avançar para uma questão ainda não avaliada nesse intervalo entre refreshes. Questões já avaliadas permanecem acessíveis por Anterior/Próxima, porém não podem ser contadas duas vezes no mesmo lote técnico; para reavaliar, use `Atualizar prioridades`.

**Arquivamento inteligente:** quando existem pelo menos seis tentativas, as quatro últimas corretas e marcadas como `Estava segura`, distribuídas ao longo de ao menos 14 dias, e acertos totais de pelo menos 80%, o card mostra **sugestão para arquivar link**. Jamais automático. Também há `Retirar da pilha` manual. Ambas usam o mesmo arquivamento reversível que conserva o histórico.

## Tela 3 — Configurações

Possui duas **subabas internas**, separadas das três abas principais:

**Cards** contém dois painéis independentes:

1. **Matérias**: botão `+ Nova matéria` abre formulário específico. A lista persistida mostra `Editar`, `Arquivar` e `Restaurar` (quando selecionado `Exibir arquivados`).
2. **Assuntos**: botão `+ Novo assunto` abre formulário com matéria, título, código e importância 1–5. Há `Editar`, `Arquivar` e `Restaurar`, respeitando a matéria. A inclusão alimenta a pilha imediatamente.

**Caderno de erros** contém dois painéis:

1. **Adicionar questão errada**: botão `+ Cadastrar questão` abre formulário específico com matéria, URL ou enunciado, assunto opcional. Links repetidos não geram segunda questão.
2. **Gerenciar links**: alternar entre `Questões ativas` e `Questões arquivadas`, editar/arquivar/restaurar com histórico preservado.

Não há formulário de registrar conteúdo novo. A API legada permanece para compatibilidade com dados já registrados, mas não participa do fluxo principal.

## Algoritmo (implementação atual)

**Cards:** escore exato em escala 0–100:

`P = 0,35D + 0,30T + 0,25E + 0,10I`

- **D**: dificuldade de recuperação, combinando nota 0–4 (78%) e percepção fácil/moderada/difícil (22%). Sem histórico, D=50.
- **T**: urgência = mínimo de 100 e `100 × dias desde a revisão / intervalo individual`. Sem histórico, T=0.
- **E**: frequência de notas 0–2 ou lacuna crítica no histórico (0–100); sem histórico, E=50.
- **I**: importância cadastrada 1–5, normalizada por `(importância−1)×25`.

A fórmula não contém bônus. **Somente na fila da matéria que a estudante selecionou**, os tópicos que atingiram o intervalo de revisão aparecem antes dos não vencidos. Dentro do grupo de vencidos, maior atraso vem antes e P desempata. Um vencimento não determina quando a estudante estuda nem a matéria que deve escolher. Intervalos: 1–60 dias para dominados, no máximo 30 dias para não dominados. Nem um tópico fácil pode permanecer indefinidamente abaixo de tópicos ainda não vencidos.

**Estados de aprendizagem:**

- **Em aprendizagem**: sem histórico, nota 0–2 ou lacuna/erro conceitual grave pendente.
- **Em consolidação**: recuperação razoável, mas algum requisito de domínio ainda não foi comprovado.
- **Dominado**: requisitos simultâneos: (1) três notas 4 consecutivas; (2) espaçamento crescente, com último intervalo ≥14 dias; (3) ao menos cinco questões distintas vinculadas e oito tentativas, com ≥85% de acertos seguros nos últimos resultados de cada questão; (4) nenhuma lacuna crítica ou erro conceitual pendente; (5) confirmação recente de explicação sem consulta; (6) confirmação recente de aplicação em questões inéditas e variadas. Esta última é autodeclarada — o sistema não lê automaticamente o conteúdo externo dos links.

**Questões:** prioridade considerando insucesso suavizado (36%), frequência histórica de erros (19%), tempo relativo ao intervalo (29%), incerteza por amostra pequena (9%), bônus de cobertura (até 7%) e reforço para erros recorrentes (12%). A confiança reduz o valor de acertos chutados. Os intervalos sugeridos chegam até 60 dias; **não há impedimento de revisitar antes**.

A pontuação é uma heurística explícita, não um modelo de aprendizado de máquina treinado. A escala de prioridade de questões também é 0–100, com vencimento à frente apenas das demais questões da mesma matéria selecionada; **não se reaproveita a fórmula de Cards em questões**. Não há cortes por dias do calendário.

### Risco de esquecimento e evolução dos intervalos — v0.7

- Cada Card ou questão já avaliada apresenta `forgetting_risk_percent` (0–100) e `forgetting_risk_level` (`baixo`, `moderado`, `alto`). Sem avaliação: risco nulo (`null`), nível `sem_dados`.
- Estimativa: `risco = 100 × [1 − (1 − b) × exp(−0,43 × d / max(1,i))]`; `d` é o número de dias desde a última avaliação; `i` é o intervalo atual em dias; `b` é o risco inicial heurístico que depende da última nota, dificuldade e lapsos (Cards) ou do último resultado, confiança e erros recentes (Caderno). O termo temporal cresce com o tempo. É um indicador de apoio, **não** uma previsão probabilística calibrada.
- Os intervalos individuais mantêm as regras v0.6 como base e recebem ajuste conservador quando houver falhas recentes anteriores ao último sucesso. Acertos seguros repetidos progressivamente elevam intervalos das questões até 60 dias; notas baixas e lapsos críticos encurtam o intervalo de assuntos. O limite de 30 dias para não dominados permanece.
- O risco informativo não cria novo termo na fórmula `P` de Cards nem na pontuação do Caderno. Seu uso quantitativo em prioridades, com importância e tempo disponível, fica reservado para evolução futura após avaliação/calibração.
- Nenhum agendamento, notificação, penalidade ou cobrança diária decorre de `next_due_at` ou `maintenance_required` (nome técnico mantido por compatibilidade).

### Isolamento obrigatório das filas — v0.7

- `/api/queue?subject_id=ID` e `/api/sessions/{id}/queue?subject_id=ID` retornam somente assuntos e questões da matéria selecionada. `ID=0` isola questões legadas sem matéria.
- O frontend mantém duas filas de estado separadas: Cards e Caderno de erros. A seleção precisa ser explícita e pode ser diferente entre as duas telas.
- Pesos, notas, erros, confiança, importância e vencimentos de uma matéria jamais alteram o cálculo ou a ordenação da outra. Testes automatizados cobrem regressões de isolamento.
- A rota sem filtro continua somente para compatibilidade de clientes anteriores; a interface não a utiliza para gerar recomendações.

## Persistência e compatibilidade

- Dados: PostgreSQL, SQLAlchemy + Alembic; login e histórico existentes são preservados.
- Migração anterior: `0006_mastery_evidence.py` adiciona `explained_without_consulting` e `applied_to_new_questions` em `topic_reviews`. Os registros antigos são preservados, com os novos campos iniciando em `false`. Migrações `0005` e anteriores seguem intactas.
- APIs de atualização: `PATCH` para edição e para arquivamento/restauração de `/api/subjects/{id}`, `/api/topics/{id}`, `/api/questions/{id}`. Os endpoints `/archive` usam `{"archived":true|false}`.
- Não há migração `0007` (nenhuma coluna ou tabela foi adicionada); os campos de risco são computados em cada consulta a partir das avaliações persistidas.
- Dados anteriores (`new_content_logs`, sessões e feedbacks) não são eliminados.
- Deployment: branch `master`, Render web service Free, PostgreSQL Neon; start aplica `alembic upgrade head`.

## Garantias práticas de funcionamento (v0.7)

- Nenhum cadastro fica somente no estado JavaScript. O formulário chama a API e recebe confirmação de `db.commit()`.
- Todos os dados são recarregados do PostgreSQL ao abrir o sistema, sem depender do cache do navegador.
- A pilha é calculada com todas as avaliações persistidas, e matérias/assuntos/links arquivados ficam fora da pilha sem eliminar relações históricas.
- O primeiro acesso com banco vazio mostra comandos clicáveis para criar matéria, assunto e questão. Não se preenche automaticamente dados fictícios.
- Há testes automatizados da API e um teste manual automatizado de navegação no Chromium em `scripts/smoke_navegador.py` (o script usa SQLite em memória; nunca altera o Neon real).
