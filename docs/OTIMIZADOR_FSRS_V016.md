# V0.16 — Otimização completa FSRS-6 (21 parâmetros)

O projeto usa **Py-FSRS** `fsrs>=6.3.2,<7`. O motor de inferência é leve e roda no Render. O treinamento completo depende do extra `fsrs[optimizer]` (PyTorch, pandas, numpy, tqdm), **instalado apenas no executor externo**. Não coloque o extra `optimizer` no `render.yaml`.

## Fluxo de produção

1. O usuário avalia assuntos e questões; o backend salva avaliações no PostgreSQL e atualiza a fila, usando as regras da v0.14 e, se validados, os modelos leves da v0.15 ou os parâmetros completos da v0.16.
2. O **GitHub Actions** agenda um trabalho semanal em `.github/workflows/optimize-fsrs.yml`, fora do Render. Antes de otimizar, aplica as migrações pendentes ao banco configurado em `FSRS_DATABASE_URL`; faça backup antes de atualizar o código. Esse trabalho verifica o histórico de cada matéria/tipo e não treina se o histórico for insuficiente.
3. Para cada escopo elegível, o trabalhador constrói objetos `fsrs.ReviewLog` só com eventos **anteriores** à fronteira temporal de validação, executa `fsrs.Optimizer(...).compute_optimal_parameters()` e valida os **21 parâmetros** usando `fsrs.Scheduler`.
4. A validação compara previsão antes de cada revisão com sucesso/esquecimento real dos eventos **posteriores** à fronteira. Mede Brier, desvio entre retenção prevista e observada e comparação com a v0.14 e FSRS não ajustado.
5. Apenas um candidato aprovado é gravado em `retention_profiles.optimizer_parameters`. O histórico completo permanece intacto, e `retention_model_runs` registra todas as tentativas. Uma falha de treino preserva o modelo anterior; depois de resultados posteriores suficientes, regressão relevante pode desativar os pesos completos.
6. O Render lê os parâmetros do Neon e faz *replay* FSRS para calcular o intervalo; o intervalo permanece limitado a ±25% da recomendação conservadora, máximo 60 dias (30 em Cards sem domínio). Nenhum treinamento pesado ocorre ao concluir uma sessão.

## Ativar a rotina — configuração única

1. Envie a v0.16 ao repositório **`vanessadcamara/estudo-adaptativo`**, branch `master`, após revisar o código e fazer backup do banco.
2. No GitHub, abra **Settings → Secrets and variables → Actions → New repository secret**. Crie **`FSRS_DATABASE_URL`** com a string de conexão do Neon autorizado (`sslmode=require`). Não coloque URL de banco, senha ou tokens em arquivos do projeto ou mensagens.
3. Confirme que GitHub Actions está habilitado e autorizado para este repositório privado. Execute **Actions → Otimizacao FSRS semanal → Run workflow** para testar; o agendamento dispara aos domingos às 09:00 UTC, sujeito aos limites e atrasos do GitHub Actions.
4. Não é preciso executar o otimizador ao terminar a sessão. A agenda faz novas tentativas toda semana, sem custo computacional extra no servidor Render.

## Restrições e interpretação

- O otimizador oficial usa **512 revisões espaçadas para o primeiro passo de gradiente**; abaixo disso, pode retornar os parâmetros padrão. Esta versão exige **no mínimo 512 no treino e 100 no teste**, além de diversidade de exemplos. Isso é **por matéria e tipo**, não 512 registros somados de matérias diferentes.
- O limiar estatístico é conservador, mas ainda **não comprova** validade preditiva individual; a própria recuperação nos Cards é autoavaliada, e repetir questões antigas introduz familiaridade. Não trate 90% de retenção do modelo como 90% de acertos na prova.
- O modelo é retreinado somente quando registros novos alteram a assinatura do histórico. A decisão de aceitar novos parâmetros é independente por escopo.
- A fila mantém as regras de sessão e de diversificação já existentes; os pesos 35/30/25/10 da fórmula dos Cards não são treinados pelo FSRS.
- Não é necessário fornecer `APP_SECRET_KEY` ou credenciais da aplicação ao executor: apenas `FSRS_DATABASE_URL` para leitura/gravação das tabelas do modelo.
- **A rota de sessão nunca executa o otimizador**. Ausência de GitHub Actions ou do segredo implica que o modelo completo ficará inativo, mas o sistema continua operando com a v0.14/v0.15.

## Verificação

```bash
python -m pytest -q
# Requer fsrs[optimizer] instalado e DATABASE_URL configurado:
python -m app.optimize_retention
# Quando preparado para gravar modelos aprovados:
python -m app.optimize_retention --apply
```

As verificações unitárias em `tests/test_full_optimizer_v16.py` simulam a biblioteca para testar segurança, isolamento temporal, persistência e fallback. Elas **não** são execução real de treinamento PyTorch. O fluxo real roda somente em ambiente com `fsrs[optimizer]` disponível.
