# Especificação funcional — Estudo Adaptativo BB v0.4

## Princípios

- Não há cronômetro, sessões fixas por data, cobrança diária, limite de tópicos por dia ou penalidade por ausência.
- Toda matéria tem uma pilha **completa e contínua** de assuntos. Todo caderno tem uma pilha **completa e contínua** de questões não arquivadas.
- A avaliação é explícita; itens não vistos ou pulados não geram nota, erro nem tentativa.
- Refresh recalcula prioridades com o histórico acumulado e o tempo corrido; pode ser usado quando desejar.
- Dados e tentativas são preservados; remover questão da pilha significa arquivar de forma reversível.

## Tela 1 — Cards

**Controles:** dropdown `Matéria`, botão `Atualizar prioridades`, cartão do assunto recomendado, ações `Marcar como finalizado` e `Pular por agora`.

**Pilha:** `Todas as matérias` ou uma matéria específica. Todos os assuntos aparecem em ordenação dinâmica por prioridade. Não são exibidos totalizadores de rodada, meta diária, chips de intervalos nem contagem de revisões do dia.

**Ao finalizar:** aparece um questionário com os seguintes campos:

| Campo | Valores | Obrigatório |
|---|---|---|
| Memória sem consultar | 0 (não lembrei), 1 (fragmentos), 2 (parcial com erros), 3 (bom com lacunas pequenas), 4 (correto e seguro) | Sim |
| Esforço de recuperação | Fácil, Moderado, Muito difícil | Sim |
| Lacuna conceitual grave | Não / Sim | Sim |
| Anotações | Texto livre | Não |

`Enviar respostas` registra o feedback e exibe o próximo assunto não avaliado desde o último refresh. `Pular` oculta somente durante essa passagem, sem reduzir peso ou registrar erro.

## Tela 2 — Caderno de erros

**Controles:** dropdown `Matéria`, botão `Atualizar prioridades`, card de uma questão única, `Anterior` e `Próxima`.

**Card:** link (quando informado), enunciado (quando informado), motivo da recomendação, prioridade e data relativa da última avaliação. Nenhuma ligação com dias fixos de estudo.

**Formulário:**

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

1. **Matérias**: nome (obrigatório); lista das matérias já cadastradas.
2. **Assuntos**: matéria, nome, código opcional, importância 1 a 5; lista dos assuntos da matéria selecionada. O assunto cadastrado entra imediatamente na pilha, sem registrar primeira aula.

**Caderno de erros** contém dois painéis:

1. **Adicionar questão errada**: matéria, URL ou enunciado, assunto opcional. Links repetidos não geram segunda questão.
2. **Gerenciar links**: alternar entre `Questões na pilha` e `Questões arquivadas`, retirar uma questão ou restaurá-la com o histórico original.

Não há formulário de registrar conteúdo novo. A API legada permanece para compatibilidade com dados já registrados, mas não participa do fluxo principal.

## Algoritmo (implementação atual)

**Cards:** prioridade pontuada pela dificuldade de recordar (33%), tempo relativo ao intervalo (30%), histórico de lacunas/erros (23%), importância (9%) e bônus de cobertura para pouco histórico (até 5%); lacuna grave fornece reforço adicional. Intervalo proposto entre 1 e 60 dias, ajustado por feedback. Tópicos dominados continuam na pilha de manutenção.

**Questões:** prioridade considerando insucesso suavizado (36%), frequência histórica de erros (19%), tempo relativo ao intervalo (29%), incerteza por amostra pequena (9%), bônus de cobertura (até 7%) e reforço para erros recorrentes (12%). A confiança reduz o valor de acertos chutados. Os intervalos sugeridos chegam até 60 dias; **não há impedimento de revisitar antes**.

Os percentuais são pesos heurísticos iniciais, não um modelo de aprendizado de máquina treinado. A avaliação faz os indicadores mudarem; as pilhas são reordenadas pela prioridade numérica sem cortes por data.

## Persistência e compatibilidade

- Dados: PostgreSQL, SQLAlchemy + Alembic; login e histórico existentes são preservados.
- Migração nova: `0004_archive_questions.py` adiciona `archived_at` em `questions` (valor inicial `NULL` para manter todos os links ativos).
- API nova: `PATCH /api/questions/{id}/archive` aceita `{"archived":true|false}`.
- Dados anteriores (`new_content_logs`, sessões e feedbacks) não são eliminados.
- Deployment: branch `master`, Render web service Free, PostgreSQL Neon; start aplica `alembic upgrade head`.
